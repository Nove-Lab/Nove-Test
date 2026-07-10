"""Run Record domain model.

Normalized representation of one test execution attempt. The Native Result
is preserved separately (under `.novetest/run/artifacts/<run_id>/`); this
record captures the normalized view plus opaque handles back to those raw
artifacts so callers can drill in without re-parsing.

Source of truth for attributes: `design/requirements-analysis/domain-model.md`
(Run Record + Native Engine context).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


SCHEMA_VERSION: int = 1


@dataclass(slots=True, frozen=True)
class RunRecord:
    """Normalized representation of one Run.

    Native Engine context is inlined (`engine_name`, `engine_version`,
    `ecosystem`) rather than nested as a separate model entity, because at
    v1 there is no behavior that requires Native Engine to round-trip on its
    own. `artifact_paths` is a name -> Project-Store-relative-path map
    (e.g. ``{"junit_xml": "run/artifacts/<run_id>/native/junit.xml"}``) so
    Memory can resolve raw payloads without engine-specific knowledge.

    ``stored_at`` (MEM-04) is the Memory engine's persistence stamp: the
    epoch-ms wall-clock instant ``store_run_evidence`` wrote the record. It is
    an additive-optional ``record.json`` key under the frozen ``schema_version
    == 1`` — the key is omitted (not ``null``) when unset, so every pre-change
    record round-trips byte-identically, and readers fall back to the file
    mtime for such legacy records. Producers (the Run engine) leave it ``None``;
    Memory stamps it at store time and keeps it OFF the nested wire projection
    (consumers read ``MemoryEntry.stored_at``, the established envelope slot).
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_reference: RunReference
    target_expression: str
    target_type: str
    engine_name: str
    ecosystem: str
    status: str
    started_at: int
    engine_version: str | None = None
    completed_at: int | None = None
    summary_counts: dict[str, int] = field(default_factory=dict)
    test_results: tuple[TestResult, ...] = field(default_factory=tuple)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    stored_at: int | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_reference": self.run_reference.to_dict(),
            "target_expression": self.target_expression,
            "target_type": self.target_type,
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "ecosystem": self.ecosystem,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "summary_counts": dict(self.summary_counts),
            "test_results": [tr.to_dict() for tr in self.test_results],
            "artifact_paths": dict(self.artifact_paths),
            "metadata": dict(self.metadata),
        }
        # Additive optional field: omitted entirely when unset (the
        # `pinned_engine` precedent), so a pre-MEM-04 record never grows a
        # key it did not have when re-serialized.
        if self.stored_at is not None:
            payload["stored_at"] = self.stored_at
        return payload

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "run_reference",
            "target_expression",
            "target_type",
            "engine_name",
            "ecosystem",
            "status",
            "started_at",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )

        engine_version_raw = d.get("engine_version")
        completed_at_raw = d.get("completed_at")
        stored_at_raw = d.get("stored_at")
        summary_counts_raw = d.get("summary_counts") or {}
        test_results_raw = d.get("test_results") or []
        artifact_paths_raw = d.get("artifact_paths") or {}
        metadata_raw = d.get("metadata") or {}

        return cls(
            run_reference=RunReference.from_dict(dict(d["run_reference"])),
            target_expression=str(d["target_expression"]),
            target_type=str(d["target_type"]),
            engine_name=str(d["engine_name"]),
            engine_version=None if engine_version_raw is None else str(engine_version_raw),
            ecosystem=str(d["ecosystem"]),
            status=str(d["status"]),
            started_at=int(d["started_at"]),
            completed_at=None if completed_at_raw is None else int(completed_at_raw),
            summary_counts={str(k): int(v) for k, v in summary_counts_raw.items()},
            test_results=tuple(TestResult.from_dict(dict(tr)) for tr in test_results_raw),
            artifact_paths={str(k): str(v) for k, v in artifact_paths_raw.items()},
            metadata=dict(metadata_raw),
            stored_at=None if stored_at_raw is None else int(stored_at_raw),
            schema_version=int(schema_version),
        )


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
