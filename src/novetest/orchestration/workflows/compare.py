"""``novetest compare`` workflow — composed Regression + Coverage view (W2/S23).

Owns the regression+coverage synthesis that previously lived inline in
``cli/app.py::compare_cmd`` (ORC-06): one call to Regression's
cache-aware ``compare_runs`` plus one call to Coverage's
``compare_coverage_facts`` for the same pair, composed into a single
:class:`CompareView`. The CLI handler resolves the two run_ids (a
transport concern shared with ``coverage diff`` / ``regression compare``
— a stale or fake id emits the structured ``not-found`` envelope at
exit 2 BEFORE this workflow is invoked), calls
:func:`build_compare_view`, and projects the view onto the envelope.

The two engines decide independently: either block may be
``kind: "unavailable"`` while the other carries facts — the view never
short-circuits on a single-engine outage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novetest.coverage import CoverageDelta, CoverageUnavailable, compare_coverage_facts
from novetest.memory import ProjectStore
from novetest.models import RunReference
from novetest.orchestration.projection import (
    coverage_delta_payload,
    regression_outcome_payload,
)
from novetest.regression import (
    RegressionFactSet,
    RegressionUnavailable,
    compare_runs,
)


@dataclass(slots=True, frozen=True)
class CompareView:
    """Composed Regression + Coverage view surfaced by ``novetest compare``.

    ``regression_outcome`` is the same discriminated block ``regression
    compare`` emits; ``coverage_delta`` is the same block ``coverage
    diff`` emits (single-sourced via ``orchestration/projection.py``).
    ``to_dict`` is the envelope ``data`` payload verbatim — key order
    (``regression_outcome`` then ``coverage_delta``) is part of the
    byte-stable wire surface.
    """

    regression_outcome: RegressionFactSet | RegressionUnavailable
    coverage_delta: CoverageDelta | CoverageUnavailable

    def to_dict(self) -> dict[str, Any]:
        return {
            "regression_outcome": regression_outcome_payload(self.regression_outcome),
            "coverage_delta": coverage_delta_payload(self.coverage_delta),
        }


def build_compare_view(
    store: ProjectStore,
    baseline_ref: RunReference,
    target_ref: RunReference,
) -> CompareView:
    """Compose the Regression + Coverage comparison for a resolved pair.

    ``compare_runs`` is cache-aware (derives + persists on miss, reads on
    hit; tombstoned inputs surface ``REASON_RUN_TOMBSTONED`` per decision
    §C.1); ``compare_coverage_facts`` propagates ``unavailable`` from
    whichever side lacks derived coverage facts. Both outcomes are
    composed unconditionally — partial availability is data, not an
    error.
    """
    return CompareView(
        regression_outcome=compare_runs(store, baseline_ref, target_ref),
        coverage_delta=compare_coverage_facts(store, baseline_ref, target_ref),
    )


__all__ = [
    "CompareView",
    "build_compare_view",
]
