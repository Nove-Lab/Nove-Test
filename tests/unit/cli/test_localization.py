"""Unit tests for the `novetest localization <run_id>` CLI handler.

Covers the orchestration-to-envelope projection: store lookup → flag
validation → run_reference lookup → engine call → envelope projection.
The Localization engine seam (``derive_localization_findings``) and
Memory's ``list_run_history`` are monkeypatched at the ``cli.app`` module
so the unit tests never touch the filesystem.

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
) -> LocalizationFinding:
    ref = RunReference(run_id=run_id, created_at=1_700_000_000_000)
    loc = CodeLocation(
        kind="symbol",
        file="src/calc.py",
        symbol="buggy",
        line_range=(4, 5),
        primary_line=5,
        evidence_lines=(5,),
    )
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
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
        mode="sbfl_per_test",
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
        lambda _store: [_make_memory_entry(_RUN_ID)],
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

    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
        app_module,
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

    monkeypatch.setattr(app_module, "list_run_history", lambda _store: [])

    def must_not_be_called(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("derive_localization_findings must not be called")

    monkeypatch.setattr(app_module, "derive_localization_findings", must_not_be_called)

    with pytest.raises(SystemExit) as exc_info:
        app_module.localization_run("fake-run-id")
    assert exc_info.value.code == 2

    payload = _captured_envelope(capsys)
    assert payload["ok"] is False
    assert payload["command"] == "localization"
    assert payload["errors"][0]["code"] == "not-found"


# ---------------------------------------------------------------------------
# Case (4): Tombstoned run → run_not_analyzable, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_tombstoned_run_surfaces_run_not_analyzable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A tombstoned run: the engine returns ``LocalizationUnavailable``
    with ``reason=="run_not_analyzable"``. The CLI projects it as
    ``kind=="unavailable"``, ``ok: true``, exit 0."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        app_module,
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
# Case (5): No failed tests → no_failed_tests, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_no_failed_tests_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A run with no failed tests: the engine returns ``no_failed_tests``."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        app_module,
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
# Case (6): Coverage missing → no_coverage, ok=true, exit 0
# ---------------------------------------------------------------------------


def test_localization_run_no_coverage_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    force_json_mode: None,
    stub_store: object,
    stub_history: None,
) -> None:
    """A run without per-test coverage: the engine returns ``no_coverage``."""

    ref = RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)
    monkeypatch.setattr(
        app_module,
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

    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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

    monkeypatch.setattr(app_module, "derive_localization_findings", must_not_be_called)

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

    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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

    monkeypatch.setattr(app_module, "derive_localization_findings", must_not_be_called)

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
# Test pattern: monkeypatch ``derive_localization_findings`` with a
# side-effecting callable that returns the CACHED finding on first call,
# the FRESH finding on subsequent calls. The CLI's first call hits the
# cached payload; ``_rederive_if_cache_overrode_flags`` then unlinks the
# (fake) cache path and re-calls the engine — that second call returns the
# fresh finding. ``localization_findings_path`` is monkeypatched onto a
# real ``tmp_path`` file so ``.unlink(missing_ok=True)`` is a real no-op.
# ---------------------------------------------------------------------------


_CACHE_WARN_CODE = "localization-cache-rederived"


@pytest.fixture
def stub_cache_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Wire ``app_module.localization_findings_path`` onto a tmp_path file.

    The post-Defect-5 invalidation calls ``localization_findings_path(...).
    unlink(missing_ok=True)``. Unit tests don't have a real store on disk,
    so this fixture redirects the path computation onto a real tmp file
    that ``unlink`` can safely operate against (idempotently after the
    first call).
    """
    from pathlib import Path as _Path

    fake_cache = tmp_path / "fake_localization_findings.json"
    fake_cache.touch()
    monkeypatch.setattr(
        app_module,
        "localization_findings_path",
        lambda *_a, **_k: fake_cache,
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
    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
    monkeypatch.setattr(app_module, "derive_localization_findings", fake_derive)

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
        app_module,
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
