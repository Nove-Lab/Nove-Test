"""Unit tests for the `novetest localization <run_id>` CLI handler.

Covers the orchestration-to-envelope projection: store lookup → flag
validation → run_reference lookup → workflow call → envelope projection.
The Localization engine seam (``derive_localization_findings``) is
monkeypatched at the ``orchestration/workflows/localization.py`` module
(where the flag-override policy calls it since W2/S22); Memory's
``list_run_history`` is monkeypatched at the ``cli.app`` module (the
run_id lookup stayed transport-side). The unit tests never touch the
filesystem.

NOTE: These tests require ``localization_run`` to be registered in
``cli/app.py`` as ``localization_app.default``. If the handler is not yet
present the tests will fail with ``AttributeError`` — add the handler per
the Phase-4 CLI task brief before running.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import OutputMode
from novetest.localization import (
    DEFAULT_FORMULA,
    DEFAULT_TOP_N,
    FORMULAS,
    LocalizationFinding,
    LocalizationUnavailable,
)
from novetest.localization.results import (
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_COVERAGE,
    REASON_NO_FAILED_TESTS,
    REASON_RUN_NOT_ANALYZABLE,
)
from novetest.models import MemoryEntry, RunRecord, RunReference
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.orchestration.workflows import localization as localization_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUN_ID = "01LOCRUNLOCRUNLOCRUNLOCRUNS"
_OTHER_ID = "01OTHEROTHEROTHEROTHEROTHE"


def _make_memory_entry(run_id: str, *, created_at: int = 1_700_000_000_000) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=created_at,
        completed_at=created_at + 1_000,
        summary_counts={"failed": 1, "passed": 2, "total": 3},
    )
    return MemoryEntry(entry_id=run_id, run_record=record, stored_at=created_at + 2_000)


def _make_finding(
    run_id: str = _RUN_ID,
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    derived_at: int = 9_000,
    mode: str = "sbfl_per_test",
) -> LocalizationFinding:
    """Construct a deterministic ``LocalizationFinding`` for unit tests.

    The ``mode`` parameter lets a test exercise mode-aware orchestration
    branches (Defect 7 — formula noop in ``failure_proximity``). When
    ``mode == "failure_proximity"`` the per-mode constraints from
    ``localization/failure_proximity.py`` are honored: ``confidence`` is
    ``"low"``, the entry's ``code_location.kind`` is ``"file"``,
    ``alternate_scores`` is empty (no SBFL formulas computed), and
    ``alternate_scores_available`` is the empty tuple. Otherwise the
    SBFL-mode shape (per-test, with alternate formulas populated) is
    returned. Both shapes pass the model's closed-enum validators.
    """
    ref = RunReference(run_id=run_id, created_at=1_700_000_000_000)
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    if mode == "failure_proximity":
        # File-level entry (kind="file"), empty alternates — matches the
        # shape ``derive_failure_proximity`` actually emits.
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
            metadata={},
        )
    # SBFL shape — symbol-level entry, populated alternate scores.
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
        metadata={},
    )


@pytest.fixture
def force_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_module, "_active_mode", OutputMode.JSON)


@pytest.fixture
def stub_store(monkeypatch: pytest.MonkeyPatch) -> object:
    sentinel = object()
    monkeypatch.setattr(app_module, "_require_store", lambda _cmd: sentinel)
    return sentinel


@pytest.fixture
def stub_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Return a single known entry so ``_resolve_run_reference`` succeeds."""
    monkeypatch.setattr(
        app_module,
        "list_run_history",
        lambda _store, skipped=None: [_make_memory_entry(_RUN_ID)],
    )


