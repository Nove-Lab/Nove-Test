"""Unit tests for the `novetest localization latest` CLI handler.

``localization latest`` is a thin wrapper around
``derive_latest_localization``: resolve store → validate flags → call the
engine's latest-resolution composer → project the outcome onto the envelope.
Most branches live inside the engine; the CLI's only job is correct
projection, flag validation, and store handling.

NOTE: These tests require ``localization_latest`` to be registered in
``cli/app.py`` as a command on ``localization_app``. If the handler is not
yet present the tests will fail with ``AttributeError`` — add the handler
per the Phase-4 CLI task brief before running.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from novetest.cli import _shared
from novetest.cli.handlers import localization as app_module
from novetest.cli.output import Envelope, EnvelopeError, OutputMode, emit_envelope
from novetest.localization import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    FORMULAS,
    LocalizationFinding,
    LocalizationUnavailable,
)
from novetest.localization.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
)
from novetest.models import RunReference
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.orchestration.workflows import localization as localization_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUN_ID = "01LATESTLOCLATESTLOCLATEST0"


_STALE_BUILD_METADATA: dict[str, Any] = {
    # What a PRE-``088091e`` build persisted — measured against a real
    # v0.2.1 binary, whose findings carry exactly these two keys.
    "changed_files_count": 0,
    "regression_reweighted": False,
}


def _current_build_metadata(mode: str) -> dict[str, Any]:
    """``metadata`` as THIS build's engine renders it, per mode.

    Both SBFL pipelines route through
    ``localization/derive.py::_exclusion_metadata``, so the four
    ``test_file_*`` keys are unconditional there; ``failure_proximity``
    never carried them. The row-43 staleness detector reads exactly that
    difference, so an SBFL-mode fixture with ``metadata={}`` is not a
    payload this build can emit — it is a stale-build payload, and tests
    for the ordinary case must not accidentally use one.
    """
    if mode == "failure_proximity":
        return dict(_STALE_BUILD_METADATA)
    return {
        "changed_files_count": None,
        "regression_reweighted": None,
        "test_file_locations_excluded": 1,
        "test_file_exclusion_reverted": False,
        "test_file_exclusion_basis": "exact",
        "test_file_locations_suppressed": [],
    }


def _make_finding(
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    derived_at: int = 7_000,
    mode: str = "sbfl_per_test",
    metadata: dict[str, Any] | None = None,
) -> LocalizationFinding:
    """Construct a deterministic ``LocalizationFinding`` for unit tests.

    Mirrors ``tests/unit/cli/test_localization.py::_make_finding`` with
    the ``mode`` parameter wired through so the latest-verb tests can
    exercise the Defect 7 carve-out (``failure_proximity`` formula-noop)
    end-to-end.
    """
    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    if mode == "failure_proximity":
        fp_loc = CodeLocation(
            kind="file",
            file="src/calc.py",
            symbol=None,
            line_range=None,
            primary_line=5,
            evidence_lines=(5,),
        )
        fp_entry = LocalizationEntry(
            rank=1,
            tied_with=(),
            code_location=fp_loc,
            score_raw=1.0,
            score_normalized=1.0,
            formula=formula,
            alternate_scores={},
            related_failed_tests=("tests/test_calc.py::test_buggy",),
            evidence_citations=(citation,),
        )
        return LocalizationFinding(
            run_reference=ref,
            engine_name="pytest",
            ecosystem="python",
            mode="failure_proximity",
            confidence="low",
            formula=formula,
            alternate_scores_available=(),
            top_n=top_n,
            entries=(fp_entry,),
            derived_at=derived_at,
            metadata=_current_build_metadata("failure_proximity")
            if metadata is None
            else metadata,
        )
    loc = CodeLocation(
        kind="symbol",
        file="src/calc.py",
        symbol="buggy",
        line_range=(4, 5),
        primary_line=5,
        evidence_lines=(5,),
    )
    entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=loc,
        score_raw=1.0,
        score_normalized=1.0,
        formula=formula,
        alternate_scores={f: 0.9 for f in FORMULAS if f != formula},
        related_failed_tests=("tests/test_calc.py::test_buggy",),
        evidence_citations=(citation,),
    )
    alt_scores_available = tuple(f for f in sorted(FORMULAS) if f != formula)
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode=mode,
        confidence="high",
        formula=formula,
        alternate_scores_available=alt_scores_available,
        top_n=top_n,
        entries=(entry,),
        derived_at=derived_at,
        metadata=_current_build_metadata(mode) if metadata is None else metadata,
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_shared, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    return json.loads(out)


# ---------------------------------------------------------------------------
# Case 1: Happy path — fact-set, identical projection to localization <run_id>
# ---------------------------------------------------------------------------


def test_localization_latest_emits_fact_set_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """``derive_latest_localization`` returns a finding → ``ok: true``,
    exit 0, ``data.localization_outcome.kind == "fact-set"``, schema_version
    absent from the block."""

    seen_stores: list[Any] = []

    def fake_derive(
        store: Any, *, formula: str = "ochiai", top_n: int = 10
    ) -> LocalizationFinding:
        seen_stores.append(store)
        return _make_finding()

    monkeypatch.setattr(localization_workflow, "derive_latest_localization", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0
    # Handler forwards exactly the resolved store sentinel.
    assert seen_stores == [stub_store]

    payload = _captured_envelope(capsys)
    assert payload["command"] == "localization.latest"
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    assert "schema_version" not in outcome
    assert outcome["formula"] == "ochiai"
    assert isinstance(outcome["entries"], list)


# ---------------------------------------------------------------------------
# Case 2: Empty store → no-run-evidence, run_reference null, detail present
# ---------------------------------------------------------------------------


def test_localization_latest_empty_store_surfaces_no_run_evidence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """An empty store: ``derive_latest_localization`` returns
    ``LocalizationUnavailable(reason="no-run-evidence")`` with
    ``run_reference=None``. The CLI surfaces ``kind: "unavailable"``,
    ``ok: true``, exit 0; ``run_reference`` is ``null`` on the wire."""

    monkeypatch.setattr(
        localization_workflow,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: LocalizationUnavailable(
            run_reference=None,
            reason=REASON_NO_RUN_EVIDENCE,
            detail="store has no run history",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_RUN_EVIDENCE
    assert outcome["run_reference"] is None
    assert outcome["detail"] is not None


# ---------------------------------------------------------------------------
# Case 3: All-tombstoned → run-not-analyzable
# ---------------------------------------------------------------------------


def test_localization_latest_all_tombstoned_surfaces_run_not_analyzable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """When all runs in the store are tombstoned / non-analyzable:
    ``derive_latest_localization`` returns ``run-not-analyzable``."""

    monkeypatch.setattr(
        localization_workflow,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: LocalizationUnavailable(
            run_reference=None,
            reason=REASON_RUN_NOT_ANALYZABLE,
            detail="all runs are tombstoned",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_NOT_ANALYZABLE


# ---------------------------------------------------------------------------
# Case 4: --formula tarantula --top-n 5 → both kwargs forwarded to engine
# ---------------------------------------------------------------------------


def test_localization_latest_flags_forwarded_to_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """Both ``--formula`` and ``--top-n`` are forwarded AS keyword arguments
    to ``derive_latest_localization``."""

    seen_kwargs: list[dict[str, Any]] = []

    def fake_derive(
        _store: Any, *, formula: str, top_n: int
    ) -> LocalizationFinding:
        seen_kwargs.append({"formula": formula, "top_n": top_n})
        return _make_finding(formula=formula, top_n=top_n)

    monkeypatch.setattr(localization_workflow, "derive_latest_localization", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="tarantula", top_n=5)
    assert exc_info.value.code == 0

    assert len(seen_kwargs) == 1
    assert seen_kwargs[0]["formula"] == "tarantula"
    assert seen_kwargs[0]["top_n"] == 5

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["formula"] == "tarantula"
    assert outcome["top_n"] == 5


# ---------------------------------------------------------------------------
# Case 5: Uninitialized workspace → uninitialized envelope, exit 2
# ---------------------------------------------------------------------------


def test_localization_latest_uninitialized_workspace_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
) -> None:
    """No Project Store → ``_require_store`` fires the uninitialized envelope
    and exits 2 BEFORE the engine is called."""

    def fake_require_store(_cmd: str) -> Any:
        import sys

        emit_envelope(
            Envelope(
                command="localization.latest",
                ok=False,
                errors=(EnvelopeError(code="uninitialized", message="no store"),),
            ),
            _shared._active_mode,
        )
        sys.exit(2)

    monkeypatch.setattr(app_module, "_require_store", fake_require_store)

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError(
            "derive_latest_localization called when no Project Store"
        )

    monkeypatch.setattr(localization_workflow, "derive_latest_localization", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest()
    assert exc_info.value.code == 2
    payload = _captured_envelope(capsys)
    assert payload["errors"][0]["code"] == "uninitialized"


# ---------------------------------------------------------------------------
# Cache-rederived warning suite (latest verb, Defect 5 fix). The detection
# + re-derive logic lives in the shared flag-override policy of
# ``orchestration/workflows/localization.py`` (W2/S22) — these tests only
# confirm the latest-verb path wires up the warning slot the same way as
# the explicit-run verb. The full six-scenario matrix is covered in
# ``test_localization.py``.
#
# Test pattern: ``derive_latest_localization`` is monkeypatched (at the
# workflow module) to return the cached finding on the first (initial)
# call; the policy then invalidates the (fake) cache and re-invokes
# ``derive_localization_findings`` directly (NOT
# ``derive_latest_localization`` — the run_reference is already resolved),
# which is monkeypatched to return the fresh finding.
# ---------------------------------------------------------------------------


_CACHE_WARN_CODE = "localization-cache-rederived"


@pytest.fixture
def stub_cache_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Wire the workflow's ``invalidate_localization_findings`` onto a tmp file.

    The post-Defect-5 invalidation calls the Localization engine's public
    ``invalidate_localization_findings(store, run_id)`` (missing-cache is
    a no-op). Unit tests don't have a real store on disk, so this fixture
    redirects the invalidation onto a real tmp file unlink whose
    existence the tests assert against.
    """
    fake_cache = tmp_path / "fake_localization_findings.json"
    fake_cache.touch()
    monkeypatch.setattr(
        localization_workflow,
        "invalidate_localization_findings",
        lambda *_a, **_k: fake_cache.unlink(missing_ok=True),
    )
    return fake_cache


