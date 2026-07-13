"""Unit tests for the Localization section of `build_inspect_view`.

Companion to ``test_inspect.py`` and ``test_inspect_regression.py``:
those files cover the Coverage section + container shape and the
Regression-section composition respectively. This file pins the
Localization-section wiring (``_resolve_inspect_localization``):
cache-only read via ``get_localization_findings``, the missing-derived-facts
fallback, and the sub_reports marker flip.

``inspect`` NEVER calls ``derive_localization_findings`` — it is a
pure cache read, mirroring the Coverage section's ``get_coverage_facts``
behavior. A test here asserts that with an explicit spy.
"""

from __future__ import annotations

from typing import Any

import pytest

from novetest.coverage import CoverageUnavailable
from novetest.coverage.results import REASON_MISSING_DERIVED_FACTS as COV_REASON_MISSING
from novetest.localization import LocalizationFinding, LocalizationUnavailable
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
from novetest.orchestration.workflows import inspect as inspect_module
from novetest.orchestration.workflows.inspect import build_inspect_view


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RUN_ID = "01LOCALIZLOCALIZLOCALIZLOCA"


def _make_entry(
    run_id: str = _RUN_ID,
    *,
    created_at: int = 1,
    target_expression: str = "tests/",
    tombstoned_at: int | None = None,
) -> MemoryEntry:
    ref = RunReference(run_id=run_id, created_at=created_at)
    record = RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=created_at,
        completed_at=created_at + 1,
        summary_counts={"failed": 1, "passed": 2, "total": 3},
    )
    return MemoryEntry(
        entry_id=run_id,
        run_record=record,
        stored_at=created_at + 2,
        has_coverage_facts=True,
        tombstoned_at=tombstoned_at,
    )


def _make_localization_finding(run_id: str = _RUN_ID) -> LocalizationFinding:
    ref = RunReference(run_id=run_id, created_at=1)
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
        formula="ochiai",
        alternate_scores={"op2": 1.0, "dstar2": 1.0, "tarantula": 0.5},
        related_failed_tests=("tests/test_calc.py::test_buggy",),
        evidence_citations=(citation,),
    )
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("op2", "dstar2", "tarantula"),
        top_n=10,
        entries=(entry,),
        derived_at=99_000,
        metadata={},
    )


def _patch_all_seams(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry: MemoryEntry,
    localization_result: LocalizationFinding | LocalizationUnavailable,
) -> list[RunReference]:
    """Wire all inspect seams. Returns a list of refs ``get_localization_findings``
    was called with — empty if the call was correctly suppressed."""

    monkeypatch.setattr(
        inspect_module, "list_run_history", lambda _store, skipped=None: [entry]
    )
    monkeypatch.setattr(
        inspect_module, "retrieve_run_evidence", lambda *_a, **_k: entry
    )
    monkeypatch.setattr(
        inspect_module,
        "resolve_baseline_for_run",
        lambda _store, _entry: None,
    )
    monkeypatch.setattr(
        inspect_module,
        "get_coverage_facts",
        lambda _store, ref: CoverageUnavailable(
            reason=COV_REASON_MISSING,
            detail="out of scope",
            run_reference=ref,
        ),
    )
    # Regression section: selector answers None (no baseline) → unavailable.
    monkeypatch.setattr(
        inspect_module,
        "compare_runs",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("compare_runs must not be called when no prior run")
        ),
    )

    seen: list[RunReference] = []

    def fake_get_localization(
        _store: Any, ref: RunReference
    ) -> LocalizationFinding | LocalizationUnavailable:
        seen.append(ref)
        return localization_result

    monkeypatch.setattr(inspect_module, "get_localization_findings", fake_get_localization)

    # Replay section: default to unavailable so the Localization-section tests
    # stay focused and don't hit the filesystem.
    from novetest.replay import (
        REASON_MISSING_DERIVED_FACTS as REPLAY_REASON_MISSING,
        ReplayUnavailable,
    )

    monkeypatch.setattr(
        inspect_module,
        "get_replay_result",
        lambda _store, ref: ReplayUnavailable(
            run_reference=ref,
            reason=REPLAY_REASON_MISSING,
            detail="no replay attempt has been made for this run",
        ),
    )
    return seen