def _captured_envelope(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    out = capsys.readouterr().out
    assert out, "expected the handler to emit an envelope to stdout"
    return json.loads(out)


# ---------------------------------------------------------------------------
# Case (1): Happy path — fact-set projection, schema_version absent
# ---------------------------------------------------------------------------


def test_localization_run_emits_fact_set_envelope(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Happy path: ``derive_localization_findings`` returns a real finding.
    The envelope is ``ok: true``, exit 0; ``data.localization_outcome.kind
    == "fact-set"``; schema_version is absent from the block; entries[0].rank
    == 1."""

    finding = _make_finding()

    def fake_derive(
        _store: Any, ref: RunReference, *, top_n: int = 10, formula: str = "ochiai"
    ) -> LocalizationFinding:
        return finding

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["command"] == "localization"
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    # schema_version must be stripped on the wire.
    assert "schema_version" not in outcome
    # formula key is "formula", NOT "primary_formula".
    assert "formula" in outcome
    assert "primary_formula" not in outcome
    assert outcome["formula"] == "ochiai"
    entries = outcome["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    assert entries[0]["rank"] == 1
    # evidence_lines lives inside code_location, NOT as a top-level entry key.
    assert "evidence_lines" not in entries[0]
    assert "evidence_lines" in entries[0]["code_location"]
    # schema_version must not appear on individual entries either.
    assert "schema_version" not in entries[0]


# ---------------------------------------------------------------------------
# Case (2): Cache-hit preserves derived_at — two calls produce same value
# ---------------------------------------------------------------------------


def test_localization_run_cache_hit_preserves_derived_at(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """Two CLI calls projecting the same stubbed finding → identical
    ``derived_at`` on the wire (idempotent cache-hit semantics)."""

    fixed_finding = _make_finding(derived_at=12345)
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: fixed_finding,
    )

    derived_values: list[int] = []
    for _ in range(2):
        with pytest.raises(SystemExit):
            app_module.localization_run(_RUN_ID)
        payload = _captured_envelope(capsys)
        derived_values.append(payload["data"]["localization_outcome"]["derived_at"])
    assert derived_values == [12345, 12345]


# ---------------------------------------------------------------------------
# Case (3): Fake run_id → not-found, exit 2
# ---------------------------------------------------------------------------


def test_localization_run_fake_run_id_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
) -> None:
    """A fake run_id short-circuits at ``_resolve_run_reference`` BEFORE the
    engine call fires — ``not-found`` envelope, exit 2."""

    monkeypatch.setattr(app_module, "list_run_history", lambda _store, skipped=None: [])

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("derive_localization_findings must not be called")

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run("fake-run-id")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "localization"
    assert payload["errors"][0]["code"] == "not-found"


# ---------------------------------------------------------------------------
# Case (4): Tombstoned run → run-not-analyzable, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_tombstoned_run_surfaces_run_not_analyzable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A tombstoned run: the engine returns ``LocalizationUnavailable``
    with ``reason=="run-not-analyzable"``. The CLI projects it as
    ``kind=="unavailable"``, ``ok: true``, exit 0."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: LocalizationUnavailable(
            run_reference=ref,
            reason=REASON_RUN_NOT_ANALYZABLE,
            detail="run is tombstoned",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_RUN_NOT_ANALYZABLE


# ---------------------------------------------------------------------------
# Case (5): No failed tests → no-failed-tests, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_no_failed_tests_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A run with no failed tests: the engine returns ``no-failed-tests``."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: LocalizationUnavailable(
            run_reference=ref,
            reason=REASON_NO_FAILED_TESTS,
            detail="0 failed tests",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_FAILED_TESTS


# ---------------------------------------------------------------------------
# Case (6): Coverage missing → no-coverage, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_no_coverage_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A run without per-test coverage: the engine returns ``no-coverage``."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: LocalizationUnavailable(
            run_reference=ref,
            reason=REASON_NO_COVERAGE,
            detail="no per-test coverage facts",
        ),
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["ok"] is True
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert outcome["reason"] == REASON_NO_COVERAGE


# ---------------------------------------------------------------------------
# Case (7): --formula op2 → engine receives formula="op2", projection reflects it
# ---------------------------------------------------------------------------


def test_localization_run_formula_flag_forwarded_to_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """``--formula op2`` is forwarded to the engine AS ``formula="op2"``
    and the projected block carries ``formula=="op2"`` with
    ``alternate_scores_available`` containing ``"ochiai"`` (not ``"op2"``)."""

    seen_formula: list[str] = []

    def fake_derive(
        _store: Any, ref: RunReference, *, top_n: int, formula: str
    ) -> LocalizationFinding:
        seen_formula.append(formula)
        return _make_finding(formula=formula)

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="op2")
    assert exc_info.value.code == 0

    assert seen_formula == ["op2"], "engine must receive formula='op2'"

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "fact-set"
    assert outcome["formula"] == "op2"
    alt = outcome["alternate_scores_available"]
    assert "ochiai" in alt, "ochiai must be in alternate_scores_available"
    assert "op2" not in alt, "op2 (the selected formula) must not be in alternates"


# ---------------------------------------------------------------------------
# Case (8): --formula bogus → invalid-flag, exit 2, engine NOT called
# ---------------------------------------------------------------------------


def test_localization_run_bogus_formula_returns_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """An unknown formula short-circuits BEFORE any engine call — emits
    ``code: "invalid-flag"`` and exits 2."""

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("derive_localization_findings called with bogus formula")

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="bogus")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid-flag"


# ---------------------------------------------------------------------------
# Case (9): --top-n 3 → engine receives top_n=3
# ---------------------------------------------------------------------------


def test_localization_run_top_n_flag_forwarded_to_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """``--top-n 3`` is forwarded to the engine AS ``top_n=3``."""

    seen_top_n: list[int] = []

    def fake_derive(
        _store: Any, ref: RunReference, *, top_n: int, formula: str
    ) -> LocalizationFinding:
        seen_top_n.append(top_n)
        return _make_finding(top_n=top_n)

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, top_n=3)
    assert exc_info.value.code == 0

    assert seen_top_n == [3], "engine must receive top_n=3"


# ---------------------------------------------------------------------------
# Case (10): --top-n 0 → invalid-flag, exit 2
# ---------------------------------------------------------------------------


def test_localization_run_top_n_zero_returns_invalid_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """``--top-n 0`` (or any non-positive value) short-circuits with
    ``code: "invalid-flag"``, exit 2, before any engine call."""

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("derive_localization_findings called with top_n=0")

    monkeypatch.setattr(localization_workflow, "derive_localization_findings", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, top_n=0)
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] == "invalid-flag"


# ---------------------------------------------------------------------------
# Cache-rederived warning suite (Defect 5 fix, 2026-06-01).
#
# Pre-Defect-5 the CLI emitted a ``localization-cache-args-ignored`` warning
# and returned the stale cached finding when explicit ``--formula`` /
# ``--top-n`` differed from the cached values. Post-Defect-5 the same
# condition INVALIDATES the cache, re-invokes ``derive_localization_findings``
# at the requested flags, and surfaces a ``localization-cache-rederived``
# warning carrying the previous (formula, top_n) for audit.
#
# Test pattern: monkeypatch ``derive_localization_findings`` (at the
# workflow module, where the policy lives since W2/S22) with a
# side-effecting callable that returns the CACHED finding on first call,
# the FRESH finding on subsequent calls. The workflow's first call hits
# the cached payload; the flag-override policy then invalidates the
# (fake) cache and re-calls the engine — that second call returns the
# fresh finding. ``invalidate_localization_findings`` is monkeypatched
# onto a real ``tmp_path`` file unlink so the invalidation side effect
# stays observable (same missing_ok semantics as the real public API).
# ---------------------------------------------------------------------------


_CACHE_WARN_CODE = "localization-cache-rederived"


@pytest.fixture
def stub_cache_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Wire the workflow's ``invalidate_localization_findings`` onto a tmp file.

    The post-Defect-5 invalidation calls the Localization engine's public
    ``invalidate_localization_findings(store, run_id)`` (missing-cache is
    a no-op). Unit tests don't have a real store on disk, so this fixture
    redirects the invalidation onto a real tmp file unlink
    (``missing_ok=True`` — idempotent after the first call) whose
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


def _two_phase_derive(
    cached: LocalizationFinding,
    fresh: LocalizationFinding,
) -> Callable[..., LocalizationFinding]:
    """Return a callable that yields ``cached`` on call 1, ``fresh`` thereafter.

    Mirrors the engine's cache-aware behavior under test: the first call
    serves from cache (stale args baked in), the orchestration layer
    invalidates the cache file, and the second call runs a fresh derive
    at the user's requested flags. ``call_count`` is tracked on the
    returned callable's ``__closure__`` for assertion.
    """
    calls: list[int] = []

    def _derive(*_a: Any, **_k: Any) -> LocalizationFinding:
        calls.append(1)
        return cached if len(calls) == 1 else fresh

    _derive.calls = calls  # type: ignore[attr-defined]
    return _derive


def test_localization_run_rederives_on_formula_only_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (a) — cache stored ``ochiai``; user passes ``--formula=dstar2``
    (only ``--formula`` explicit). Post-Defect-5: cache file is unlinked,
    engine re-invoked, fresh ``dstar2`` finding returned. One
    ``localization-cache-rederived`` warning with ``previous`` carrying
    ``ochiai`` / ``top_n=10`` and ``requested`` carrying ``dstar2`` /
    ``top_n=10`` (defaulted)."""

    cached_finding = _make_finding(formula="ochiai", top_n=10)
    fresh_finding = _make_finding(formula="dstar2", top_n=10)
    fake_derive = _two_phase_derive(cached_finding, fresh_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="dstar2")
    assert exc_info.value.code == 0

    # Engine called twice — once for cache hit, once for fresh derive.
    assert len(fake_derive.calls) == 2  # type: ignore[attr-defined]
    # Cache file is gone after invalidation (idempotent unlink).
    assert not stub_cache_path.exists()

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    # Fresh finding's args reflect the user's request, not the cached state.
    assert outcome["formula"] == "dstar2"
    assert outcome["top_n"] == 10

    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == _CACHE_WARN_CODE
    assert "--formula='dstar2'" in warning["message"]
    assert "--formula='ochiai'" in warning["message"]
    details = warning["details"]
    assert details["previous"]["formula"] == "ochiai"
    assert details["previous"]["top_n"] == 10
    assert details["requested"]["formula"] == "dstar2"
    assert details["requested"]["formula_explicit"] is True
    assert details["requested"]["top_n"] == DEFAULT_TOP_N
    assert details["requested"]["top_n_explicit"] is False
    assert details["cache_path"].endswith(
        f"run_{_RUN_ID}/localization_findings.json"
    )


def test_localization_run_rederives_on_top_n_only_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (b) — cache stored ``top_n=10``; user passes ``--top-n=5``
    (only ``--top-n`` explicit, ``--formula`` defaulted). Re-derive at
    ``top_n=5`` returns fresh finding; warning fires with
    ``top_n_explicit=True`` / ``formula_explicit=False``; ``requested.
    formula`` field carries the Cyclopts default."""

    cached_finding = _make_finding(formula="ochiai", top_n=10)
    fresh_finding = _make_finding(formula="ochiai", top_n=5)
    fake_derive = _two_phase_derive(cached_finding, fresh_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, top_n=5)
    assert exc_info.value.code == 0

    assert len(fake_derive.calls) == 2  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["top_n"] == 5
    assert outcome["formula"] == "ochiai"

    warnings = payload["warnings"]
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == _CACHE_WARN_CODE
    assert "--top-n=5" in warning["message"]
    assert "--top-n=10" in warning["message"]
    details = warning["details"]
    assert details["previous"]["top_n"] == 10
    assert details["requested"]["top_n"] == 5
    assert details["requested"]["top_n_explicit"] is True
    assert details["requested"]["formula"] == DEFAULT_FORMULA
    assert details["requested"]["formula_explicit"] is False


def test_localization_run_rederives_on_both_flag_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (c) — both ``--formula`` and ``--top-n`` differ from cache.
    Single re-derive + warning emitted with both ``_explicit`` flags
    True; ``previous`` and ``requested`` both populated."""

    cached_finding = _make_finding(formula="ochiai", top_n=10)
    fresh_finding = _make_finding(formula="op2", top_n=3)
    fake_derive = _two_phase_derive(cached_finding, fresh_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="op2", top_n=3)
    assert exc_info.value.code == 0

    assert len(fake_derive.calls) == 2  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    assert outcome["formula"] == "op2"
    assert outcome["top_n"] == 3

    warnings = payload["warnings"]
    assert len(warnings) == 1
    warning = warnings[0]
    details = warning["details"]
    assert details["previous"]["formula"] == "ochiai"
    assert details["previous"]["top_n"] == 10
    assert details["requested"]["formula"] == "op2"
    assert details["requested"]["formula_explicit"] is True
    assert details["requested"]["top_n"] == 3
    assert details["requested"]["top_n_explicit"] is True


def test_localization_run_no_warning_when_request_matches_cache(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (d) — user passes ``--formula=dstar2 --top-n=5`` and the
    returned finding also reports ``dstar2`` / ``5`` (cache match, OR
    fresh derive). No re-derive, no warning. Regression-pin for the
    cache-hit-no-mismatch path (engine called exactly once)."""

    matching_finding = _make_finding(formula="dstar2", top_n=5)
    fake_derive = _two_phase_derive(matching_finding, matching_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="dstar2", top_n=5)
    assert exc_info.value.code == 0

    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    # Cache file was NOT unlinked.
    assert stub_cache_path.exists()


def test_localization_run_no_warning_when_flags_omitted_despite_cache_diff(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (e) — cache stored ``dstar2 / top_n=3`` but the user passes
    NEITHER flag (both default in effect). Per brief scope §1, a
    defaulted flag never triggers re-derive even when it differs from
    the cache. Cache returned verbatim; no warning. Regression-pin for
    the "no explicit signal → keep cache" path."""

    cached_finding = _make_finding(formula="dstar2", top_n=3)
    fake_derive = _two_phase_derive(cached_finding, cached_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    # User saw the cached finding verbatim (no re-derive).
    outcome = payload["data"]["localization_outcome"]
    assert outcome["formula"] == "dstar2"
    assert outcome["top_n"] == 3
    assert stub_cache_path.exists()


def test_localization_run_no_warning_when_outcome_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Case (f) — engine returns ``LocalizationUnavailable``. No cache to
    invalidate; pass through unchanged. No warning even when the user
    passed explicit flags."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    unavailable = LocalizationUnavailable(
        run_reference=ref,
        reason=REASON_NO_FAILED_TESTS,
        detail="no failures",
    )
    monkeypatch.setattr(
        localization_workflow,
        "derive_localization_findings",
        lambda *_a, **_k: unavailable,
    )

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="dstar2", top_n=5)
    assert exc_info.value.code == 0

    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    outcome = payload["data"]["localization_outcome"]
    assert outcome["kind"] == "unavailable"
    assert stub_cache_path.exists()


# ---------------------------------------------------------------------------
# Defect 7 fix (2026-06-08) — ``failure_proximity`` mode formula-noop suite
#
# Background: ``failure_proximity`` is a heuristic frequency-count mode
# that runs when no coverage data is available (``CoverageFactSet``
# unavailable). It is NOT an SBFL formula — it pins
# ``finding.formula = "ochiai"`` as a structural placeholder regardless
# of ``--formula`` input (see ``localization/failure_proximity.py::
# _PLACEHOLDER_FORMULA``). Pre-Defect-7, the cache-rederived warning
# path treated this placeholder mismatch as a legitimate cache hit-vs-
# explicit-flags collision and entered an infinite loop: every retry
# unlinked the cache, re-derived, got the same placeholder back, and
# emitted the same warning. Post-Defect-7, the flag-override policy
# (now in ``orchestration/workflows/localization.py``) recognizes the
# placeholder scenario and reports a single
# ``localization-formula-noop-in-mode`` warning (via the workflow's
# ``FormulaNoopAudit``) WITHOUT triggering a re-derive — breaking the loop and
# giving AI consumers a distinct "structural noop, do not retry"
# signal instead of "fixable misconfig, retry".
#
# Test matrix (per the 2026-06-08 task brief §"Test 매트릭스"):
#   1. failure_proximity + default formula → no warning, no mismatch
#   2. failure_proximity + non-default formula → noop warning 1, no loop
#   3. sbfl mode + default formula → unchanged baseline
#   4. sbfl mode + non-default formula → unchanged cache-rederive path
#   5. failure_proximity + non-default formula cache state pre/post
#      assertions (derives called exactly once, cache file still
#      present — explicit proof of the no-loop guarantee).
# ---------------------------------------------------------------------------


_NOOP_WARN_CODE = "localization-formula-noop-in-mode"


def test_localization_run_failure_proximity_default_formula_no_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Matrix #1: ``failure_proximity`` + no ``--formula`` flag (default
    ``"ochiai"``). The placeholder matches the resolved default so the
    ``formula_explicit`` gate is False; ``formula_mismatch`` cannot
    fire. Engine called exactly once, no warning, cache file untouched.

    This is the regression-pin for the "happy path" of failure_proximity:
    a user who doesn't pass ``--formula`` sees zero noise."""

    finding = _make_finding(formula="ochiai", top_n=10, mode="failure_proximity")
    fake_derive = _two_phase_derive(finding, finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    # Single derive call — no re-derive triggered.
    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    outcome = payload["data"]["localization_outcome"]
    assert outcome["mode"] == "failure_proximity"
    assert outcome["formula"] == "ochiai"
    # Cache file was NOT unlinked.
    assert stub_cache_path.exists()


def test_localization_run_failure_proximity_non_default_formula_emits_noop_warning_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Matrix #2: ``failure_proximity`` + ``--formula=op2`` (explicit,
    non-default). The engine pins ``formula="ochiai"`` as a placeholder
    regardless of input, so ``resolved_formula="op2"`` mismatches the
    returned ``cached_formula="ochiai"``. The new Defect 7 carve-out
    recognizes this as structural-noop-in-mode rather than a fixable
    cache-stale-vs-flag collision: re-derive is SKIPPED, and a single
    ``localization-formula-noop-in-mode`` warning is emitted with
    details ``{requested_formula, returned_formula, mode}``.

    Pre-Defect-7 the same input triggered a ``localization-cache-
    rederived`` warning AND a second derive call — the start of the
    warning loop. This test pins the new non-loop behavior."""

    finding = _make_finding(formula="ochiai", top_n=10, mode="failure_proximity")
    fake_derive = _two_phase_derive(finding, finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="op2")
    assert exc_info.value.code == 0

    # The crucial assertion: engine called EXACTLY ONCE. Pre-Defect-7 this
    # would be 2 (initial + post-invalidation re-derive). The single-call
    # invariant is the wire-level proof that no re-derive happened.
    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    # Cache file untouched (no unlink).
    assert stub_cache_path.exists()

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    # Engine's placeholder is preserved — user sees what the engine
    # actually computed, not a fictional ``formula="op2"`` finding.
    assert outcome["mode"] == "failure_proximity"
    assert outcome["formula"] == "ochiai"

    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    # The brief's DoD #1: noop warning code emitted EXACTLY ONCE per
    # invocation.
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning["code"] == _NOOP_WARN_CODE
    # Message names both the requested formula and the placeholder + mode
    # so an AI consumer reading the message alone (without parsing
    # details) sees the noop nature.
    assert "op2" in warning["message"]
    assert "ochiai" in warning["message"]
    assert "failure_proximity" in warning["message"]
    details = warning["details"]
    assert details["requested_formula"] == "op2"
    assert details["returned_formula"] == "ochiai"
    assert details["mode"] == "failure_proximity"
    # No stale ``previous`` / ``requested`` / ``cache_path`` fields —
    # this is the new structural-noop shape, NOT the cache-rederived
    # shape. Asserting absence pins the schema decision.
    assert "previous" not in details
    assert "requested" not in details
    assert "cache_path" not in details


def test_localization_run_sbfl_default_formula_unchanged_behavior(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Matrix #3: ``sbfl_per_test`` mode + no ``--formula`` flag. The
    Defect 7 carve-out MUST NOT change behavior here — engine called
    exactly once (whatever the cached formula is matches the resolved
    default since the user didn't pass it explicitly). Regression-pin
    that the new mode-aware branch only activates for failure_proximity.

    (This mirrors the pre-existing "no warning when flags omitted
    despite cache diff" assertion above but explicitly pins the
    ``mode = "sbfl_per_test"`` axis.)"""

    cached_finding = _make_finding(
        formula="dstar2", top_n=7, mode="sbfl_per_test"
    )
    fake_derive = _two_phase_derive(cached_finding, cached_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID)
    assert exc_info.value.code == 0

    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    payload = _captured_envelope(capsys)
    assert payload["warnings"] == []
    outcome = payload["data"]["localization_outcome"]
    assert outcome["mode"] == "sbfl_per_test"
    assert outcome["formula"] == "dstar2"
    assert stub_cache_path.exists()


def test_localization_run_sbfl_non_default_formula_unchanged_behavior(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Matrix #4: ``sbfl_per_test`` mode + ``--formula=op2`` explicit. The
    Defect 7 carve-out MUST NOT change behavior here — this is the
    existing cache-rederived path: engine called twice, cache unlinked,
    fresh finding returned at ``op2``, single
    ``localization-cache-rederived`` warning emitted (NOT the new noop
    warning).

    Regression-pin that the noop carve-out only fires when
    ``outcome.mode == "failure_proximity"``."""

    cached_finding = _make_finding(formula="ochiai", top_n=10, mode="sbfl_per_test")
    fresh_finding = _make_finding(formula="op2", top_n=10, mode="sbfl_per_test")
    fake_derive = _two_phase_derive(cached_finding, fresh_finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="op2")
    assert exc_info.value.code == 0

    # Two derive calls — cache-rederive flow ran end-to-end.
    assert len(fake_derive.calls) == 2  # type: ignore[attr-defined]
    # Cache file was unlinked (re-derive did happen).
    assert not stub_cache_path.exists()

    payload = _captured_envelope(capsys)
    outcome = payload["data"]["localization_outcome"]
    # Fresh finding's formula reflects the user's request — SBFL can
    # actually honor it.
    assert outcome["mode"] == "sbfl_per_test"
    assert outcome["formula"] == "op2"

    warnings = payload["warnings"]
    assert len(warnings) == 1
    warning = warnings[0]
    # Pre-existing cache-rederived warning, NOT the new noop warning.
    assert warning["code"] == _CACHE_WARN_CODE
    # Defense-in-depth: assert the noop warning code is NOT present so
    # the carve-out can't silently fire on the SBFL path.
    assert all(w["code"] != _NOOP_WARN_CODE for w in warnings)


def test_localization_run_failure_proximity_non_default_formula_no_rederive_loop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
    stub_cache_path: Path,
) -> None:
    """Matrix #5: dedicated no-loop assertion. Pre-Defect-7 the infinite-
    loop reproduction was: every retry triggered ``unlink + re-derive +
    re-warn`` because the re-derive returned the same placeholder.

    The unit-test seam can't loop the CLI (each invocation is independent),
    but we CAN pin the load-bearing single-invocation invariant: within
    one ``localization_run`` call, ``derive_localization_findings`` is
    invoked EXACTLY ONCE (the first call returns the placeholder finding;
    the carve-out short-circuits before any re-derive). This proves the
    "no infinite loop" property at the load-bearing seam.

    The cache file's pre-state is "exists" (the stub fixture creates it);
    the cache file's post-state MUST also be "exists" (no unlink ran).
    This pre/post pair is the wire-level evidence requested in the
    brief's matrix item #5 ("cache state pre/post 호출 검증")."""

    # Pre-state assertion — fixture creates the cache file.
    assert stub_cache_path.exists()

    finding = _make_finding(formula="ochiai", top_n=10, mode="failure_proximity")
    # Sentinel: if a re-derive ever happens, we'd see calls.count > 1.
    # We make the "fresh" return identical to "cached" so a buggy
    # implementation that calls twice would still pass the formula
    # assertions but FAIL the call-count + cache-existence checks below.
    fake_derive = _two_phase_derive(finding, finding)
    monkeypatch.setattr(localization_workflow, "derive_localization_findings", fake_derive)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run(_RUN_ID, formula="dstar2")
    assert exc_info.value.code == 0

    # Load-bearing assertion #1: exactly one engine call.
    assert len(fake_derive.calls) == 1  # type: ignore[attr-defined]
    # Load-bearing assertion #2: cache file still present (no unlink).
    assert stub_cache_path.exists()

    payload = _captured_envelope(capsys)
    # Single noop warning — same shape as matrix #2 but the focal point
    # here is the call-count + cache-existence invariant above.
    warnings = payload["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["code"] == _NOOP_WARN_CODE
