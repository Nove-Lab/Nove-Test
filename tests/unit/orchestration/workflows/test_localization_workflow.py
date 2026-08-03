"""W2/S22 (ORC-07/XCT-02) — localization flag-override workflow tests.

Two layers:

1. **Policy tests** — the full Defect-5 / Defect-7 / row-41 / row-43
   scenario matrix exercised directly at the workflow seam
   (``orchestration/workflows/localization.py``): passthroughs,
   invalidate+re-derive (on explicit AND on defaulted flags since the
   2026-08-03 determinism fix), the failure_proximity formula-noop
   carve-out, and the stale-build detector — including WHICH audit
   structure comes back.

2. **Behavior-preservation oracle (S17 precedent)** — a verbatim replica
   of the pre-S22 ``cli/app.py::_rederive_if_cache_overrode_flags``
   (policy + immediate ``EnvelopeWarning`` construction) is run side by
   side with the NEW pipeline (workflow policy → audit →
   ``cli/app.py::_localization_audit_warning``). Every scenario but one
   must produce the same outcome object and an EQUAL
   ``EnvelopeWarning | None`` — proving the S22 extraction still changed
   nothing on the wire. The single exception is the row-41 fix's own
   input (defaulted flags differing from the cache), where the oracle
   pins the DIVERGENCE instead: see ``diverges_by_design``.

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


def _current_build_metadata(mode: str) -> dict[str, Any]:
    """``metadata`` exactly as THIS build's engine renders it, per mode.

    Both SBFL pipelines run every finding through
    ``localization/derive.py::_exclusion_metadata``, so the four
    ``test_file_*`` keys are unconditional there since ``088091e``;
    ``failure_proximity`` carries only the two older keys and never had
    the four. The row-43 staleness detector reads exactly this
    difference, so a fixture that hand-waves ``metadata={}`` on an SBFL
    mode is not a payload this build can emit — it is a PRE-088091e
    payload, and tests that want the ordinary case must say so.
    """
    base: dict[str, Any] = {"changed_files_count": None, "regression_reweighted": None}
    if mode == "failure_proximity":
        return {"changed_files_count": 0, "regression_reweighted": False}
    return {
        **base,
        "test_file_locations_excluded": 1,
        "test_file_exclusion_reverted": False,
        "test_file_exclusion_basis": "exact",
        "test_file_locations_suppressed": [],
    }


def _make_finding(
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    mode: str = "sbfl_per_test",
    metadata: dict[str, Any] | None = None,
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
        metadata=_current_build_metadata(mode) if metadata is None else metadata,
    )


def _stale_build_finding(
    *,
    formula: str = "ochiai",
    top_n: int = 10,
    mode: str = "sbfl_per_test",
) -> LocalizationFinding:
    """A finding in the shape a PRE-``088091e`` build persisted (row 43).

    Same payload minus the four ``test_file_*`` keys — measured, not
    guessed: a real v0.2.1 build derives ``metadata`` keys
    ``['changed_files_count', 'regression_reweighted']`` and nothing
    else.
    """
    return _make_finding(
        formula=formula,
        top_n=top_n,
        mode=mode,
        metadata={"changed_files_count": 0, "regression_reweighted": False},
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


def test_defaulted_formula_rederives_when_cache_holds_another_formula(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Row-41 fix: an OMITTED ``--formula`` asks for ``DEFAULT_FORMULA``.

    Pre-fix this returned the cached ``dstar2`` finding untouched, which
    is how a bare ``localization latest`` came to serve back the last
    EXPLICITLY requested formula (same command, same inputs, different
    answer). The defaults are already substituted into
    ``resolved_formula`` before the policy runs, so the mismatch is real
    and the cache must be re-derived.
    """
    cached = _make_finding(formula="dstar2", top_n=10)
    fresh = _make_finding(formula="ochiai", top_n=10)
    fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert (audit.previous_formula, audit.requested_formula) == ("dstar2", "ochiai")
    # The audit still DISCLOSES that neither flag was typed by the user —
    # the booleans stopped gating and became pure disclosure.
    assert audit.formula_explicit is False
    assert audit.top_n_explicit is False
    assert fake_cache.invalidations == [(_STORE, _RUN_ID)]
    assert len(fake.calls) == 2  # type: ignore[attr-defined]
    _, second_kwargs = fake.calls[1]  # type: ignore[attr-defined]
    assert second_kwargs == {"top_n": 10, "formula": "ochiai"}


