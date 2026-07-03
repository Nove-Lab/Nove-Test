"""Cross-run coverage delta computation.

Workflow (from ``design/workflows/coverage.md``):

    compare_coverage_facts(run_reference_1, run_reference_2)
        -> coverage/get_coverage_facts (per side)

We resolve previously-derived facts for both runs, compute per-file
transitions (newly-covered / newly-uncovered lines and branches), and
produce a ``CoverageDelta`` entity. Either side missing facts surfaces
as ``CoverageUnavailable``.

Mapping-granularity mismatch is allowed: the per-Code-Location transition
set is still meaningful (it's defined at line/branch resolution, not
test-resolution), so we only flag granularity as ``incomparable`` when one
side has ``aggregate`` granularity and the caller would have expected
per-test signal. For the four interfaces of this slice, we **return the
delta regardless of granularity** but record both sides' granularity on
the result so callers can decide what to surface. This keeps the engine
focused on facts; Orchestration decides whether a coarser granularity is
acceptable for the requested workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self

from novetest.coverage.results import (
    REASON_ENGINE_MISMATCH,
    CoverageUnavailable,
)
from novetest.coverage.retrieval import get_coverage_facts
from novetest.memory.project_store import ProjectStore
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    CoverageSummary,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


SCHEMA_VERSION: int = 1


@dataclass(slots=True, frozen=True)
class FileCoverageDelta:
    """Per-file transition between baseline (``before``) and target (``after``).

    Lines / branches are reported as the set difference in **integer line
    numbers** — i.e. lines that were missing in baseline and executed in
    target (``newly_covered_lines``) and vice versa
    (``newly_uncovered_lines``). For branches we use the same set diff over
    ``(from_line, to_line)`` arc tuples.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    file_path: str
    newly_covered_lines: tuple[int, ...]
    newly_uncovered_lines: tuple[int, ...]
    newly_covered_branches: tuple[tuple[int, int], ...]
    newly_uncovered_branches: tuple[tuple[int, int], ...]
    summary_before: CoverageSummary
    summary_after: CoverageSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "newly_covered_lines": list(self.newly_covered_lines),
            "newly_uncovered_lines": list(self.newly_uncovered_lines),
            "newly_covered_branches": [list(b) for b in self.newly_covered_branches],
            "newly_uncovered_branches": [
                list(b) for b in self.newly_uncovered_branches
            ],
            "summary_before": self.summary_before.to_dict(),
            "summary_after": self.summary_after.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "file_path",
            "newly_covered_lines",
            "newly_uncovered_lines",
            "newly_covered_branches",
            "newly_uncovered_branches",
            "summary_before",
            "summary_after",
        )
        _require_keys(d, required, cls.__name__)
        return cls(
            file_path=str(d["file_path"]),
            newly_covered_lines=tuple(int(x) for x in d["newly_covered_lines"]),
            newly_uncovered_lines=tuple(int(x) for x in d["newly_uncovered_lines"]),
            newly_covered_branches=tuple(
                _branch_pair(b) for b in d["newly_covered_branches"]
            ),
            newly_uncovered_branches=tuple(
                _branch_pair(b) for b in d["newly_uncovered_branches"]
            ),
            summary_before=CoverageSummary.from_dict(dict(d["summary_before"])),
            summary_after=CoverageSummary.from_dict(dict(d["summary_after"])),
        )


