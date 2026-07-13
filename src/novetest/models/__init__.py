"""Shared domain-model entity definitions.

Internal models are frozen ``dataclasses(slots=True, frozen=True)`` with
hand-rolled ``to_dict``/``from_dict``. Each model carries a v1
``schema_version`` so `record.json` can be migrated forward on read without
a release-bound migration. See
`design/implementation-plan/foundations.md` §4-§5 for the persistence and
modeling rationale.
"""

from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.engine_matrix import SUPPORTED_ENGINE_PAIRS
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.memory_entry import MemoryEntry
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import FAIL_LIKE_OUTCOMES, TestResult


__all__ = [
    "FAIL_LIKE_OUTCOMES",
    "SUPPORTED_ENGINE_PAIRS",
    "CodeLocation",
    "CoverageFactSet",
    "CoverageSummary",
    "EvidenceCitation",
    "FileCoverage",
    "LocalizationEntry",
    "LocalizationFinding",
    "MemoryEntry",
    "ReplayResult",
    "RunRecord",
    "RunReference",
    "TestResult",
]
