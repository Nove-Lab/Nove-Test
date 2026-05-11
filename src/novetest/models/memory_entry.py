"""Memory Entry domain model.

Stored evidence package for a run: the Run Record plus per-fact availability
flags that describe which derived facts (Coverage / Regression / Localization
/ Replay) and tombstone state are currently retrievable for the run.

Source of truth: `design/requirements-analysis/domain-model.md` (Memory
Entry) and `design/interace-contract/memory.md` §2 (availabilityState).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self

from novetest.models.run_record import RunRecord


SCHEMA_VERSION: int = 1


@dataclass(slots=True, frozen=True)
class MemoryEntry:
    """Persisted Memory Entry for one run.

    ``entry_id`` and ``run_record.run_reference.run_id`` are equal in the v1
    Project Store; both are kept on the wire to preserve the domain-model
    distinction between Memory Entry identity and Run Reference identity.

    The four ``has_*`` booleans summarize availability of derived facts so
    `memory list` and `memory show` can short-circuit a full availability
    probe. ``tombstoned_at`` is non-null exactly when the entry has been
    soft-deleted (Run Reference remains resolvable for Evidence Citation).
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    entry_id: str
    run_record: RunRecord
    stored_at: int
    has_coverage_facts: bool = False
    has_regression_facts: bool = False
    has_localization_findings: bool = False
    has_replay_result: bool = False
    tombstoned_at: int | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "run_record": self.run_record.to_dict(),
            "stored_at": self.stored_at,
            "has_coverage_facts": self.has_coverage_facts,
            "has_regression_facts": self.has_regression_facts,
            "has_localization_findings": self.has_localization_findings,
            "has_replay_result": self.has_replay_result,
            "tombstoned_at": self.tombstoned_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = ("schema_version", "entry_id", "run_record", "stored_at")
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        tombstoned_raw = d.get("tombstoned_at")
        return cls(
            entry_id=str(d["entry_id"]),
            run_record=RunRecord.from_dict(dict(d["run_record"])),
            stored_at=int(d["stored_at"]),
            has_coverage_facts=bool(d.get("has_coverage_facts", False)),
            has_regression_facts=bool(d.get("has_regression_facts", False)),
            has_localization_findings=bool(d.get("has_localization_findings", False)),
            has_replay_result=bool(d.get("has_replay_result", False)),
            tombstoned_at=None if tombstoned_raw is None else int(tombstoned_raw),
            schema_version=int(schema_version),
        )


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
