"""W2/S23 (ORC-08) — projector single-source guards + wire-shape oracles.

Three layers of protection for ``orchestration/projection.py``:

1. **Divergence guards** — neither ``cli/app.py`` nor
   ``orchestration/workflows/inspect.py`` may re-grow a LOCAL definition
   of any projector (the pre-S23 state was four pairs of doubles held
   together only by a docstring promise of "identical wire shape").
   Enforced by AST scan of both modules' sources plus identity checks
   that the names both call paths use ARE the shared functions.

2. **Wire-shape pins** — the exact payload keys/discriminators for both
   ``kind`` variants of all five projectors, exercised through the ONE
   shared implementation.

3. **Behavior-preservation oracles (S17 precedent)** — verbatim replicas
   of the pre-move ``cli/app.py`` projector bodies AND the pre-move
   ``workflows/inspect.py`` section bodies, asserted byte-equal against
   the shared functions for every outcome variant. A silent shape change
   in ``projection.py`` fails against BOTH pre-move call-path replicas.
"""

from __future__ import annotations

import ast
import inspect as inspect_stdlib
from typing import Any

import pytest

from novetest.cli import app as app_module
from novetest.cli.output import Envelope
from novetest.coverage import CoverageUnavailable
from novetest.coverage.compare import CoverageDelta, FileCoverageDelta
from novetest.localization import LocalizationFinding, LocalizationUnavailable
from novetest.models import MemoryEntry, ReplayResult, RunRecord, RunReference
from novetest.models.coverage_fact_set import CoverageFactSet, CoverageSummary
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
)
from novetest.models.regression_fact_set import RegressionFactSet, RegressionSummary
from novetest.orchestration import projection
from novetest.orchestration.workflows import inspect as inspect_module
from novetest.regression import RegressionUnavailable
from novetest.replay import ReplayUnavailable


_BASELINE_ID = "01BASELINETESTTESTTESTTEST"
_TARGET_ID = "01TARGETTESTTESTTESTTESTTE"
_RUN_ID = "01PROJRUNPROJRUNPROJRUNPRO"


# ---------------------------------------------------------------------------
# Outcome factories (borrowed shapes from the existing CLI handler tests)
# ---------------------------------------------------------------------------


def _ref(run_id: str = _RUN_ID, created_at: int = 1) -> RunReference:
    return RunReference(run_id=run_id, created_at=created_at)


def _summary(percent: float = 80.0) -> CoverageSummary:
    return CoverageSummary(
        num_statements=10,
        covered_statements=8,
        missing_statements=2,
        excluded_statements=0,
        num_branches=2,
        covered_branches=1,
        missing_branches=1,
        percent_covered=percent,
    )


def _coverage_fact_set() -> CoverageFactSet:
    return CoverageFactSet(
        run_reference=_ref(),
        engine_name="pytest",
        ecosystem="python",
        mapping_granularity="per-test",
        summary=_summary(),
        files=(),
        derived_at=4,
    )


def _coverage_unavailable(with_ref: bool) -> CoverageUnavailable:
    return CoverageUnavailable(
        reason="missing-derived-facts",
        detail="no coverage_facts.json",
        run_reference=_ref() if with_ref else None,
    )


def _coverage_delta() -> CoverageDelta:
    return CoverageDelta(
        baseline_run_reference=_ref(_BASELINE_ID, 1),
        target_run_reference=_ref(_TARGET_ID, 2),
        baseline_granularity="per-test",
        target_granularity="per-test",
        summary_before=_summary(70.0),
        summary_after=_summary(90.0),
        files_added=("new_file.py",),
        files_removed=(),
        file_deltas=(
            FileCoverageDelta(
                file_path="changed_file.py",
                newly_covered_lines=(5, 7),
                newly_uncovered_lines=(),
                newly_covered_branches=(),
                newly_uncovered_branches=(),
                summary_before=_summary(70.0),
                summary_after=_summary(90.0),
            ),
        ),
    )


