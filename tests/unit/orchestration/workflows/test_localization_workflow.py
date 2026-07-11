"""W2/S22 (ORC-07/XCT-02) — localization flag-override workflow tests.

Two layers:

1. **Policy tests** — the full Defect-5 / Defect-7 scenario matrix
   exercised directly at the workflow seam
   (``orchestration/workflows/localization.py``): passthroughs,
   invalidate+re-derive, and the failure_proximity formula-noop
   carve-out, including WHICH audit structure comes back.

2. **Behavior-preservation oracle (S17 precedent)** — a verbatim replica
   of the pre-S22 ``cli/app.py::_rederive_if_cache_overrode_flags``
   (policy + immediate ``EnvelopeWarning`` construction) is run side by
   side with the NEW pipeline (workflow policy → audit →
   ``cli/app.py::_localization_audit_warning``). For every scenario the
   two pipelines must produce the same outcome object and an EQUAL
   ``EnvelopeWarning | None`` — proving the extraction changed nothing
   on the wire.

The engine seams (``derive_localization_findings``,
``invalidate_localization_findings``) are monkeypatched at the workflow
module; the replica binds the SAME fakes, so both pipelines observe
identical engine behavior. The CLI-handler wiring of these workflows is
covered by ``tests/unit/cli/test_localization*.py``; the real on-disk
invalidation is covered end-to-end by
``tests/integration/cli/test_localization_e2e.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from novetest.cli.app import (
    _build_localization_cache_rederived_warning,
    _build_localization_formula_noop_warning,
    _localization_audit_warning,
)
from novetest.cli.output import EnvelopeWarning
from novetest.localization import LocalizationFinding, LocalizationUnavailable
from novetest.models import RunReference
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.orchestration.workflows import localization as wf
from novetest.orchestration.workflows.localization import (
    CacheRederivedAudit,
    FormulaNoopAudit,
    derive_latest_localization_with_flag_policy,
    derive_localization_with_flag_policy,
)


_RUN_ID = "01WFLOCWFLOCWFLOCWFLOCWFLO"
_STORE = object()  # policy never inspects the store; engine seams are faked


def _ref() -> RunReference:
    return RunReference(run_id=_RUN_ID, created_at=1_700_000_000_000)


def _make_finding(
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    mode: str = "sbfl_per_test",
) -> LocalizationFinding:
    ref = _ref()
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    is_fp = mode == "failure_proximity"
    entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=CodeLocation(
            kind="file" if is_fp else "symbol",
            file="src/calc.py",
            symbol=None if is_fp else "buggy",
            line_range=None if is_fp else (4, 5),
            primary_line=5,
            evidence_lines=(5,),
        ),
        score_raw=1.0,
        score_normalized=1.0,
        formula=formula,
        alternate_scores={} if is_fp else {"op2": 0.9},
        related_failed_tests=("tests/test_calc.py::test_buggy",),
        evidence_citations=(citation,),
    )
    return LocalizationFinding(
        run_reference=ref,
        engine_name="pytest",
        ecosystem="python",
        mode=mode,
        confidence="low" if is_fp else "high",
        formula=formula,
        alternate_scores_available=() if is_fp else ("op2",),
        top_n=top_n,
        entries=(entry,),
        derived_at=9_000,
        metadata={},
    )


def _two_phase_derive(
    cached: LocalizationFinding | LocalizationUnavailable,
    fresh: LocalizationFinding,
) -> Callable[..., LocalizationFinding | LocalizationUnavailable]:
    """Cached on call 1, fresh thereafter — the engine's cache-aware shape."""
    calls: list[tuple[Any, ...]] = []

    def _derive(*args: Any, **kwargs: Any) -> LocalizationFinding | LocalizationUnavailable:
        calls.append((args, kwargs))
        return cached if len(calls) == 1 else fresh

    _derive.calls = calls  # type: ignore[attr-defined]
    return _derive


class _FakeCache:
    """Observable stand-in for ``invalidate_localization_findings``."""

    def __init__(self, tmp_path: Path) -> None:
        self.path = tmp_path / "fake_localization_findings.json"
        self.path.touch()
        self.invalidations: list[tuple[Any, str]] = []

    def invalidate(self, store: Any, run_id: str) -> None:
        self.invalidations.append((store, run_id))
        self.path.unlink(missing_ok=True)

    @property
    def exists(self) -> bool:
        return self.path.exists()