def test_defaulted_top_n_rederives_when_cache_holds_another_top_n(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Row-41 fix, ``top_n`` half — the same gating covered both fields."""
    cached = _make_finding(formula="ochiai", top_n=3)
    fresh = _make_finding(formula="ochiai", top_n=10)
    fake = _two_phase_derive(cached, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    assert (audit.previous_top_n, audit.requested_top_n) == (3, 10)
    assert not fake_cache.exists


def test_defaulted_flags_matching_the_cache_stay_a_silent_cache_hit(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """The common case must stay cheap: bare call, cache already at the
    defaults, current-build metadata → one engine call, no invalidation,
    no warning. (Guards the row-41 fix against becoming "re-derive on
    every bare call".)"""
    cached = _make_finding(formula="ochiai", top_n=10)
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


def test_failure_proximity_bare_calls_never_warn_however_often_repeated(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Defect-7 no-loop guard against the row-41 change.

    The Defect-7 loop was "every retry re-derives, gets the same
    placeholder back, warns again". Making DEFAULTED flags trigger
    re-derives could have re-armed it through the default path — it does
    not, because ``failure_proximity``'s placeholder IS
    ``DEFAULT_FORMULA`` (``localization/failure_proximity.py::
    _PLACEHOLDER_FORMULA`` == ``"ochiai"``), so a bare call finds no
    mismatch at all. Ten consecutive bare calls: no audit, no
    invalidation, one engine call each.
    """
    placeholder = _make_finding(
        formula="ochiai", top_n=10, mode="failure_proximity"
    )
    fake = _two_phase_derive(placeholder, placeholder)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    for _ in range(10):
        outcome, audit = derive_localization_with_flag_policy(
            _STORE,  # type: ignore[arg-type]
            _ref(),
            formula="ochiai",
            top_n=10,
            formula_explicit=False,
            top_n_explicit=False,
        )
        assert outcome is placeholder
        assert audit is None
    assert len(fake.calls) == 10  # type: ignore[attr-defined]
    assert fake_cache.invalidations == []
    assert fake_cache.exists


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
# 1b) Row-43 — the stale-build detector (an SBFL-mode finding whose
#     ``metadata`` lacks ``test_file_exclusion_basis`` predates 088091e).
# ---------------------------------------------------------------------------


def test_stale_build_sbfl_finding_is_invalidated_and_rederived(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Flags agree, so pre-row-43 this was served verbatim: a v0.2.1-derived
    ranking returned by a v0.3.0 binary at ``ok: true`` with no warning.
    Now the four-key detector fires: invalidate, re-derive at the resolved
    flags, and report the DISTINCT stale-build audit."""
    stale = _stale_build_finding(formula="ochiai", top_n=10)
    fresh = _make_finding(formula="ochiai", top_n=10)
    fake = _two_phase_derive(stale, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert audit == wf.StaleBuildRederivedAudit(
        run_id=_RUN_ID,
        mode="sbfl_per_test",
        missing_metadata_key="test_file_exclusion_basis",
        requested_formula="ochiai",
        requested_top_n=10,
    )
    # Invalidation through the PUBLIC engine API, re-derive at the
    # resolved flags — the same mechanics as the flag-override path.
    assert fake_cache.invalidations == [(_STORE, _RUN_ID)]
    assert not fake_cache.exists
    assert len(fake.calls) == 2  # type: ignore[attr-defined]
    _, second_kwargs = fake.calls[1]  # type: ignore[attr-defined]
    assert second_kwargs == {"top_n": 10, "formula": "ochiai"}


def test_stale_build_detector_also_covers_sbfl_aggregate(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Both SBFL modes render the four keys, so both are in scope."""
    stale = _stale_build_finding(mode="sbfl_aggregate")
    fresh = _make_finding(mode="sbfl_aggregate")
    monkeypatch.setattr(
        wf, "derive_localization_findings", _two_phase_derive(stale, fresh)
    )
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, wf.StaleBuildRederivedAudit)
    assert audit.mode == "sbfl_aggregate"


def test_current_build_finding_is_not_rederived_by_the_stale_detector(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """The common case stays a cheap cache hit: a finding carrying the
    four keys triggers exactly ONE engine call and no invalidation."""
    cached = _make_finding(formula="ochiai", top_n=10)
    assert "test_file_exclusion_basis" in cached.metadata  # fixture guard
    fake = _two_phase_derive(cached, _make_finding())
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
    assert fake_cache.invalidations == []
    assert fake_cache.exists


def test_failure_proximity_missing_keys_is_not_treated_as_stale(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """The SBFL-mode guard is load-bearing, not decoration.

    A FRESH ``failure_proximity`` finding from this build also lacks the
    four keys (measured: its metadata is
    ``['changed_files_count', 'regression_reweighted']``), so applying
    the detector there would re-derive every no-coverage run forever.
    """
    fp = _make_finding(mode="failure_proximity")
    assert "test_file_exclusion_basis" not in fp.metadata  # fixture guard
    fake = _two_phase_derive(fp, _make_finding(mode="failure_proximity"))
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fp
    assert audit is None
    assert len(fake.calls) == 1  # type: ignore[attr-defined]
    assert fake_cache.exists


def test_stale_build_plus_flag_mismatch_reports_the_flag_audit(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """Precedence, pinned: when the flags ALREADY force a re-derive, the
    payload is refreshed by this build anyway and
    ``localization-cache-rederived`` already discloses it — so the
    stale-build check does not double-fire and the wire behaviour of
    every pre-existing flag-override case is untouched."""
    stale = _stale_build_finding(formula="ochiai", top_n=10)
    fresh = _make_finding(formula="op2", top_n=10)
    fake = _two_phase_derive(stale, fresh)
    monkeypatch.setattr(wf, "derive_localization_findings", fake)
    outcome, audit = derive_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        _ref(),
        formula="op2",
        top_n=10,
        formula_explicit=True,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, CacheRederivedAudit)
    # ONE invalidation + ONE re-derive, not two of each.
    assert fake_cache.invalidations == [(_STORE, _RUN_ID)]
    assert len(fake.calls) == 2  # type: ignore[attr-defined]


def test_stale_build_detector_on_the_latest_variant(
    monkeypatch: pytest.MonkeyPatch, fake_cache: _FakeCache
) -> None:
    """``localization latest`` shares the policy, so it shares the fix."""
    stale = _stale_build_finding()
    fresh = _make_finding()
    monkeypatch.setattr(wf, "derive_latest_localization", lambda *_a, **_k: stale)
    monkeypatch.setattr(
        wf, "derive_localization_findings", lambda *_a, **_k: fresh
    )
    outcome, audit = derive_latest_localization_with_flag_policy(
        _STORE,  # type: ignore[arg-type]
        formula="ochiai",
        top_n=10,
        formula_explicit=False,
        top_n_explicit=False,
    )
    assert outcome is fresh
    assert isinstance(audit, wf.StaleBuildRederivedAudit)
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
        # The ONE scenario the row-41 fix deliberately changed: the
        # oracle asserts DIVERGENCE here, not equality (see the test).
        "name": "defaulted-flags-keep-cache",
        "diverges_by_design": True,
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

    if scenario.get("diverges_by_design"):
        # Row-41 (2026-08-03) intentionally broke the pre-move behaviour
        # for exactly this input: defaulted flags that differ from the
        # cache. The oracle keeps the scenario and pins the divergence so
        # a future refactor cannot quietly restore the old answer.
        assert old_outcome is cached and old_warning is None, (
            "the pre-row-41 replica is supposed to serve the stale cache here"
        )
        assert new_outcome is fresh, (
            "post-row-41 a bare call must re-derive at the DEFAULT values"
        )
        assert new_warning is not None
        assert new_warning.code == "localization-cache-rederived"
        assert new_cache.exists is False and old_cache_file.exists() is True
        return

    assert new_outcome is old_outcome or new_outcome == old_outcome
    assert new_warning == old_warning
    # Cache side effects agree (invalidated in both pipelines or neither).
    assert new_cache.exists == old_cache_file.exists()