@dataclass(slots=True, frozen=True)
class CoverageDelta:
    """Cross-run coverage delta entity.

    Carries the two Run References (NFR-COV-001 traceability), per-file
    transitions, file-set adds/removes, and both sides' summary +
    granularity so Orchestration can compose richer reports without
    re-loading the underlying fact sets.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    baseline_run_reference: RunReference
    target_run_reference: RunReference
    baseline_granularity: str
    target_granularity: str
    summary_before: CoverageSummary
    summary_after: CoverageSummary
    files_added: tuple[str, ...]
    files_removed: tuple[str, ...]
    file_deltas: tuple[FileCoverageDelta, ...]
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "baseline_run_reference": self.baseline_run_reference.to_dict(),
            "target_run_reference": self.target_run_reference.to_dict(),
            "baseline_granularity": self.baseline_granularity,
            "target_granularity": self.target_granularity,
            "summary_before": self.summary_before.to_dict(),
            "summary_after": self.summary_after.to_dict(),
            "files_added": list(self.files_added),
            "files_removed": list(self.files_removed),
            "file_deltas": [fd.to_dict() for fd in self.file_deltas],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "baseline_run_reference",
            "target_run_reference",
            "baseline_granularity",
            "target_granularity",
            "summary_before",
            "summary_after",
            "files_added",
            "files_removed",
            "file_deltas",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        return cls(
            baseline_run_reference=RunReference.from_dict(
                dict(d["baseline_run_reference"])
            ),
            target_run_reference=RunReference.from_dict(
                dict(d["target_run_reference"])
            ),
            baseline_granularity=str(d["baseline_granularity"]),
            target_granularity=str(d["target_granularity"]),
            summary_before=CoverageSummary.from_dict(dict(d["summary_before"])),
            summary_after=CoverageSummary.from_dict(dict(d["summary_after"])),
            files_added=tuple(str(p) for p in d["files_added"]),
            files_removed=tuple(str(p) for p in d["files_removed"]),
            file_deltas=tuple(
                FileCoverageDelta.from_dict(dict(fd)) for fd in d["file_deltas"]
            ),
            schema_version=int(schema_version),
        )


def compare_coverage_facts(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> CoverageDelta | CoverageUnavailable:
    """Return the coverage delta between ``baseline`` and ``target`` runs.

    Both sides must have previously-derived facts. If either side is
    missing, return ``CoverageUnavailable`` propagated from
    ``get_coverage_facts``.

    Cross-engine pairs are refused (``REASON_ENGINE_MISMATCH``) — D5 of
    ``decisions/2026-07-03-engine-selection-policy.md``: cross-run analyses
    never cross an engine boundary. A pytest fact set diffed against a
    cargo-test fact set would produce a "delta" that is pure file-set noise
    (disjoint path universes) or, worse, silently-wrong line arithmetic on
    coincidentally-shared paths. The guard lives here on the engine side —
    not at the CLI call sites — so every present and future consumer
    (``coverage diff``, ``compare``, Regression's coverage embed, any
    Orchestration composition) is protected by construction.
    """
    baseline = get_coverage_facts(store, baseline_run_reference)
    if isinstance(baseline, CoverageUnavailable):
        return baseline
    target = get_coverage_facts(store, target_run_reference)
    if isinstance(target, CoverageUnavailable):
        return target

    if baseline.engine_name != target.engine_name:
        # Mirrors regression/compare.py's engine guard (same wire string
        # "engine-mismatch", same detail shape carrying both names).
        # ``run_reference`` names the baseline side per the 2026-05-16
        # envelope decision's tie-break convention (binding constraint #4:
        # when the unavailability is not attributable to a single side,
        # the baseline is named); the detail string identifies both sides
        # so consumers don't need to guess.
        return CoverageUnavailable(
            reason=REASON_ENGINE_MISMATCH,
            detail=(
                f"baseline engine_name={baseline.engine_name!r} "
                f"!= target engine_name={target.engine_name!r}"
            ),
            run_reference=baseline.run_reference,
        )

    return _build_delta(baseline, target)


# --- internals ---------------------------------------------------------------


def _build_delta(
    baseline: CoverageFactSet, target: CoverageFactSet
) -> CoverageDelta:
    baseline_files = {f.file_path: f for f in baseline.files}
    target_files = {f.file_path: f for f in target.files}

    baseline_paths = set(baseline_files)
    target_paths = set(target_files)
    common_paths = baseline_paths & target_paths

    files_added = tuple(sorted(target_paths - baseline_paths))
    files_removed = tuple(sorted(baseline_paths - target_paths))

    file_deltas: list[FileCoverageDelta] = []
    for path in sorted(common_paths):
        delta = _file_delta(baseline_files[path], target_files[path])
        # Skip files with no actual transitions — keeps the on-the-wire
        # payload compact for unchanged files. This is purely a size win;
        # consumers should treat the absence of a file_delta as "no change".
        if (
            delta.newly_covered_lines
            or delta.newly_uncovered_lines
            or delta.newly_covered_branches
            or delta.newly_uncovered_branches
        ):
            file_deltas.append(delta)

    return CoverageDelta(
        baseline_run_reference=baseline.run_reference,
        target_run_reference=target.run_reference,
        baseline_granularity=baseline.mapping_granularity,
        target_granularity=target.mapping_granularity,
        summary_before=baseline.summary,
        summary_after=target.summary,
        files_added=files_added,
        files_removed=files_removed,
        file_deltas=tuple(file_deltas),
    )


def _file_delta(before: FileCoverage, after: FileCoverage) -> FileCoverageDelta:
    before_exec = set(before.executed_lines)
    after_exec = set(after.executed_lines)

    newly_covered_lines = tuple(sorted(after_exec - before_exec))
    newly_uncovered_lines = tuple(sorted(before_exec - after_exec))

    before_branches = set(before.executed_branches)
    after_branches = set(after.executed_branches)

    newly_covered_branches = tuple(sorted(after_branches - before_branches))
    newly_uncovered_branches = tuple(sorted(before_branches - after_branches))

    return FileCoverageDelta(
        file_path=before.file_path,
        newly_covered_lines=newly_covered_lines,
        newly_uncovered_lines=newly_uncovered_lines,
        newly_covered_branches=newly_covered_branches,
        newly_uncovered_branches=newly_uncovered_branches,
        summary_before=before.summary,
        summary_after=after.summary,
    )


def _branch_pair(raw: Any) -> tuple[int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"Branch arc must be a 2-element sequence, got {raw!r}")
    return (int(raw[0]), int(raw[1]))


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
