"""``replay_run`` unit tests — recorded-engine readiness gate + rerun accounting.

W2/S38 slice (ANA-13 + ANA-14, Gate-1 Q2 = Option A). Every Run-engine seam
is monkeypatched at the ``replay/engine.py`` module namespace, so these tests
pin the engine's COMPOSITION contract without spawning any native engine:

- **ANA-13 (readiness gate):** ``replay_run`` gates on exactly the RECORDED
  engine via ``run/probe_engine(workspace, ecosystem, engine_name)`` — never
  on the workspace's first auto-detected candidate. In a polyglot workspace
  the two can differ; the pre-S38 ``assess_engine_readiness(workspace)`` call
  probed ``detect_engine_candidates(...)[0]`` and mis-gated both directions.
- **ANA-14 (rerun accounting, Q2-A):** a rerun that raises
  ``AdapterInvocationError`` is counted as an ERRORED ATTEMPT
  (``CrashedRerun`` in the classifier's input set) instead of being silently
  discarded — ``reruns_total`` = attempted reruns, and the verdict can
  honestly flip (2 crashes + 2 passes is NOT ``reproducible``). Crashed
  attempts are never persisted as Memory Entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.memory.project_store import ProjectStore, create_project_store
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.replay.classifier import CrashedRerun
from novetest.replay.context import ReplayContext
from novetest.replay.errors import REASON_ENGINE_NOT_READY, ReplayUnavailable
from novetest.run import (
    AdapterInvocationError,
    EngineNotSupportedError,
    NativeEngineContext,
    TestTarget,
)
from novetest.run.types import EngineReadinessResult

import novetest.replay.engine as replay_engine


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


_ORIGINAL_REF = RunReference(
    run_id="01SREPLAYENGINE000000ORIG", created_at=1_700_000_000_000
)


def _record(run_id: str, status: str) -> RunRecord:
    """Minimal ``RunRecord`` carrying only the fields the engine touches."""
    return RunRecord(
        run_reference=RunReference(run_id=run_id, created_at=1_700_000_001_000),
        target_expression="tests/",
        target_type="directory",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=1_700_000_001_000,
    )


def _context(
    workspace: Path, *, ecosystem: str, engine_name: str, original_status: str = "passed"
) -> ReplayContext:
    """A reconstructed replay context recording the given engine pair."""
    return ReplayContext(
        original_record=_record("01SREPLAYENGINE000000ORIG", original_status),
        test_target=TestTarget(
            target_expression="tests/",
            target_type="directory",
            workspace_path=workspace,
        ),
        engine_context=NativeEngineContext(
            ecosystem=ecosystem, engine_name=engine_name
        ),
    )


def _readiness(state: str, ecosystem: str, engine_name: str) -> EngineReadinessResult:
    return EngineReadinessResult(
        state=state,
        engine_context=(
            None
            if state == "engine-missing"
            else NativeEngineContext(ecosystem=ecosystem, engine_name=engine_name)
        ),
        evidence=(),
        issues=(),
    )


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return create_project_store(tmp_path)


@pytest.fixture()
def persisted(monkeypatch: pytest.MonkeyPatch) -> list[RunRecord]:
    """Capture ``store_run_evidence`` calls; nothing is written to disk."""
    calls: list[RunRecord] = []
    monkeypatch.setattr(
        replay_engine,
        "store_run_evidence",
        lambda _store, record: calls.append(record),
    )
    return calls


@pytest.fixture()
def written_results(monkeypatch: pytest.MonkeyPatch) -> list[ReplayResult]:
    """Capture ``write_replay_result`` calls; nothing is written to disk."""
    calls: list[ReplayResult] = []
    monkeypatch.setattr(
        replay_engine,
        "write_replay_result",
        lambda _store, _ref, result: calls.append(result),
    )
    return calls


def _install_context(
    monkeypatch: pytest.MonkeyPatch, context: ReplayContext
) -> None:
    monkeypatch.setattr(
        replay_engine, "reconstruct_replay_context", lambda _store, _ref: context
    )


def _install_probe(
    monkeypatch: pytest.MonkeyPatch,
    ready_pairs: dict[tuple[str, str], str],
) -> list[tuple[Path, str, str]]:
    """Fake ``probe_engine`` keyed by (ecosystem, engine) → readiness state.

    Returns the recorded call list so tests can assert the gate probed
    exactly the RECORDED engine pair (the load-bearing ANA-13 assertion:
    a partial regression to workspace-scan gating leaves this list empty).
    """
    calls: list[tuple[Path, str, str]] = []

    async def fake_probe(
        workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        calls.append((workspace, ecosystem, engine_name))
        state = ready_pairs.get((ecosystem, engine_name), "engine-missing")
        return _readiness(state, ecosystem, engine_name)

    monkeypatch.setattr(replay_engine, "probe_engine", fake_probe)
    return calls


def _install_execute(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[str | Exception],
) -> list[dict[str, Any]]:
    """Fake ``execute_with_engine_context`` scripted per invocation.

    Each entry is either a run-level status (→ a parsed ``RunRecord`` with
    that status) or an exception instance (→ raised). Returns the recorded
    call list.
    """
    calls: list[dict[str, Any]] = []

    async def fake_execute(
        test_target: TestTarget,
        engine_context: NativeEngineContext,
        *,
        artifact_dir: Path,
        run_id: str,
        timeout: float | None,
    ) -> tuple[RunRecord, tuple[str, ...]]:
        index = len(calls)
        calls.append({"run_id": run_id, "engine_context": engine_context})
        outcome = outcomes[index]
        if isinstance(outcome, Exception):
            raise outcome
        return _record(f"01SREPLAYENGINE0000RERUN{index:X}", outcome), ()

    monkeypatch.setattr(replay_engine, "execute_with_engine_context", fake_execute)
    return calls


# ---------------------------------------------------------------------------
# ANA-13 — the readiness gate probes exactly the RECORDED engine
# ---------------------------------------------------------------------------


async def test_gate_rejects_when_recorded_engine_not_ready_even_if_first_candidate_is(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """Polyglot scenario A: candidates[0] (pytest) ready, recorded cargo missing.

    The gate must reject with ``engine-not-ready`` (the exit-4
    ``ReplayUnavailable`` surface) BEFORE any rerun executes — instead of
    passing on the unrelated ready engine and letting every rerun crash into
    an ``unable_to_replay`` at exit 0.
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="rust", engine_name="cargo-test")
    )
    probe_calls = _install_probe(
        monkeypatch, ready_pairs={("python", "pytest"): "ready"}
    )
    execute_calls = _install_execute(monkeypatch, outcomes=[])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=3)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.reason == REASON_ENGINE_NOT_READY
    assert outcome.run_reference == _ORIGINAL_REF
    assert "rust:cargo-test" in (outcome.detail or "")
    # The load-bearing ANA-13 pin: the probe targeted the RECORDED pair.
    assert probe_calls == [(tmp_path, "rust", "cargo-test")]
    assert execute_calls == []
    assert written_results == []