def _regression_fact_set() -> RegressionFactSet:
    return RegressionFactSet(
        baseline_run_reference=_ref(_BASELINE_ID, 1),
        target_run_reference=_ref(_TARGET_ID, 2),
        baseline_engine_name="pytest",
        target_engine_name="pytest",
        baseline_engine_version="8.2.0",
        target_engine_version="8.2.0",
        derived_at=4,
        summary=RegressionSummary(
            regressed=0,
            fixed=1,
            still_failing=0,
            still_passing=12,
            still_skipped=0,
            newly_skipped=0,
            newly_active=0,
            added=0,
            removed=0,
            total_baseline_tests=13,
            total_target_tests=13,
        ),
        test_transitions=(),
        output_diff=None,
        coverage_change=None,
    )


def _regression_unavailable(
    *, with_baseline: bool, with_target: bool
) -> RegressionUnavailable:
    return RegressionUnavailable(
        reason="no-comparable-baseline",
        detail="tests/",
        baseline_run_reference=_ref(_BASELINE_ID, 1) if with_baseline else None,
        target_run_reference=_ref(_TARGET_ID, 2) if with_target else None,
    )


def _localization_finding() -> LocalizationFinding:
    ref = _ref()
    citation = EvidenceCitation(
        kind="test_result",
        run_reference=ref,
        selector={"test_id": "tests/test_calc.py::test_buggy", "outcome": "failed"},
    )
    entry = LocalizationEntry(
        rank=1,
        tied_with=(),
        code_location=CodeLocation(
            kind="symbol",
            file="src/calc.py",
            symbol="buggy",
            line_range=(4, 5),
            primary_line=5,
            evidence_lines=(5,),
        ),
        score_raw=1.0,
        score_normalized=1.0,
        formula="ochiai",
        alternate_scores={"op2": 0.9},
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
        alternate_scores_available=("op2",),
        top_n=10,
        entries=(entry,),
        derived_at=9_000,
        metadata={},
    )


def _localization_unavailable() -> LocalizationUnavailable:
    return LocalizationUnavailable(
        run_reference=_ref(),
        reason="no-failed-tests",
        detail="0 failed tests",
    )


def _replay_result() -> ReplayResult:
    return ReplayResult(
        run_reference=_ref(),
        classification="inconsistent",
        reruns_total=5,
        reruns_failed=2,
        test_id="tests/t.py::t",
        reason=None,
    )


def _replay_unavailable() -> ReplayUnavailable:
    return ReplayUnavailable(
        run_reference=_ref(),
        reason="tombstoned-original",
        detail="tombstoned",
    )


# ---------------------------------------------------------------------------
# 1) Divergence guards — no local re-definitions, both call paths bind
#    the SAME shared functions.
# ---------------------------------------------------------------------------


_PROJECTOR_NAMES = frozenset(
    {
        "coverage_outcome_payload",
        "coverage_delta_payload",
        "regression_outcome_payload",
        "localization_outcome_payload",
        "replay_outcome_payload",
    }
)

# The historical local names the doubles carried — a revert under EITHER
# naming convention must trip the guard.
_LEGACY_LOCAL_NAMES = frozenset(
    {
        "_coverage_outcome_payload",
        "_coverage_delta_payload",
        "_regression_outcome_payload",
        "_localization_outcome_payload",
        "_replay_outcome_payload",
        "_coverage_outcome_section",
        "_regression_outcome_section",
        "_localization_outcome_section",
        "_replay_outcome_section",
    }
)


def _module_function_names(module: object) -> set[str]:
    """All function names DEFINED (any nesting) in a module's source."""
    tree = ast.parse(inspect_stdlib.getsource(module))  # type: ignore[arg-type]
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@pytest.mark.parametrize("module", [app_module, inspect_module])
def test_no_local_projector_definitions(module: object) -> None:
    """Neither consumer module defines any projector locally (S23 guard)."""
    defined = _module_function_names(module)
    forbidden = defined & (_PROJECTOR_NAMES | _LEGACY_LOCAL_NAMES)
    assert not forbidden, (
        f"{module.__name__} locally re-defines projector(s) {sorted(forbidden)}; "  # type: ignore[attr-defined]
        "the single source is novetest/orchestration/projection.py (W2/S23)"
    )


def test_cli_app_binds_the_shared_projectors() -> None:
    """``cli/app.py`` imports the SAME function objects projection defines."""
    assert app_module.coverage_outcome_payload is projection.coverage_outcome_payload
    assert app_module.coverage_delta_payload is projection.coverage_delta_payload
    assert (
        app_module.regression_outcome_payload is projection.regression_outcome_payload
    )
    assert (
        app_module.localization_outcome_payload
        is projection.localization_outcome_payload
    )
    assert app_module.replay_outcome_payload is projection.replay_outcome_payload


