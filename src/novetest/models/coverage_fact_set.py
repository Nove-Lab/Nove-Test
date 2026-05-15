"""Coverage Fact Set domain model.

Persisted structured Coverage Facts derived from a single Run's native
coverage payload (e.g. coverage.py JSON). The set carries per-file line
and branch coverage, the test-to-code mapping (when granularity permits),
and aggregate summary counters, all anchored to the originating Run
Reference (NFR-COV-001).

Source of truth for attributes:
- `design/requirements-analysis/domain-model.md` (Coverage Fact + Code Location)
- `design/interace-contract/coverage.md`
- `design/implementation-plan/engine-adapters.md` (`mapping_granularity` tiers)

This file owns three frozen dataclasses that together form the on-disk
`coverage_facts.json` payload:

- ``CoverageSummary``  — aggregate counters across all files.
- ``FileCoverage``     — one source file's line/branch coverage + per-line
                          test contexts (test-to-code map at line resolution).
- ``CoverageFactSet``  — the top-level entity persisted as
                          ``<store>/coverage/facts/run_<id>/coverage_facts.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

from novetest.models.run_reference import RunReference


SCHEMA_VERSION: int = 1

# Allowed values for ``CoverageFactSet.mapping_granularity`` — engine-adapter
# defined tiers; see engine-adapters.md "Per-Test Coverage Attribution".
MAPPING_GRANULARITIES: frozenset[str] = frozenset(
    {"per-test", "per-test-class", "per-test-file", "aggregate"}
)


@dataclass(slots=True, frozen=True)
class CoverageSummary:
    """Aggregate coverage counters across every file in a Fact Set.

    Field names mirror coverage.py's ``totals`` block so the mapping is
    auditable for the pytest path. ``percent_covered`` is the engine-reported
    value (rounded by the native engine); we do not recompute it to avoid
    drift between this and what the native CLI reports.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    num_statements: int
    covered_statements: int
    missing_statements: int
    excluded_statements: int
    num_branches: int
    covered_branches: int
    missing_branches: int
    percent_covered: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_statements": self.num_statements,
            "covered_statements": self.covered_statements,
            "missing_statements": self.missing_statements,
            "excluded_statements": self.excluded_statements,
            "num_branches": self.num_branches,
            "covered_branches": self.covered_branches,
            "missing_branches": self.missing_branches,
            "percent_covered": self.percent_covered,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "num_statements",
            "covered_statements",
            "missing_statements",
            "num_branches",
            "covered_branches",
            "missing_branches",
            "percent_covered",
        )
        _require_keys(d, required, cls.__name__)
        return cls(
            num_statements=int(d["num_statements"]),
            covered_statements=int(d["covered_statements"]),
            missing_statements=int(d["missing_statements"]),
            excluded_statements=int(d.get("excluded_statements", 0)),
            num_branches=int(d["num_branches"]),
            covered_branches=int(d["covered_branches"]),
            missing_branches=int(d["missing_branches"]),
            percent_covered=float(d["percent_covered"]),
        )


@dataclass(slots=True, frozen=True)
class FileCoverage:
    """Coverage payload for a single source file.

    ``file_path`` is the path as reported by the native engine (already
    project-relative when coverage.py is configured with
    ``relative_files = True`` — see Run Team's adapter slice). Branches are
    pairs of ``(from_line, to_line)``: coverage.py emits them in this shape
    in ``executed_branches`` / ``missing_branches``.

    ``line_contexts`` is the test-to-code map at line resolution: it maps
    each executed line to the tuple of test node IDs that hit it. The map
    is empty for files with no per-test attribution (``mapping_granularity``
    coarser than ``per-test``).
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    file_path: str
    executed_lines: tuple[int, ...]
    missing_lines: tuple[int, ...]
    excluded_lines: tuple[int, ...]
    executed_branches: tuple[tuple[int, int], ...]
    missing_branches: tuple[tuple[int, int], ...]
    summary: CoverageSummary
    line_contexts: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "executed_lines": list(self.executed_lines),
            "missing_lines": list(self.missing_lines),
            "excluded_lines": list(self.excluded_lines),
            "executed_branches": [list(b) for b in self.executed_branches],
            "missing_branches": [list(b) for b in self.missing_branches],
            "summary": self.summary.to_dict(),
            # JSON object keys are strings — store line numbers as strings on the wire.
            "line_contexts": {
                str(line): list(nodeids) for line, nodeids in self.line_contexts.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "file_path",
            "executed_lines",
            "missing_lines",
            "excluded_lines",
            "executed_branches",
            "missing_branches",
            "summary",
        )
        _require_keys(d, required, cls.__name__)
        line_contexts_raw = d.get("line_contexts") or {}
        return cls(
            file_path=str(d["file_path"]),
            executed_lines=tuple(int(x) for x in d["executed_lines"]),
            missing_lines=tuple(int(x) for x in d["missing_lines"]),
            excluded_lines=tuple(int(x) for x in d["excluded_lines"]),
            executed_branches=tuple(
                _branch_pair(b) for b in d["executed_branches"]
            ),
            missing_branches=tuple(
                _branch_pair(b) for b in d["missing_branches"]
            ),
            summary=CoverageSummary.from_dict(dict(d["summary"])),
            line_contexts={
                int(line): tuple(str(n) for n in nodeids)
                for line, nodeids in line_contexts_raw.items()
            },
        )


@dataclass(slots=True, frozen=True)
class CoverageFactSet:
    """Structured Coverage Facts for one Run.

    Persisted at ``<store>/coverage/facts/run_<run_id>/coverage_facts.json``
    — this filename is **load-bearing**: Memory's ``_availability_flags``
    probes for exactly this path to auto-flip
    ``MemoryEntry.has_coverage_facts``. See
    ``design/interace-contract/coverage.md`` and the Memory store code.

    ``mapping_granularity`` is mandatory and constrained to the four tiers
    defined in ``design/implementation-plan/engine-adapters.md``.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_reference: RunReference
    engine_name: str
    ecosystem: str
    mapping_granularity: str
    summary: CoverageSummary
    files: tuple[FileCoverage, ...]
    derived_at: int
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.mapping_granularity not in MAPPING_GRANULARITIES:
            raise ValueError(
                f"Invalid mapping_granularity={self.mapping_granularity!r}; "
                f"expected one of {sorted(MAPPING_GRANULARITIES)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_reference": self.run_reference.to_dict(),
            "engine_name": self.engine_name,
            "ecosystem": self.ecosystem,
            "mapping_granularity": self.mapping_granularity,
            "summary": self.summary.to_dict(),
            "files": [f.to_dict() for f in self.files],
            "derived_at": self.derived_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "run_reference",
            "engine_name",
            "ecosystem",
            "mapping_granularity",
            "summary",
            "files",
            "derived_at",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        return cls(
            run_reference=RunReference.from_dict(dict(d["run_reference"])),
            engine_name=str(d["engine_name"]),
            ecosystem=str(d["ecosystem"]),
            mapping_granularity=str(d["mapping_granularity"]),
            summary=CoverageSummary.from_dict(dict(d["summary"])),
            files=tuple(FileCoverage.from_dict(dict(f)) for f in d["files"]),
            derived_at=int(d["derived_at"]),
            metadata=dict(d.get("metadata") or {}),
            schema_version=int(schema_version),
        )


def _branch_pair(raw: Any) -> tuple[int, int]:
    """Normalize a coverage.py branch arc representation to ``(from, to)``."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(
            f"Branch arc must be a 2-element sequence, got {raw!r}"
        )
    return (int(raw[0]), int(raw[1]))


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
