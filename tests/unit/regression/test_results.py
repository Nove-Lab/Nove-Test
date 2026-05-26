"""Unit tests for ``novetest.regression.results``.

The shape mirrors ``CoverageUnavailable``: a frozen dataclass with a
reason code, optional detail, and optional Run References. Constants and
``KNOWN_REASONS`` membership are part of the decision §7 contract.
"""

from __future__ import annotations

from dataclasses import is_dataclass

from novetest.models.run_reference import RunReference
from novetest.regression.results import (
    KNOWN_REASONS,
    REASON_ENGINE_MISMATCH,
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_COMPARABLE_BASELINE,
    REASON_RUN_NOT_FOUND,
    REASON_RUN_TOMBSTONED,
    REASON_TARGET_MISMATCH,
    RegressionUnavailable,
)


_REF_A = RunReference(run_id="01HBASE", created_at=1)
_REF_B = RunReference(run_id="01HTRGT", created_at=2)


def test_known_reasons_is_the_closed_six_set() -> None:
    assert KNOWN_REASONS == frozenset(
        {
            REASON_RUN_NOT_FOUND,
            REASON_RUN_TOMBSTONED,
            REASON_NO_COMPARABLE_BASELINE,
            REASON_MISSING_DERIVED_FACTS,
            REASON_ENGINE_MISMATCH,
            REASON_TARGET_MISMATCH,
        }
    )


def test_reason_constants_match_decision_strings() -> None:
    """Pin the wire-level strings — these flow into the CLI envelope."""
    assert REASON_RUN_NOT_FOUND == "run-not-found"
    assert REASON_RUN_TOMBSTONED == "run-tombstoned"
    assert REASON_NO_COMPARABLE_BASELINE == "no-comparable-baseline"
    assert REASON_MISSING_DERIVED_FACTS == "missing-derived-facts"
    assert REASON_ENGINE_MISMATCH == "engine-mismatch"
    assert REASON_TARGET_MISMATCH == "target-mismatch"


def test_regression_unavailable_is_frozen_dataclass() -> None:
    assert is_dataclass(RegressionUnavailable)


def test_regression_unavailable_equality_and_defaults() -> None:
    a = RegressionUnavailable(reason=REASON_RUN_NOT_FOUND)
    b = RegressionUnavailable(reason=REASON_RUN_NOT_FOUND)
    assert a == b
    assert a.detail is None
    assert a.baseline_run_reference is None
    assert a.target_run_reference is None


def test_regression_unavailable_carries_both_refs() -> None:
    u = RegressionUnavailable(
        reason=REASON_RUN_TOMBSTONED,
        detail="baseline",
        baseline_run_reference=_REF_A,
        target_run_reference=_REF_B,
    )
    assert u.baseline_run_reference == _REF_A
    assert u.target_run_reference == _REF_B