async def test_gate_passes_when_recorded_engine_ready_even_if_first_candidate_is_not(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """Polyglot scenario B: recorded cargo ready, candidates[0] (pytest) not.

    The replay must proceed — the pre-S38 workspace-scan gate unjustly
    returned ``ReplayUnavailable`` (engine-not-ready, exit 4) here.
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="rust", engine_name="cargo-test")
    )
    probe_calls = _install_probe(
        monkeypatch, ready_pairs={("rust", "cargo-test"): "ready"}
    )
    _install_execute(monkeypatch, outcomes=["passed", "passed"])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=2)

    assert isinstance(outcome, ReplayResult)
    assert outcome.classification == "reproducible"
    assert outcome.reruns_total == 2
    assert probe_calls == [(tmp_path, "rust", "cargo-test")]
    assert len(persisted) == 2
    assert written_results == [outcome]


async def test_gate_single_ecosystem_behavior_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """Single-ecosystem regression pin: recorded engine == candidates[0].

    The ANA-13 fix is behavior-neutral here — a ready pytest workspace
    replaying a pytest run still proceeds to a classified ``ReplayResult``.
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    probe_calls = _install_probe(
        monkeypatch, ready_pairs={("python", "pytest"): "ready"}
    )
    _install_execute(monkeypatch, outcomes=["passed"])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=1)

    assert isinstance(outcome, ReplayResult)
    assert outcome.classification == "reproducible"
    assert outcome.reruns_total == 1
    assert outcome.per_rerun_outcomes == ("passed",)
    assert probe_calls == [(tmp_path, "python", "pytest")]
    assert len(persisted) == 1
    assert written_results == [outcome]