@pytest.fixture
def fake_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeCache:
    cache = _FakeCache(tmp_path)
    monkeypatch.setattr(wf, "invalidate_localization_findings", cache.invalidate)
    return cache


# ---------------------------------------------------------------------------
# 1) Policy tests at the workflow seam
# ---------------------------------------------------------------------------


def test_unavailable_outcome_passes_through_with_no_audit(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    unavailable = LocalizationUnavailable(
        run_reference=_ref(), reason="no-failed-tests", detail="0 failed tests"
    )
    monkeypatch.setattr(
        wf, "derive_localization_findings", lambda *_a, **_k: unavailable
    )
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="dstar2",
        top_n=5,
        formula_explicit=True,
        top_n_explicit=True,
    )
    assert outcome is unavailable
    assert audit is None
    assert fake_cache.exists  # never invalidated


def test_defaulted_flags_never_trigger_rederive_despite_cache_diff(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    cached = _make_finding(formula="dstar2", top_n=3)
    fake = _two_phase_derive(cached, cached)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is cached
    assert audit is None
    assert len(fake.calls) == 1  # type: ignore[attr-defined]
    assert fake_cache.exists


def test_explicit_formula_mismatch_invalidates_and_rederives(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    cached = _make_finding(formula="ochiai", top_n=10)
    fresh = _make_finding(formula="dstar2", top_n=10)
    fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="dstar2",
        top_n=10,
        formula_explicit=True,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert audit.run_id == _RUN_ID
    assert (audit.previous_formula, audit.previous_top_n) == ("ochiai", 10)
    assert (audit.requested_formula, audit.requested_top_n) == ("dstar2", 10)
    assert audit.formula_explicit is True
    assert audit.top_n_explicit is False
    # Invalidation went through the PUBLIC engine API with (store, run_id).
    assert fake_cache.invalidations == [(_STORE, _RUN_ID)]
    assert not fake_cache.exists
    # Re-derive happened at the requested flags.
    assert len(fake.calls) == 2  # type: ignore[attr-defined]
    _, second_kwargs = fake.calls[1]  # type: ignore[attr-defined]
    assert second_kwargs == {"top_n": 10, "formula": "dstar2"}


def test_explicit_top_n_mismatch_rederives(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    cached = _make_finding(formula="ochiai", top_n=10)
    fresh = _make_finding(formula="ochiai", top_n=5)
    fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=5,
        formula_explicit=False,
        top_n_explicit=True,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert audit.previous_top_n == 10
    assert audit.requested_top_n == 5
    assert not fake_cache.exists


def test_matching_explicit_flags_pass_through(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    matching = _make_finding(formula="dstar2", top_n=5)
    fake = _two_phase_derive(matching, matching)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="dstar2",
        top_n=5,
        formula_explicit=True,
        top_n_explicit=True,
    )
    assert outcome is matching
    assert audit is None
    assert len(fake.calls) == 1  # type: ignore[attr-defined]
    assert fake_cache.exists


def test_failure_proximity_formula_only_mismatch_reports_noop_audit(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Defect 7 carve-out: no invalidation, no re-derive, noop audit."""
    placeholder = _make_finding(
        formula="ochiai", top_n=10, mode="failure_proximity"
    )
    fake = _two_phase_derive(placeholder, placeholder)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="op2",
        top_n=10,
        formula_explicit=True,
        top_n_explicit=False,
    )
    assert outcome is placeholder
    assert audit == FormulaNoopAudit(
        requested_formula="op2",
        returned_formula="ochiai",
        mode="failure_proximity",
    )
    assert len(fake.calls) == 1  # type: ignore[attr-defined]
    assert fake_cache.invalidations == []
    assert fake_cache.exists


def test_failure_proximity_top_n_mismatch_still_rederives(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """The carve-out is formula-ONLY: a top_n mismatch re-derives normally."""
    cached = _make_finding(formula="ochiai", top_n=10, mode="failure_proximity")
    fresh = _make_finding(formula="ochiai", top_n=3, mode="failure_proximity")
    fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="op2",
        top_n=3,
        formula_explicit=True,
        top_n_explicit=True,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert not fake_cache.exists


def test_latest_variant_applies_the_same_policy(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """``latest``: initial derive via ``derive_latest_localization``; the
    re-derive goes through ``derive_localization_findings`` (run_reference
    already resolved by the returned finding)."""
    cached = _make_finding(formula="ochiai", top_n=10)
    fresh = _make_finding(formula="dstar2", top_n=10)
    latest_calls: list[dict[str, Any]] = []

    def fake_latest(store: Any, *, formula: str, top_n: int) -> LocalizationFinding:
        latest_calls.append({"formula": formula, "top_n": top_n})
        return cached

    monkeypatch.setattr(wf, "derive_latest_localization", fake_latest)
    monkeypatch.setattr(
        wf, "derive_localization_findings", lambda *_a, **_k: fresh
    )
    outcome, audit = derive_latest_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        formula="dstar2",
        top_n=10,
        formula_explicit=True,
        top_n_explicit=False,
    )
    assert latest_calls == [{"formula": "dstar2", "top_n": 10}]
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert fake_cache.invalidations == [(_STORE, _RUN_ID)]


# ---------------------------------------------------------------------------
# 2) Behavior-preservation oracle — verbatim pre-S22 replica vs the new
#    workflow → audit → CLI-warning pipeline.
# ---------------------------------------------------------------------------


def _replica_rederive_if_cache_overrode_flags(
    *,
    store: Any,
    outcome: LocalizationFinding | LocalizationUnavailable,
    resolved_formula: str,
    resolved_top_n: int,
    formula_explicit: bool,
    top_n_explicit: bool,
    derive_localization_findings: Callable[..., Any],
    localization_findings_path: Callable[..., Path],
) -> tuple[
    LocalizationFinding | LocalizationUnavailable,
    EnvelopeWarning | None,
]:
    """Verbatim replica of pre-S22 ``cli/app.py::_rederive_if_cache_overrode_flags``.

    Body copied from `main` ``e32b3ec`` (docstring elided); the two engine
    seams the original resolved as ``cli.app`` module globals are threaded
    as parameters so the oracle can bind the SAME fakes the workflow sees.
    The warning builders are the (unchanged) real ``cli/app.py`` helpers.
    """
    if not isinstance(outcome, LocalizationFinding):
        return outcome, None
    cached_formula = outcome.formula
    cached_top_n = outcome.top_n
    formula_mismatch = formula_explicit and resolved_formula != cached_formula
    top_n_mismatch = top_n_explicit and resolved_top_n != cached_top_n
    if not (formula_mismatch or top_n_mismatch):
        return outcome, None

    is_failure_proximity_formula_noop = (
        outcome.mode == "failure_proximity"
        and formula_mismatch
        and not top_n_mismatch
    )
    if is_failure_proximity_formula_noop:
        warning = _build_localization_formula_noop_warning(
            requested_formula=resolved_formula,
            returned_formula=cached_formula,
            mode=outcome.mode,
        )
        return outcome, warning

    run_reference = outcome.run_reference
    previous_cached_args = (cached_formula, cached_top_n)
    localization_findings_path(store, run_reference.run_id).unlink(missing_ok=True)
    fresh = derive_localization_findings(
        store,
        run_reference,
        top_n=resolved_top_n,
        formula=resolved_formula,
    )
    warning = _build_localization_cache_rederived_warning(
        run_id=run_reference.run_id,
        previous_cached_args=previous_cached_args,
        resolved_formula=resolved_formula,
        resolved_top_n=resolved_top_n,
        formula_explicit=formula_explicit,
        top_n_explicit=top_n_explicit,
    )
    return fresh, warning


_ORACLE_SCENARIOS: list[dict[str, Any]] = [
    # (initial outcome factory kwargs OR "unavailable", flags)
    {
        "name": "unavailable-passthrough",
        "cached": "unavailable",
        "fresh": {"formula": "dstar2", "top_n": 5},
        "formula": "dstar2",
        "top_n": 5,
        "formula_explicit": True,
        "top_n_explicit": True,
    },
    {
        "name": "defaulted-flags-keep-cache",
        "cached": {"formula": "dstar2", "top_n": 3},
        "fresh": {"formula": "ochiai", "top_n": 10},
        "formula": "ochiai",
        "top_n": 10,
        "formula_explicit": False,
        "top_n_explicit": False,
    },
    {
        "name": "explicit-formula-mismatch-rederives",
        "cached": {"formula": "ochiai", "top_n": 10},
        "fresh": {"formula": "dstar2", "top_n": 10},
        "formula": "dstar2",
        "top_n": 10,
        "formula_explicit": True,
        "top_n_explicit": False,
    },
    {
        "name": "explicit-top-n-mismatch-rederives",
        "cached": {"formula": "ochiai", "top_n": 10},
        "fresh": {"formula": "ochiai", "top_n": 5},
        "formula": "ochiai",
        "top_n": 5,
        "formula_explicit": False,
        "top_n_explicit": True,
    },
    {
        "name": "both-flags-mismatch-rederives",
        "cached": {"formula": "ochiai", "top_n": 10},
        "fresh": {"formula": "op2", "top_n": 3},
        "formula": "op2",
        "top_n": 3,
        "formula_explicit": True,
        "top_n_explicit": True,
    },
    {
        "name": "matching-explicit-flags-passthrough",
        "cached": {"formula": "dstar2", "top_n": 5},
        "fresh": {"formula": "dstar2", "top_n": 5},
        "formula": "dstar2",
        "top_n": 5,
        "formula_explicit": True,
        "top_n_explicit": True,
    },
    {
        "name": "failure-proximity-formula-noop",
        "cached": {"formula": "ochiai", "top_n": 10, "mode": "failure_proximity"},
        "fresh": {"formula": "ochiai", "top_n": 10, "mode": "failure_proximity"},
        "formula": "op2",
        "top_n": 10,
        "formula_explicit": True,
        "top_n_explicit": False,
    },
    {
        "name": "failure-proximity-top-n-mismatch-rederives",
        "cached": {"formula": "ochiai", "top_n": 10, "mode": "failure_proximity"},
        "fresh": {"formula": "ochiai", "top_n": 3, "mode": "failure_proximity"},
        "formula": "op2",
        "top_n": 3,
        "formula_explicit": True,
        "top_n_explicit": True,
    },
]


@pytest.mark.parametrize(
    "scenario", _ORACLE_SCENARIOS, ids=[s["name"] for s in _ORACLE_SCENARIOS]
)
def test_oracle_new_pipeline_equals_premove_inline_policy(
    scenario: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """(outcome, EnvelopeWarning|None) equal between OLD and NEW pipelines."""
    if scenario["cached"] == "unavailable":
        cached: LocalizationFinding | LocalizationUnavailable = (
            LocalizationUnavailable(
                run_reference=_ref(), reason="no-failed-tests", detail="none"
            )
        )
    else:
        cached = _make_finding(**scenario["cached"])
    fresh = _make_finding(**scenario["fresh"])

    flags = {
        "formula": scenario["formula"],
        "top_n": scenario["top_n"],
        "formula_explicit": scenario["formula_explicit"],
        "top_n_explicit": scenario["top_n_explicit"],
    }

    # NEW pipeline: full workflow entry (initial derive is engine call #1;
    # a policy re-derive is call #2) → audit → CLI warning mapper.
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_cache = _FakeCache(new_dir)
    new_fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", new_fake)
    monkeypatch.setattr(wf, "invalidate_localization_findings", new_cache.invalidate)
    new_outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula=flags["formula"],
        top_n=flags["top_n"],
        formula_explicit=flags["formula_explicit"],
        top_n_explicit=flags["top_n_explicit"],
    )
    new_warning = _localization_audit_warning(audit)

    # OLD pipeline: verbatim pre-S22 inline replica bound to equivalent fakes.
    old_cache_file = tmp_path / "old" / "fake_localization_findings.json"
    old_cache_file.parent.mkdir(exist_ok=True)
    old_cache_file.touch()
    old_fake = _two_phase_derive(cached, fresh)
    # Replica receives the initial outcome directly (as the pre-move CLI
    # did after its own first derive call), so consume call #1 to keep
    # the two-phase fakes aligned between pipelines.
    old_fake(_STORE, _ref(), top_n=flags["top_n"], formula=flags["formula"])
    old_outcome, old_warning = _replica_rederive_if_cache_overrode_flags(
        store=_STORE,
        outcome=cached,
        resolved_formula=flags["formula"],
        resolved_top_n=flags["top_n"],
        formula_explicit=flags["formula_explicit"],
        top_n_explicit=flags["top_n_explicit"],
        derive_localization_findings=old_fake,
        localization_findings_path=lambda *_a, **_k: old_cache_file,
    )

    assert new_outcome is old_outcome or new_outcome == old_outcome
    assert new_warning == old_warning
    # Cache side effects agree (invalidated in both pipelines or neither).
    assert new_cache.exists == old_cache_file.exists()
