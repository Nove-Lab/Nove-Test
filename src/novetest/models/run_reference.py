"""Run Reference domain model.

Stable identifier used to retrieve, compare, replay, and cite a run. See
`design/requirements-analysis/domain-model.md` for the attribute source of
truth and `design/implementation-plan/foundations.md` §4 for the
`schema_version` policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self


SCHEMA_VERSION: int = 1


@dataclass(slots=True, frozen=True)
class RunReference:
    """Stable identifier for a single run.

    The `run_id` is supplied by the caller (ULID generation lives outside this
    model). `created_at` is the epoch-millisecond stamp that orders runs in
    Run History.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_id: str
    created_at: int
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        _require_keys(d, ("schema_version", "run_id", "created_at"), cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        return cls(
            run_id=str(d["run_id"]),
            created_at=int(d["created_at"]),
            schema_version=int(schema_version),
        )


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