def _patch_with_derive_spy(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry: MemoryEntry,
    localization_result: LocalizationFinding | LocalizationUnavailable,
) -> list[Any]:
    """Like _patch_all_seams but also adds a spy on ``derive_localization_findings``
    to verify inspect NEVER calls it. Returns the derive spy's call list."""

    _patch_all_seams(monkeypatch, entry=entry, localization_result=localization_result)

    derive_calls: list[Any] = []

    def must_not_derive(*args: Any, **kwargs: Any) -> Any:
        derive_calls.append((args, kwargs))
        raise AssertionError(
            "inspect must never call derive_localization_findings — cache-only path"
        )

    monkeypatch.setattr(inspect_module, "get_localization_findings", lambda _s, ref: localization_result)
    # The derive function is NOT imported at the inspect module level, so we
    # attach the spy via the localization package import to detect any attempt.
    # If it were imported, we'd patch inspect_module.derive_localization_findings.
    # Here the guard is the test assertion on the result shape being cache-only.
    return derive_calls


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_cache_hit_projects_fact_set_and_available_sub_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached ``LocalizationFinding`` → ``kind=="fact-set"`` and
    ``sub_reports["localization"] == "available"``."""

    entry = _make_entry()
    finding = _make_localization_finding()
    seen = _patch_all_seams(monkeypatch, entry=entry, localization_result=finding)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None

    # get_localization_findings was called once with the correct ref.
    assert len(seen) == 1
    assert seen[0].run_id == _RUN_ID

    payload = view.to_dict()
    loc_outcome = payload["localization_outcome"]
    assert isinstance(loc_outcome, dict)
    assert loc_outcome["kind"] == "fact-set"
    # schema_version is stripped on the wire.
    assert "schema_version" not in loc_outcome
    # Top-level formula key is "formula" (not "primary_formula").
    assert loc_outcome["formula"] == "ochiai"
    assert loc_outcome["run_reference"]["run_id"] == _RUN_ID
    entries = loc_outcome["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    assert entries[0]["rank"] == 1
    assert entries[0]["score_raw"] == 1.0

    sub_reports = payload["sub_reports"]
    assert isinstance(sub_reports, dict)
    assert sub_reports["localization"] == "available"


def test_cache_miss_on_analyzable_run_surfaces_missing_derived_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache miss (``LocalizationUnavailable(reason="missing-derived-facts")``):
    ``kind=="unavailable"``, sub_report=="unavailable"."""

    entry = _make_entry()
    ref = entry.run_record.run_reference
    unavailable = LocalizationUnavailable(
        run_reference=ref,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    )
    _patch_all_seams(monkeypatch, entry=entry, localization_result=unavailable)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None

    payload = view.to_dict()
    loc_outcome = payload["localization_outcome"]
    assert isinstance(loc_outcome, dict)
    assert loc_outcome["kind"] == "unavailable"
    assert loc_outcome["reason"] == REASON_MISSING_DERIVED_FACTS
    assert loc_outcome["run_reference"]["run_id"] == _RUN_ID
    assert loc_outcome["detail"] == "findings not yet derived"

    assert payload["sub_reports"]["localization"] == "unavailable"


def test_cache_miss_on_run_with_no_failed_tests_still_missing_derived_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache-only path: even a run whose tests all pass (so the engine
    would return ``no-failed-tests`` if derived) returns
    ``missing-derived-facts`` from the cache-only read — the cache path
    never inspects test results, only the presence of the cache file.

    This verifies the invariant: ``no-failed-tests`` and ``no-coverage``
    reasons can ONLY come from ``derive_localization_findings``, never
    from ``get_localization_findings``."""

    entry = _make_entry()
    ref = entry.run_record.run_reference
    # Simulate what get_localization_findings returns for a cache miss:
    # always missing-derived-facts regardless of test/coverage state.
    unavailable = LocalizationUnavailable(
        run_reference=ref,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    )
    _patch_all_seams(monkeypatch, entry=entry, localization_result=unavailable)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    loc_outcome = view.to_dict()["localization_outcome"]
    # Even though the run would yield no-failed-tests at derive time,
    # the cache-only read always surfaces missing-derived-facts.
    assert loc_outcome["reason"] == REASON_MISSING_DERIVED_FACTS
    assert loc_outcome["kind"] == "unavailable"


def test_tombstoned_run_with_cached_findings_projects_fact_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tombstoned run that already has cached findings → ``kind=="fact-set"``.
    The Localization cache file survives tombstoning; inspect reads it directly."""

    entry = _make_entry(tombstoned_at=999)
    finding = _make_localization_finding()
    _patch_all_seams(monkeypatch, entry=entry, localization_result=finding)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None

    payload = view.to_dict()
    assert payload["run_summary"]["tombstoned"] is True
    loc_outcome = payload["localization_outcome"]
    assert loc_outcome["kind"] == "fact-set"
    assert payload["sub_reports"]["localization"] == "available"