def test_inspect_workflow_binds_the_shared_projectors() -> None:
    """``workflows/inspect.py`` imports the SAME function objects."""
    assert (
        inspect_module.coverage_outcome_payload is projection.coverage_outcome_payload
    )
    assert (
        inspect_module.regression_outcome_payload
        is projection.regression_outcome_payload
    )
    assert (
        inspect_module.localization_outcome_payload
        is projection.localization_outcome_payload
    )
    assert inspect_module.replay_outcome_payload is projection.replay_outcome_payload


# ---------------------------------------------------------------------------
# 2) Wire-shape pins through the shared implementation
# ---------------------------------------------------------------------------


def test_coverage_outcome_fact_set_shape() -> None:
    payload = projection.coverage_outcome_payload(_coverage_fact_set())
    assert payload["kind"] == "fact-set"
    assert list(payload.keys()) == [
        "kind",
        "run_reference",
        "mapping_granularity",
        "summary",
    ]
    assert payload["run_reference"]["run_id"] == _RUN_ID
    assert "schema_version" not in payload


def test_coverage_outcome_unavailable_shape_null_and_present_ref() -> None:
    with_ref = projection.coverage_outcome_payload(_coverage_unavailable(True))
    without_ref = projection.coverage_outcome_payload(_coverage_unavailable(False))
    for payload in (with_ref, without_ref):
        assert payload["kind"] == "unavailable"
        assert list(payload.keys()) == ["kind", "run_reference", "reason", "detail"]
        assert payload["reason"] == "missing-derived-facts"
    assert with_ref["run_reference"]["run_id"] == _RUN_ID
    assert without_ref["run_reference"] is None


