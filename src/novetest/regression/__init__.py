"""Regression engine — run-to-run behavior comparison.

Consumes Run Records from Memory (and optionally Coverage Facts from
Coverage) and produces a structured ``RegressionFactSet`` describing per-
test outcome transitions, stdout/stderr fingerprints, and an embedded
``CoverageDelta`` when both runs have Coverage Facts.

Public API exposes the Internal interfaces from
``design/interace-contract/regression.md`` that this Phase-3-entry slice
implements:

- ``compare_runs``               — public entry point (cache-aware)
- ``derive_regression_facts``    — write-side helper (always re-derives)
- ``get_regression_facts``       — cache-read helper

Plus the discriminator types callers need to ``isinstance``-match the
unavailable outcome (decision §7) without importing private modules.

The CLI verbs (``novetest regression compare`` / ``novetest regression
latest`` / ``novetest compare``) and the higher-level
``resolve_latest_baseline`` / ``derive_latest_regression`` /
``check_regression_availability`` helpers are intentionally OUT of scope
for this slice — see ``agent-comms/tasks/regression-team-2026-05-26-
compare-runs-impl.md``.
"""

from novetest.models.regression_fact_set import (
    SCHEMA_VERSION,
    TRANSITION_CATEGORIES,
    OutputDiffRecord,
    RegressionFactSet,
    RegressionSummary,
    TestTransition,
)
from novetest.regression.compare import (
    compare_runs,
    derive_regression_facts,
)
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
from novetest.regression.retrieval import get_regression_facts


__all__ = [
    "KNOWN_REASONS",
    "OutputDiffRecord",
    "REASON_ENGINE_MISMATCH",
    "REASON_MISSING_DERIVED_FACTS",
    "REASON_NO_COMPARABLE_BASELINE",
    "REASON_RUN_NOT_FOUND",
    "REASON_RUN_TOMBSTONED",
    "REASON_TARGET_MISMATCH",
    "RegressionFactSet",
    "RegressionSummary",
    "RegressionUnavailable",
    "SCHEMA_VERSION",
    "TRANSITION_CATEGORIES",
    "TestTransition",
    "compare_runs",
    "derive_regression_facts",
    "get_regression_facts",
]