async def test_gate_not_ready_recorded_engine_single_ecosystem_still_exit4_surface(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """Single-ecosystem regression pin: a not-ready recorded engine still
    surfaces ``ReplayUnavailable`` / ``engine-not-ready`` (exit-4 posture)."""
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    _install_probe(monkeypatch, ready_pairs={})  # nothing ready
    execute_calls = _install_execute(monkeypatch, outcomes=[])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.reason == REASON_ENGINE_NOT_READY
    assert execute_calls == []
    assert written_results == []


async def test_gate_unsupported_recorded_pair_is_replay_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    tmp_path: Path,
) -> None:
    """Legacy-record counterexample: an out-of-matrix recorded pair.

    ``RunRecord.from_dict`` does not re-validate (ecosystem, engine) against
    the supported matrix, so a legacy/hand-edited ``record.json`` can reach
    the gate with a pair ``probe_engine`` refuses — handled as
    ``ReplayUnavailable`` (engine-not-ready), not a crash.
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="nose")
    )

    async def raising_probe(
        workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        raise EngineNotSupportedError(
            f"({ecosystem!r}, {engine_name!r}) is not a supported pair"
        )

    monkeypatch.setattr(replay_engine, "probe_engine", raising_probe)
    _install_execute(monkeypatch, outcomes=[])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.reason == REASON_ENGINE_NOT_READY
    assert "nose" in (outcome.detail or "")


# ---------------------------------------------------------------------------
# ANA-14 (Q2 Option A) — crashed reruns are errored ATTEMPTS, never discarded
# ---------------------------------------------------------------------------


def _crash(message: str) -> AdapterInvocationError:
    return AdapterInvocationError(message, kind="unparseable-output")


async def test_two_crashes_two_passes_is_not_reproducible(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """The ANA-14 headline case: ``--reruns=4``, 2 crashes + 2 passes.

    Pre-S38 the discard classified this ``reproducible`` with
    ``reruns_total: 2`` — a 50% crash rate hidden. Q2-A accounting: honest
    attempted count, crashes as ordered ``errored`` outcomes, verdict flips
    to ``inconsistent``.
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    _install_probe(monkeypatch, ready_pairs={("python", "pytest"): "ready"})
    _install_execute(
        monkeypatch,
        outcomes=[_crash("engine crashed mid-run"), "passed",
                  _crash("engine crashed mid-run"), "passed"],
    )

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=4)

    assert isinstance(outcome, ReplayResult)
    assert outcome.classification == "inconsistent"
    assert outcome.reruns_total == 4
    assert outcome.reruns_failed == 2
    # Attempt ORDER is preserved: crash, pass, crash, pass.
    assert outcome.per_rerun_outcomes == ("errored", "passed", "errored", "passed")
    assert outcome.consistency_summary["replay_errored"] == 2
    assert outcome.consistency_summary["replay_passed"] == 2
    # Only PARSED reruns are persisted — no fabricated Memory Entries.
    assert len(persisted) == 2
    assert written_results == [outcome]