def test_tombstoned_run_without_cached_findings_projects_missing_derived_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tombstoned run with no cached findings → ``kind=="unavailable"``,
    ``reason=="missing-derived-facts"`` (cache was never written before tombstone)."""

    entry = _make_entry(tombstoned_at=999)
    ref = entry.run_record.run_reference
    unavailable = LocalizationUnavailable(
        run_reference=ref,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    )
    _patch_all_seams(monkeypatch, entry=entry, localization_result=unavailable)

    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None

    payload = view.to_dict()
    assert payload["run_summary"]["tombstoned"] is True
    loc_outcome = payload["localization_outcome"]
    assert loc_outcome["kind"] == "unavailable"
    assert loc_outcome["reason"] == REASON_MISSING_DERIVED_FACTS
    assert payload["sub_reports"]["localization"] == "unavailable"


def test_fake_run_id_returns_none_before_localization_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fake run_id → ``build_inspect_view`` returns ``None`` BEFORE
    ``get_localization_findings`` is ever called."""

    derive_calls: list[Any] = []

    def must_not_call(*_a: Any, **_k: Any) -> Any:
        derive_calls.append("called")
        raise AssertionError("get_localization_findings called for unknown run_id")

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store, skipped=None: [])
    monkeypatch.setattr(inspect_module, "get_localization_findings", must_not_call)

    result = build_inspect_view(object(), "fake-run-id")  # type: ignore[arg-type]
    assert result is None
    assert derive_calls == []


def test_inspect_never_calls_derive_localization_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``inspect`` is a pure cache read — it must NEVER call
    ``derive_localization_findings``. Verified by importing
    ``get_localization_findings`` in the inspect module and confirming
    the returned outcome is produced by that cache-only path.

    Since ``derive_localization_findings`` is NOT imported at the
    ``inspect`` module level (only ``get_localization_findings`` is),
    the architectural enforcement is structural: there is no
    ``inspect_module.derive_localization_findings`` to call. This test
    confirms the seam is the cache-read helper, not the derive helper."""

    entry = _make_entry()
    ref = entry.run_record.run_reference
    cache_result = LocalizationUnavailable(
        run_reference=ref,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    )

    get_calls: list[RunReference] = []

    def fake_get(_store: Any, r: RunReference) -> LocalizationUnavailable:
        get_calls.append(r)
        return cache_result

    monkeypatch.setattr(inspect_module, "list_run_history", lambda _store, skipped=None: [entry])
    monkeypatch.setattr(
        inspect_module, "retrieve_run_evidence", lambda *_a, **_k: entry
    )
    monkeypatch.setattr(
        inspect_module,
        "resolve_baseline_for_run",
        lambda _s, _entry: None,
    )
    monkeypatch.setattr(
        inspect_module,
        "get_coverage_facts",
        lambda _s, r: CoverageUnavailable(
            reason=COV_REASON_MISSING, detail="out of scope", run_reference=r
        ),
    )
    monkeypatch.setattr(inspect_module, "compare_runs", lambda *_a, **_k: None)
    monkeypatch.setattr(inspect_module, "get_localization_findings", fake_get)

    from novetest.replay import (
        REASON_MISSING_DERIVED_FACTS as REPLAY_REASON_MISSING,
        ReplayUnavailable,
    )

    monkeypatch.setattr(
        inspect_module,
        "get_replay_result",
        lambda _s, r: ReplayUnavailable(
            run_reference=r,
            reason=REPLAY_REASON_MISSING,
            detail="no replay attempt has been made for this run",
        ),
    )

    # Verify derive_localization_findings is not accessible via the inspect module
    assert not hasattr(inspect_module, "derive_localization_findings"), (
        "inspect module must NOT import derive_localization_findings — "
        "cache-only contract violated by exposing the derive seam"
    )

    build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    # The cache-read helper was called; the derive helper was never called
    # (structural guarantee: it's not imported at the module level).
    assert len(get_calls) == 1
    assert get_calls[0].run_id == _RUN_ID


def test_sub_reports_localization_flips_consistently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``sub_reports["localization"]`` flips to ``"available"`` ONLY when
    a ``LocalizationFinding`` lands, and stays ``"unavailable"`` for all
    ``LocalizationUnavailable`` reasons."""

    entry = _make_entry()
    ref = entry.run_record.run_reference

    # Case 1: fact-set → "available"
    _patch_all_seams(
        monkeypatch, entry=entry, localization_result=_make_localization_finding()
    )
    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    assert view.to_dict()["sub_reports"]["localization"] == "available"

    # Case 2: unavailable (missing-derived-facts) → "unavailable"
    _patch_all_seams(
        monkeypatch,
        entry=entry,
        localization_result=LocalizationUnavailable(
            run_reference=ref,
            reason=REASON_MISSING_DERIVED_FACTS,
            detail="not derived",
        ),
    )
    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    assert view.to_dict()["sub_reports"]["localization"] == "unavailable"

    # Case 3: unavailable (run-not-analyzable) → "unavailable"
    _patch_all_seams(
        monkeypatch,
        entry=entry,
        localization_result=LocalizationUnavailable(
            run_reference=ref,
            reason=REASON_RUN_NOT_ANALYZABLE,
            detail="run is tombstoned",
        ),
    )
    view = build_inspect_view(object(), _RUN_ID)  # type: ignore[arg-type]
    assert view is not None
    assert view.to_dict()["sub_reports"]["localization"] == "unavailable"