def test_coverage_delta_shape_strips_schema_version() -> None:
    payload = projection.coverage_delta_payload(_coverage_delta())
    assert payload["kind"] == "delta"
    assert "schema_version" not in payload
    assert payload["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert payload["files_added"] == ["new_file.py"]


def test_coverage_delta_unavailable_shape() -> None:
    payload = projection.coverage_delta_payload(_coverage_unavailable(True))
    assert payload["kind"] == "unavailable"
    assert list(payload.keys()) == ["kind", "run_reference", "reason", "detail"]


def test_regression_outcome_fact_set_shape_strips_schema_version() -> None:
    payload = projection.regression_outcome_payload(_regression_fact_set())
    assert payload["kind"] == "fact-set"
    assert "schema_version" not in payload
    assert payload["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert payload["target_run_reference"]["run_id"] == _TARGET_ID


def test_regression_outcome_unavailable_independently_nullable_refs() -> None:
    both = projection.regression_outcome_payload(
        _regression_unavailable(with_baseline=True, with_target=True)
    )
    baseline_only = projection.regression_outcome_payload(
        _regression_unavailable(with_baseline=True, with_target=False)
    )
    neither = projection.regression_outcome_payload(
        _regression_unavailable(with_baseline=False, with_target=False)
    )
    for payload in (both, baseline_only, neither):
        assert payload["kind"] == "unavailable"
        assert list(payload.keys()) == [
            "kind",
            "baseline_run_reference",
            "target_run_reference",
            "reason",
            "detail",
        ]
    assert both["target_run_reference"]["run_id"] == _TARGET_ID
    assert baseline_only["target_run_reference"] is None
    assert baseline_only["baseline_run_reference"]["run_id"] == _BASELINE_ID
    assert neither["baseline_run_reference"] is None


def test_localization_outcome_fact_set_shape_strips_schema_version() -> None:
    payload = projection.localization_outcome_payload(_localization_finding())
    assert payload["kind"] == "fact-set"
    assert "schema_version" not in payload
    assert payload["formula"] == "ochiai"
    assert payload["entries"][0]["rank"] == 1


def test_localization_outcome_unavailable_shape() -> None:
    payload = projection.localization_outcome_payload(_localization_unavailable())
    assert payload["kind"] == "unavailable"
    assert set(payload.keys()) == {"kind", "run_reference", "reason", "detail"}
    assert payload["reason"] == "no-failed-tests"


def test_replay_outcome_result_shape_drops_run_reference() -> None:
    payload = projection.replay_outcome_payload(_replay_result())
    assert payload["kind"] == "replay-result"
    assert "schema_version" not in payload
    assert "run_reference" not in payload
    assert payload["classification"] == "inconsistent"


def test_replay_outcome_unavailable_shape() -> None:
    payload = projection.replay_outcome_payload(_replay_unavailable())
    assert payload["kind"] == "unavailable"
    assert payload["reason"] == "tombstoned-original"
    assert "run_reference" in payload


# ---------------------------------------------------------------------------
# 3) Behavior-preservation oracles (S17 precedent) — verbatim replicas of
#    the PRE-S23 cli/app.py projector bodies AND workflows/inspect.py
#    section bodies, compared against the shared functions.
# ---------------------------------------------------------------------------


def _replica_cli_coverage_outcome_payload(
    outcome: CoverageFactSet | CoverageUnavailable,
) -> dict[str, Any]:
    """Verbatim body of pre-S23 ``cli/app.py::_coverage_outcome_payload``."""
    if isinstance(outcome, CoverageFactSet):
        return {
            "kind": "fact-set",
            "run_reference": outcome.run_reference.to_dict(),
            "mapping_granularity": outcome.mapping_granularity,
            "summary": outcome.summary.to_dict(),
        }
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _replica_cli_coverage_delta_payload(
    outcome: CoverageDelta | CoverageUnavailable,
) -> dict[str, Any]:
    """Verbatim body of pre-S23 ``cli/app.py::_coverage_delta_payload``."""
    if isinstance(outcome, CoverageDelta):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "delta", **body}
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _replica_cli_regression_outcome_payload(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, Any]:
    """Verbatim body of pre-S23 ``cli/app.py::_regression_outcome_payload``."""
    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _replica_cli_localization_outcome_payload(
    outcome: LocalizationFinding | LocalizationUnavailable,
) -> dict[str, Any]:
    """Verbatim body of pre-S23 ``cli/app.py::_localization_outcome_payload``."""
    if isinstance(outcome, LocalizationFinding):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


def _replica_cli_replay_outcome_payload(
    outcome: ReplayResult | ReplayUnavailable,
) -> dict[str, Any]:
    """Verbatim body of pre-S23 ``cli/app.py::_replay_outcome_payload``."""
    if isinstance(outcome, ReplayResult):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        body.pop("run_reference", None)
        return {"kind": "replay-result", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


def _replica_inspect_coverage_outcome_section(
    outcome: CoverageFactSet | CoverageUnavailable,
) -> dict[str, object]:
    """Verbatim body of pre-S23 ``inspect.py::_coverage_outcome_section``."""
    if isinstance(outcome, CoverageFactSet):
        return {
            "kind": "fact-set",
            "run_reference": outcome.run_reference.to_dict(),
            "mapping_granularity": outcome.mapping_granularity,
            "summary": outcome.summary.to_dict(),
        }
    return {
        "kind": "unavailable",
        "run_reference": (
            outcome.run_reference.to_dict()
            if outcome.run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _replica_inspect_regression_outcome_section(
    outcome: RegressionFactSet | RegressionUnavailable,
) -> dict[str, object]:
    """Verbatim body of pre-S23 ``inspect.py::_regression_outcome_section``."""
    if isinstance(outcome, RegressionFactSet):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {
        "kind": "unavailable",
        "baseline_run_reference": (
            outcome.baseline_run_reference.to_dict()
            if outcome.baseline_run_reference is not None
            else None
        ),
        "target_run_reference": (
            outcome.target_run_reference.to_dict()
            if outcome.target_run_reference is not None
            else None
        ),
        "reason": outcome.reason,
        "detail": outcome.detail,
    }


def _replica_inspect_localization_outcome_section(
    outcome: LocalizationFinding | LocalizationUnavailable,
) -> dict[str, object]:
    """Verbatim body of pre-S23 ``inspect.py::_localization_outcome_section``."""
    if isinstance(outcome, LocalizationFinding):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        return {"kind": "fact-set", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


def _replica_inspect_replay_outcome_section(
    outcome: ReplayResult | ReplayUnavailable,
) -> dict[str, object]:
    """Verbatim body of pre-S23 ``inspect.py::_replay_outcome_section``."""
    if isinstance(outcome, ReplayResult):
        body = outcome.to_dict()
        body.pop("schema_version", None)
        body.pop("run_reference", None)
        return {"kind": "replay-result", **body}
    return {"kind": "unavailable", **outcome.to_dict()}


def test_oracle_coverage_outcome_matches_both_premove_call_paths() -> None:
    for outcome in (
        _coverage_fact_set(),
        _coverage_unavailable(True),
        _coverage_unavailable(False),
    ):
        shared = projection.coverage_outcome_payload(outcome)
        assert shared == _replica_cli_coverage_outcome_payload(outcome)
        assert shared == _replica_inspect_coverage_outcome_section(outcome)


def test_oracle_coverage_delta_matches_premove_call_path() -> None:
    for outcome in (_coverage_delta(), _coverage_unavailable(True)):
        shared = projection.coverage_delta_payload(outcome)
        assert shared == _replica_cli_coverage_delta_payload(outcome)


def test_oracle_regression_outcome_matches_both_premove_call_paths() -> None:
    for outcome in (
        _regression_fact_set(),
        _regression_unavailable(with_baseline=True, with_target=True),
        _regression_unavailable(with_baseline=True, with_target=False),
        _regression_unavailable(with_baseline=False, with_target=False),
    ):
        shared = projection.regression_outcome_payload(outcome)
        assert shared == _replica_cli_regression_outcome_payload(outcome)
        assert shared == _replica_inspect_regression_outcome_section(outcome)


def test_oracle_localization_outcome_matches_both_premove_call_paths() -> None:
    for outcome in (_localization_finding(), _localization_unavailable()):
        shared = projection.localization_outcome_payload(outcome)
        assert shared == _replica_cli_localization_outcome_payload(outcome)
        assert shared == _replica_inspect_localization_outcome_section(outcome)


def test_oracle_replay_outcome_matches_both_premove_call_paths() -> None:
    for outcome in (_replay_result(), _replay_unavailable()):
        shared = projection.replay_outcome_payload(outcome)
        assert shared == _replica_cli_replay_outcome_payload(outcome)
        assert shared == _replica_inspect_replay_outcome_section(outcome)


# ---------------------------------------------------------------------------
# Both call paths still EMIT through the shared function — end-to-end
# spot checks (verb path exercised in tests/unit/cli/*, inspect path here).
# ---------------------------------------------------------------------------


def test_inspect_view_to_dict_uses_shared_projections() -> None:
    """``InspectView.to_dict`` blocks equal the shared projections exactly."""
    ref = _ref()
    record = RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=1,
        completed_at=2,
        summary_counts={"failed": 1, "total": 1},
    )
    entry = MemoryEntry(entry_id=ref.run_id, run_record=record, stored_at=3)
    view = inspect_module.InspectView(
        entry=entry,
        coverage_outcome=_coverage_fact_set(),
        regression_outcome=_regression_unavailable(
            with_baseline=True, with_target=True
        ),
        localization_outcome=_localization_unavailable(),
        replay_outcome=_replay_unavailable(),
    )
    payload = view.to_dict()
    assert payload["coverage_outcome"] == projection.coverage_outcome_payload(
        _coverage_fact_set()
    )
    assert payload["regression_outcome"] == projection.regression_outcome_payload(
        _regression_unavailable(with_baseline=True, with_target=True)
    )
    assert payload["localization_outcome"] == projection.localization_outcome_payload(
        _localization_unavailable()
    )
    assert payload["replay_outcome"] == projection.replay_outcome_payload(
        _replay_unavailable()
    )
    assert payload["sub_reports"] == {
        "coverage": "available",
        "regression": "unavailable",
        "localization": "unavailable",
        "replay": "unavailable",
    }


# ---------------------------------------------------------------------------
# 4) Strip-allowlist sync guard (W2/S28, ORC-27)
#
# ``orchestration/projection.py`` strips ``schema_version`` from every
# persisted-record body before it reaches the v1 envelope's ``data`` block
# (envelope versioning lives at the top-level ``schema`` field, never inside
# individual data blocks). That strip was a hardcoded ``body.pop("schema_version")``
# literal repeated per-projector, with NO single source tying the stripped
# field name back to the models that emit it and no drift guard. This section
# centralizes the strip allowlist into ONE constant and fails loudly on either
# drift direction:
#
#   - a model dropping/renaming ``schema_version`` would turn the pop into a
#     silent no-op (Guard A catches it: strip list ⊆ persisted body keys);
#   - a projector that stopped stripping would leak the persisted field onto
#     the wire (Guard B catches it);
#   - the transport envelope growing/losing a top-level field would silently
#     shift what the snapshot convention pins (Guard C catches it — a new
#     top-level envelope field must consciously join the frozen set).
# ---------------------------------------------------------------------------


# Single source of truth for the persisted-body key(s) the wire projection
# strips. Adding a projector strip => add the field here (and vice versa).
WIRE_PROJECTION_STRIPPED_KEYS: frozenset[str] = frozenset({"schema_version"})

# The frozen v1 envelope top-level wire keys (``Envelope.to_dict``). Bumping is
# a deliberate, versioned change requiring a ``decisions/`` entry.
ENVELOPE_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"schema", "command", "ok", "data", "errors", "warnings"}
)

# Every persisted-record body a projector pops WIRE_PROJECTION_STRIPPED_KEYS out
# of (the ``body = outcome.to_dict(); body.pop(...)`` sites in projection.py).
_STRIP_SITE_BODY_FACTORIES = (
    _coverage_delta,
    _regression_fact_set,
    _localization_finding,
    _replay_result,
)

# (projector, factory) pairs for every schema-bearing wire projection — the
# payloads that must never carry a persisted ``schema_version``.
_SCHEMA_BEARING_PROJECTIONS = (
    (projection.coverage_outcome_payload, _coverage_fact_set),
    (projection.coverage_delta_payload, _coverage_delta),
    (projection.regression_outcome_payload, _regression_fact_set),
    (projection.localization_outcome_payload, _localization_finding),
    (projection.replay_outcome_payload, _replay_result),
)


def test_strip_keys_are_live_persisted_body_fields() -> None:
    """Guard A — the stripped key names ARE live fields on every strip-site body.

    If a model stops emitting ``schema_version`` the ``body.pop`` becomes a
    silent no-op; this fails loudly, by name, when the allowlist drifts off the
    persisted shape (strip list ⊆ persisted body keys).
    """
    for factory in _STRIP_SITE_BODY_FACTORIES:
        body_keys = set(factory().to_dict().keys())
        missing = WIRE_PROJECTION_STRIPPED_KEYS - body_keys
        assert not missing, (
            f"{factory.__name__}().to_dict() no longer emits {sorted(missing)}; "
            "the projection strip would silently become a no-op — reconcile "
            "WIRE_PROJECTION_STRIPPED_KEYS with the persisted body shape."
        )


def test_wire_projections_strip_every_allowlisted_key() -> None:
    """Guard B — no schema-bearing projection leaks an allowlisted key onto the wire."""
    for projector, factory in _SCHEMA_BEARING_PROJECTIONS:
        payload = projector(factory())
        leaked = WIRE_PROJECTION_STRIPPED_KEYS & set(payload.keys())
        assert not leaked, (
            f"{projector.__name__} leaked {sorted(leaked)} onto the wire; a "
            "persisted schema_version must never reach the envelope data block."
        )


def test_envelope_top_level_keys_frozen_and_disjoint_from_strip_list() -> None:
    """Guard C — pin the transport envelope's top-level key set; keep the strip
    allowlist disjoint from it.

    A new top-level envelope field must consciously join ENVELOPE_TOP_LEVEL_KEYS
    (and the snapshot/strip convention updated) rather than silently drift; and
    the wire-projection strip targets nested persisted-body fields only, so it
    can never remove a transport field.
    """
    actual = set(Envelope(command="x", ok=True).to_dict().keys())
    assert actual == ENVELOPE_TOP_LEVEL_KEYS, (
        "v1 envelope top-level keys drifted from the frozen set "
        f"{sorted(ENVELOPE_TOP_LEVEL_KEYS)}; got {sorted(actual)} — a schema "
        "change requires a decisions/ entry (schema: novetest/v1 bump)."
    )
    assert WIRE_PROJECTION_STRIPPED_KEYS.isdisjoint(ENVELOPE_TOP_LEVEL_KEYS)
