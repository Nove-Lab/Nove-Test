"""Unit tests for ``novetest.models.replay_result``.

Mirror of the sibling model contract tests (MOD-03): ``replay_result.py`` had
no dedicated ``tests/unit/models/`` mirror before this slice — it was
exercised only incidentally through the replay/orchestration suites, so the
serialization invariants around ``to_dict``/``from_dict`` (the required-key
set, the nested ``RunReference`` round-trip, ``schema_version`` pinning, and
the closed-vocabulary validators) had no direct pin. These cover them.
"""

from __future__ import annotations

import pytest

from novetest.models.replay_result import (
    REPLAY_CLASSIFICATIONS,
    REPLAY_UNABLE_REASONS,
    SCHEMA_VERSION,
    ReplayResult,
)
from novetest.models.run_reference import RunReference


_ORIGINAL = RunReference(run_id="01HREPLAY000000000000ORIG", created_at=1_700_000_000_000)
_REPLAYED = RunReference(run_id="01HREPLAY000000000000RPLY", created_at=1_700_000_005_000)


def _inconsistent(**overrides: object) -> ReplayResult:
    defaults: dict[str, object] = {
        "run_reference": _ORIGINAL,
        "classification": "inconsistent",
        "reruns_total": 3,
        "reruns_failed": 1,
        "test_id": "tests/test_flaky.py::test_sometimes",
        "replayed_run_reference": _REPLAYED,
        "per_rerun_outcomes": ("passed", "failed", "passed"),
        "consistency_summary": {
            "original_passed": 1,
            "replay_passed": 2,
            "replay_failed": 1,
            "replay_errored": 0,
        },
        "attempted_at": 1_700_000_006_000,
        "reason": None,
    }
    defaults.update(overrides)
    return ReplayResult(**defaults)  # type: ignore[arg-type]


# --- round-trip / serialization invariants ----------------------------------


def test_round_trip_full_fields() -> None:
    result = _inconsistent()
    restored = ReplayResult.from_dict(result.to_dict())
    assert restored == result


def test_round_trip_minimal_required_fields_only() -> None:
    """Only the five binding fields set; every optional takes its default."""
    result = ReplayResult(
        run_reference=_ORIGINAL,
        classification="reproducible",
        reruns_total=2,
        reruns_failed=0,
    )
    restored = ReplayResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.test_id is None
    assert restored.replayed_run_reference is None
    assert restored.per_rerun_outcomes == ()
    assert restored.consistency_summary == {}
    assert restored.attempted_at == 0
    assert restored.reason is None


def test_round_trip_unable_to_replay_with_reason() -> None:
    result = ReplayResult(
        run_reference=_ORIGINAL,
        classification="unable_to_replay",
        reruns_total=0,
        reruns_failed=0,
        reason="no-replayed-runs",
    )
    restored = ReplayResult.from_dict(result.to_dict())
    assert restored == result
    assert restored.reason == "no-replayed-runs"


def test_to_dict_field_completeness() -> None:
    """to_dict emits exactly the persisted key set (serialization invariant)."""
    payload = _inconsistent().to_dict()
    assert set(payload) == {
        "schema_version",
        "run_reference",
        "classification",
        "reruns_total",
        "reruns_failed",
        "test_id",
        "replayed_run_reference",
        "per_rerun_outcomes",
        "consistency_summary",
        "attempted_at",
        "reason",
    }


def test_to_dict_includes_schema_version_and_nested_versions() -> None:
    payload = _inconsistent().to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["run_reference"]["schema_version"] == SCHEMA_VERSION
    assert payload["replayed_run_reference"]["schema_version"] == SCHEMA_VERSION


def test_to_dict_nests_optional_run_reference_as_none() -> None:
    payload = _inconsistent(replayed_run_reference=None).to_dict()
    assert payload["replayed_run_reference"] is None


def test_to_dict_projects_per_rerun_outcomes_as_list() -> None:
    """``per_rerun_outcomes`` (a tuple in memory) serializes to a JSON list."""
    payload = _inconsistent().to_dict()
    assert payload["per_rerun_outcomes"] == ["passed", "failed", "passed"]
    assert isinstance(payload["per_rerun_outcomes"], list)


# --- schema_version pinning --------------------------------------------------


def test_from_dict_rejects_future_schema_version() -> None:
    payload = _inconsistent().to_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="Unsupported"):
        ReplayResult.from_dict(payload)


def test_from_dict_missing_required_key_raises() -> None:
    payload = _inconsistent().to_dict()
    del payload["reruns_total"]
    with pytest.raises(ValueError, match="missing required keys"):
        ReplayResult.from_dict(payload)


# --- validators (closed vocabularies + numeric invariants) -------------------


def test_rejects_unknown_classification() -> None:
    with pytest.raises(ValueError, match="classification"):
        _inconsistent(classification="flaky")


def test_rejects_negative_reruns_total() -> None:
    with pytest.raises(ValueError, match="reruns_total"):
        _inconsistent(reruns_total=-1, reruns_failed=0)


def test_rejects_reruns_failed_out_of_range() -> None:
    with pytest.raises(ValueError, match="reruns_failed"):
        _inconsistent(reruns_total=2, reruns_failed=3)


def test_rejects_unknown_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        _inconsistent(reason="mystery")


# --- closed-enum contract + frozen ------------------------------------------


def test_closed_vocabularies_match_documented_contract() -> None:
    assert REPLAY_CLASSIFICATIONS == frozenset(
        {"reproducible", "inconsistent", "unable_to_replay"}
    )
    assert REPLAY_UNABLE_REASONS == frozenset(
        {"no-replayed-runs", "replay-run-errored"}
    )


def test_instances_are_frozen() -> None:
    result = _inconsistent()
    with pytest.raises(AttributeError):
        result.classification = "reproducible"  # type: ignore[misc]
