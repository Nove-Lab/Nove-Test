"""Shared domain-model entity definitions.

Internal models are frozen ``dataclasses(slots=True, frozen=True)`` with
hand-rolled ``to_dict``/``from_dict``. Each model carries a v1
``schema_version`` so `record.json` can be migrated forward on read without
a release-bound migration. See
`design/implementation-plan/foundations.md` §4-§5 for the persistence and
modeling rationale.
"""

from novetest.models.memory_entry import MemoryEntry
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


__all__ = [
    "MemoryEntry",
    "RunRecord",
    "RunReference",
    "TestResult",
]