def test_localization_latest_rederives_on_explicit_formula_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_cache_path: Path,
) -> None:
    """``latest`` resolves to a cached run; ``derive_latest_localization``
    returns the cached finding (formula ``ochiai``); user passed
    ``--formula=dstar2``. Post-Defect-5: cache file unlinked,
    ``derive_localization_findings`` re-invoked at ``dstar2``, fresh
    finding returned. One ``localization-cache-rederived`` warning with
    ``previous.formula == "ochiai"`` and ``requested.formula == "dstar2"``."""

    cached_finding = _make_finding(formula="ochiai", top_n=10)
    fresh_finding = _make_finding(formula="dstar2", top_n=10)
    monkeypatch.setattr(
        localization_workflow,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: cached_finding,
    )
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: fresh_finding,
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="dstar2")
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    # Fresh finding's formula reflects the user's explicit request.
    assert outcome["formula"] == "dstar2"
    assert not stub_cache_path.exists()  # invalidated

    warnings = payload["warnings"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == _CACHE_WARN_CODE
    details = warning["details"]
    assert details["previous"]["formula"] == "ochiai"
    assert details["previous"]["top_n"] == 10
    assert details["requested"]["formula"] == "dstar2"
    assert details["requested"]["formula_explicit"] is True
    assert details["cache_path"].endswith(
        f"run_{_RUN_ID}/localization_findings.json"
    )


def test_localization_latest_no_warning_on_match(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_cache_path: Path,
) -> None:
    """When ``latest`` returns a finding whose flags match the user's
    explicit request, no re-derive triggered; no warning. Cache file
    untouched."""

    matching = _make_finding(formula="tarantula", top_n=5)
    monkeypatch.setattr(
        localization_workflow,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: matching,
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="tarantula", top_n=5)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    assert stub_cache_path.exists()


def test_localization_latest_no_warning_when_outcome_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_cache_path: Path,
) -> None:
    """``latest`` against an empty store: ``LocalizationUnavailable`` —
    no cache to invalidate, no re-derive, no warning even when the user
    passed explicit flags."""

    monkeypatch.setattr(
        localization_workflow,
        "derive_latest_localization",
        lambda _store, *, formula, top_n: LocalizationUnavailable(
            run_reference=None,
            reason=REASON_NO_RUN_EVIDENCE,
            detail="empty store",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="dstar2", top_n=3)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    assert stub_cache_path.exists()


# ---------------------------------------------------------------------------
# Defect 7 fix (2026-06-08) — formula noop in ``failure_proximity`` mode
# also applies to the ``latest`` verb (same shared flag-override-policy
# carve-out in ``orchestration/workflows/localization.py``). The run-verb's
# ``test_localization.py`` carries the full 5-case matrix; this single
# mirror test pins the wire-level behavior on the latest verb so the
# carve-out can't regress on one verb without breaking the other.
# ---------------------------------------------------------------------------


_NOOP_WARN_CODE = "localization-formula-noop-in-mode"


def test_localization_latest_failure_proximity_non_default_formula_emits_noop_warning_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_cache_path: Path,
) -> None:
    """``latest`` resolves to a failure_proximity run; user passes
    ``--formula=dstar2``. The placeholder ``formula="ochiai"`` would
    pre-Defect-7 trigger an infinite cache-rederive loop. Post-Defect-7
    the carve-out emits a single ``localization-formula-noop-in-mode``
    warning and skips the re-derive (no second engine call, cache file
    untouched). Same load-bearing assertion shape as
    ``test_localization.py::...failure_proximity_non_default_formula_
    emits_noop_warning_once`` but exercising the latest verb path."""

    finding = _make_finding(formula="ochiai", top_n=10, mode="failure_proximity")
    latest_calls: list[int] = []
    fresh_calls: list[int] = []

    def fake_latest(_store: Any, *, formula: str, top_n: int) -> LocalizationFinding:
        latest_calls.append(1)
        return finding

    def fake_fresh(*_a: Any, **_k: Any) -> LocalizationFinding:
        fresh_calls.append(1)
        return finding

    monkeypatch.setattr(localization_workflow, "derive_latest_localization", fake_latest)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_fresh)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_latest(formula="dstar2")
    assert exc_info.value.code == 0

    # latest derive called once; fresh-derive NEVER called (no re-derive).
    assert len(latest_calls) == 1
    assert len(fresh_calls) == 0
    # Cache file untouched.
    assert stub_cache_path.exists()

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["mode"] == "failure_proximity"
    assert outcome["formula"] == "ochiai"

    warnings = payload["warnings"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == _NOOP_WARN_CODE
    assert warning["details"]["requested_formula"] == "dstar2"
    assert warning["details"]["returned_formula"] == "ochiai"
    assert warning["details"]["mode"] == "failure_proximity"