async def test_all_crashes_is_unable_to_replay_result_not_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """All reruns crash (engine READY but every invocation unparseable).

    Exit/ok posture pin (per ``replay/errors.py``): a READY engine whose
    reruns crash is a completed attempt → a ``ReplayResult`` classified
    ``unable_to_replay`` (the CLI maps ANY ``ReplayResult`` to exit 0,
    ``ok: true``) — NOT a ``ReplayUnavailable``/``engine-not-ready`` (exit
    4), which is reserved for a missing/misconfigured engine caught by the
    gate. Accounting stays honest: ``reruns_total`` = attempted count (the
    pre-S38 discard reported ``no-replayed-runs`` with ``reruns_total: 0``).
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    _install_probe(monkeypatch, ready_pairs={("python", "pytest"): "ready"})
    _install_execute(
        monkeypatch, outcomes=[_crash("boom"), _crash("boom"), _crash("boom")]
    )

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=3)

    assert isinstance(outcome, ReplayResult)
    assert not isinstance(outcome, ReplayUnavailable)
    assert outcome.classification == "unable_to_replay"
    assert outcome.reason == "replay-run-errored"
    assert outcome.reruns_total == 3
    assert outcome.reruns_failed == 0
    assert outcome.per_rerun_outcomes == ("errored", "errored", "errored")
    assert outcome.replayed_run_reference is None
    assert persisted == []
    # The result is still cached — a completed (if unreproducible) attempt.
    assert written_results == [outcome]


async def test_zero_crashes_accounting_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """0-crash sessions are byte-identical to pre-S38 behavior."""
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    _install_probe(monkeypatch, ready_pairs={("python", "pytest"): "ready"})
    _install_execute(monkeypatch, outcomes=["passed", "failed", "passed"])

    outcome = await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=3)

    assert isinstance(outcome, ReplayResult)
    assert outcome.classification == "inconsistent"
    assert outcome.reruns_total == 3
    assert outcome.reruns_failed == 1
    assert outcome.per_rerun_outcomes == ("passed", "failed", "passed")
    assert outcome.consistency_summary["replay_errored"] == 0
    assert len(persisted) == 3
    assert written_results == [outcome]


async def test_crashed_rerun_detail_reaches_classifier_input(
    monkeypatch: pytest.MonkeyPatch,
    store: ProjectStore,
    persisted: list[RunRecord],
    written_results: list[ReplayResult],
    tmp_path: Path,
) -> None:
    """The adapter error message is retained on the ``CrashedRerun`` marker.

    Q2-A keeps the detail in the classifier's INPUT set only (no schema
    change on the serialized ``ReplayResult``).
    """
    _install_context(
        monkeypatch, _context(tmp_path, ecosystem="python", engine_name="pytest")
    )
    _install_probe(monkeypatch, ready_pairs={("python", "pytest"): "ready"})
    _install_execute(monkeypatch, outcomes=[_crash("jest exited 127"), "passed"])

    captured: list[list[RunRecord | CrashedRerun]] = []
    real_classify = replay_engine.classify_replay_consistency

    def spying_classify(
        original: RunRecord,
        rerun_attempts: list[RunRecord | CrashedRerun],
        *,
        attempted_at: int = 0,
    ) -> ReplayResult:
        captured.append(list(rerun_attempts))
        return real_classify(original, rerun_attempts, attempted_at=attempted_at)

    monkeypatch.setattr(
        replay_engine, "classify_replay_consistency", spying_classify
    )

    await replay_engine.replay_run(store, _ORIGINAL_REF, reruns=2)

    assert len(captured) == 1
    first_attempt = captured[0][0]
    assert isinstance(first_attempt, CrashedRerun)
    assert first_attempt.detail == "jest exited 127"
    assert isinstance(captured[0][1], RunRecord)
