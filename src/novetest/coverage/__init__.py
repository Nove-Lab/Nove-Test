"""Coverage engine — structured Coverage Facts and cross-run deltas.

Consumes the native coverage payload that Run Team's adapter writes under
``<store>/run/artifacts/run_<id>/native/coverage.json`` and produces
structured Coverage Facts persisted at
``<store>/coverage/facts/run_<id>/coverage_facts.json``.

Public API exposes the four Internal interfaces from
``design/interace-contract/coverage.md``:

- ``derive_coverage_facts``      — build facts from the native payload and persist
- ``get_coverage_facts``         — load previously-derived facts
- ``compare_coverage_facts``     — cross-run delta
- ``check_coverage_availability``— filesystem probe for stage eligibility

Plus the result types callers need to discriminate ``isinstance`` against
the unavailable outcome (REQ-COV-004) without importing private modules.
"""

from novetest.coverage.availability import (
    CoverageAvailability,
    check_coverage_availability,
)
from novetest.coverage.compare import (
    SCHEMA_VERSION as COVERAGE_DELTA_SCHEMA_VERSION,
)
from novetest.coverage.compare import (
    CoverageDelta,
    FileCoverageDelta,
    compare_coverage_facts,
)
from novetest.coverage.derive import derive_coverage_facts
from novetest.coverage.results import CoverageUnavailable
from novetest.coverage.retrieval import get_coverage_facts


__all__ = [
    "COVERAGE_DELTA_SCHEMA_VERSION",
    "CoverageAvailability",
    "CoverageDelta",
    "CoverageUnavailable",
    "FileCoverageDelta",
    "check_coverage_availability",
    "compare_coverage_facts",
    "derive_coverage_facts",
    "get_coverage_facts",
]
