"""Regression Fact Set domain model.

Persisted structured Regression Facts derived by comparing two Run Records
sharing the same resolved Test Target. The set carries per-test outcome
transitions (the 9-category closed taxonomy), aggregate counts, a
SHA-256-keyed view of the native stdout/stderr diff, and — when both runs
have Coverage Facts — an embedded ``CoverageDelta`` payload.

Source of truth for the wire format:
- ``agent-comms/decisions/2026-05-26-regression-facts-json-layout.md`` §3, §4, §8
- ``design/interace-contract/regression.md``
- ``design/workflows/regression.md``

This file owns four frozen dataclasses that together form the on-disk
``regression_facts.json`` payload:

- ``TestTransition``       — one per-test transition record (closed 9-category enum).
- ``RegressionSummary``    — aggregate counts mirroring the 9 categories.
- ``OutputDiffRecord``     — SHA-256 + Project-Store-relative path refs only.
- ``RegressionFactSet``    — the top-level entity persisted at
  ``<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json``.

Read-side tolerance (per decision §8) is implemented in ``from_dict``:
optional fields default when absent on the wire so cross-engine consumers
can evolve loosely; any other omitted required field still raises
``ValueError``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

from novetest.models.run_reference import RunReference


SCHEMA_VERSION: int = 1


# Closed enum, validated at ``TestTransition.__post_init__``. Adding a value
# is a breaking change (consumers pattern-match on the closed set); requires
# a ``schema_version`` bump per decision §"Forward-compatible extension rules".
TRANSITION_CATEGORIES: frozenset[str] = frozenset(
    {
        "regressed",      # B=pass-like, T=fail-like
        "fixed",          # B=fail-like, T=pass-like
        "still_failing",  # B=fail-like, T=fail-like
        "still_passing",  # B=pass-like, T=pass-like
        "still_skipped",  # B=skip-like, T=skip-like
        "newly_skipped",  # B=active,    T=skip-like
        "newly_active",   # B=skip-like, T=active
        "added",          # B=missing,   T=present
        "removed",        # B=present,   T=missing
    }
)


@dataclass(slots=True, frozen=True)
class TestTransition:
    """One per-test transition between baseline and target.

    ``baseline_outcome`` / ``target_outcome`` preserve the raw native
    engine outcome strings — ``TestResult.outcome`` is intentionally not
    enum-locked at v1, so the closed 9-category ``category`` field is the
    interchange surface and the raw string remains available for callers
    that need it.

    ``baseline_outcome`` is ``None`` exactly when ``category == "added"``;
    ``target_outcome`` is ``None`` exactly when ``category == "removed"``.
    Failure references and duration values are independently nullable
    because the native engine may not have provided them.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION
    # Pytest collection guard — keeps this dataclass from being picked up
    # by test discovery just because its name starts with ``Test``. Mirrors
    # ``TestResult.__test__``.
    __test__: ClassVar[bool] = False

    node_id: str
    category: str
    baseline_outcome: str | None
    target_outcome: str | None
    baseline_failure_reference: str | None
    target_failure_reference: str | None
    baseline_duration_ms: int | None
    target_duration_ms: int | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.category not in TRANSITION_CATEGORIES:
            raise ValueError(
                f"Invalid TestTransition.category={self.category!r}; "
                f"expected one of {sorted(TRANSITION_CATEGORIES)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "category": self.category,
            "baseline_outcome": self.baseline_outcome,
            "target_outcome": self.target_outcome,
            "baseline_failure_reference": self.baseline_failure_reference,
            "target_failure_reference": self.target_failure_reference,
            "baseline_duration_ms": self.baseline_duration_ms,
            "target_duration_ms": self.target_duration_ms,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        _require_keys(d, ("schema_version", "node_id", "category"), cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        return cls(
            node_id=str(d["node_id"]),
            category=str(d["category"]),
            baseline_outcome=_opt_str(d.get("baseline_outcome")),
            target_outcome=_opt_str(d.get("target_outcome")),
            baseline_failure_reference=_opt_str(d.get("baseline_failure_reference")),
            target_failure_reference=_opt_str(d.get("target_failure_reference")),
            baseline_duration_ms=_opt_int(d.get("baseline_duration_ms")),
            target_duration_ms=_opt_int(d.get("target_duration_ms")),
            schema_version=int(schema_version),
        )


@dataclass(slots=True, frozen=True)
class RegressionSummary:
    """Aggregate counters across the 9 transition categories.

    ``total_baseline_tests`` = in-both + removed.
    ``total_target_tests``   = in-both + added.

    Convenience aggregates (not strictly recoverable from the per-category
    counts because in-both fans out across six categories).
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    regressed: int
    fixed: int
    still_failing: int
    still_passing: int
    still_skipped: int
    newly_skipped: int
    newly_active: int
    added: int
    removed: int
    total_baseline_tests: int
    total_target_tests: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "regressed": self.regressed,
            "fixed": self.fixed,
            "still_failing": self.still_failing,
            "still_passing": self.still_passing,
            "still_skipped": self.still_skipped,
            "newly_skipped": self.newly_skipped,
            "newly_active": self.newly_active,
            "added": self.added,
            "removed": self.removed,
            "total_baseline_tests": self.total_baseline_tests,
            "total_target_tests": self.total_target_tests,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "regressed",
            "fixed",
            "still_failing",
            "still_passing",
            "still_skipped",
            "newly_skipped",
            "newly_active",
            "added",
            "removed",
            "total_baseline_tests",
            "total_target_tests",
        )
        _require_keys(d, required, cls.__name__)
        return cls(
            regressed=int(d["regressed"]),
            fixed=int(d["fixed"]),
            still_failing=int(d["still_failing"]),
            still_passing=int(d["still_passing"]),
            still_skipped=int(d["still_skipped"]),
            newly_skipped=int(d["newly_skipped"]),
            newly_active=int(d["newly_active"]),
            added=int(d["added"]),
            removed=int(d["removed"]),
            total_baseline_tests=int(d["total_baseline_tests"]),
            total_target_tests=int(d["total_target_tests"]),
        )


@dataclass(slots=True, frozen=True)
class OutputDiffRecord:
    """Stdout/stderr diff via SHA-256 fingerprints + path references.

    Decision §4 (constraint #4): we deliberately do NOT embed diff text
    bodies in the JSON — a 10k-test pytest run can carry multi-MB
    stdout/stderr, which would blow the NFR-REG-002 5s re-parse budget.
    Determinism (NFR-REG-001) is preserved by SHA-256 of the captured
    artifact bytes; per-test failure context lives on
    ``TestResult.failure_reference``.

    All path fields are **Project-Store-relative** (decision §4 constraint
    #5), matching ``RunRecord.artifact_paths``. Each side independently
    nullable when its native artifact is missing — when ALL four are None
    the caller should set ``RegressionFactSet.output_diff = None`` (the
    null-pattern for "neither side had stdout/stderr at all").
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    baseline_stdout_sha256: str | None
    target_stdout_sha256: str | None
    baseline_stderr_sha256: str | None
    target_stderr_sha256: str | None
    stdout_identical: bool
    stderr_identical: bool
    baseline_stdout_path: str | None
    target_stdout_path: str | None
    baseline_stderr_path: str | None
    target_stderr_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_stdout_sha256": self.baseline_stdout_sha256,
            "target_stdout_sha256": self.target_stdout_sha256,
            "baseline_stderr_sha256": self.baseline_stderr_sha256,
            "target_stderr_sha256": self.target_stderr_sha256,
            "stdout_identical": self.stdout_identical,
            "stderr_identical": self.stderr_identical,
            "baseline_stdout_path": self.baseline_stdout_path,
            "target_stdout_path": self.target_stdout_path,
            "baseline_stderr_path": self.baseline_stderr_path,
            "target_stderr_path": self.target_stderr_path,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        # ``stdout_identical`` / ``stderr_identical`` are required (booleans
        # have no useful default); the SHA / path fields are read-tolerant
        # because the native artifact may genuinely be absent on one side.
        _require_keys(d, ("stdout_identical", "stderr_identical"), cls.__name__)
        return cls(
            baseline_stdout_sha256=_opt_str(d.get("baseline_stdout_sha256")),
            target_stdout_sha256=_opt_str(d.get("target_stdout_sha256")),
            baseline_stderr_sha256=_opt_str(d.get("baseline_stderr_sha256")),
            target_stderr_sha256=_opt_str(d.get("target_stderr_sha256")),
            stdout_identical=bool(d["stdout_identical"]),
            stderr_identical=bool(d["stderr_identical"]),
            baseline_stdout_path=_opt_str(d.get("baseline_stdout_path")),
            target_stdout_path=_opt_str(d.get("target_stdout_path")),
            baseline_stderr_path=_opt_str(d.get("baseline_stderr_path")),
            target_stderr_path=_opt_str(d.get("target_stderr_path")),
        )


@dataclass(slots=True, frozen=True)
class RegressionFactSet:
    """Structured Regression Facts for a (baseline, target) pair.

    Persisted at
    ``<store>/regression/pairs/run_<baseline_id>__run_<target_id>/regression_facts.json``
    — this directory naming is **load-bearing**: Memory's
    ``_availability_flags`` probe scans for ``run_<run_id>`` substrings in
    the pair directory names to flip ``MemoryEntry.has_regression_facts``.
    See decision §1 and ``src/novetest/memory/store.py:_any_regression_pair_exists``.

    ``coverage_change`` is the verbatim ``CoverageDelta.to_dict()`` payload
    when both runs have Coverage Facts; ``None`` otherwise. Read-side
    re-validates the embedded ``schema_version`` (handled at the retrieval
    layer per decision §C.6 — this dataclass just stores the dict).
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    baseline_run_reference: RunReference
    target_run_reference: RunReference
    baseline_engine_name: str
    target_engine_name: str
    baseline_engine_version: str | None
    target_engine_version: str | None
    derived_at: int
    summary: RegressionSummary
    test_transitions: tuple[TestTransition, ...]
    output_diff: OutputDiffRecord | None
    coverage_change: dict[str, Any] | None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "baseline_run_reference": self.baseline_run_reference.to_dict(),
            "target_run_reference": self.target_run_reference.to_dict(),
            "baseline_engine_name": self.baseline_engine_name,
            "target_engine_name": self.target_engine_name,
            "baseline_engine_version": self.baseline_engine_version,
            "target_engine_version": self.target_engine_version,
            "derived_at": self.derived_at,
            "summary": self.summary.to_dict(),
            "test_transitions": [t.to_dict() for t in self.test_transitions],
            "output_diff": (
                None if self.output_diff is None else self.output_diff.to_dict()
            ),
            "coverage_change": (
                None if self.coverage_change is None else dict(self.coverage_change)
            ),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "baseline_run_reference",
            "target_run_reference",
            "baseline_engine_name",
            "target_engine_name",
            "derived_at",
            "summary",
            "test_transitions",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        output_diff_raw = d.get("output_diff")
        coverage_change_raw = d.get("coverage_change")
        return cls(
            baseline_run_reference=RunReference.from_dict(
                dict(d["baseline_run_reference"])
            ),
            target_run_reference=RunReference.from_dict(
                dict(d["target_run_reference"])
            ),
            baseline_engine_name=str(d["baseline_engine_name"]),
            target_engine_name=str(d["target_engine_name"]),
            baseline_engine_version=_opt_str(d.get("baseline_engine_version")),
            target_engine_version=_opt_str(d.get("target_engine_version")),
            derived_at=int(d["derived_at"]),
            summary=RegressionSummary.from_dict(dict(d["summary"])),
            test_transitions=tuple(
                TestTransition.from_dict(dict(t)) for t in d["test_transitions"]
            ),
            output_diff=(
                None
                if output_diff_raw is None
                else OutputDiffRecord.from_dict(dict(output_diff_raw))
            ),
            coverage_change=(
                None if coverage_change_raw is None else dict(coverage_change_raw)
            ),
            warnings=tuple(str(w) for w in (d.get("warnings") or ())),
            metadata=dict(d.get("metadata") or {}),
            schema_version=int(schema_version),
        )


# --- internals ---------------------------------------------------------------


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
