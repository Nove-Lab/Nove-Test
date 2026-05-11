"""Test Result domain model.

Individual test outcome associated with a Run Record. See
`design/requirements-analysis/domain-model.md` Test Result entry for
attribute source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self


SCHEMA_VERSION: int = 1


@dataclass(slots=True, frozen=True)
class TestResult:
    """One test outcome as normalized from a Native Result.

    - `node_id` mirrors the native engine's stable test identifier (pytest
      nodeid, jest test path, JUnit fully-qualified method name, etc.).
    - `outcome` is the normalized result: typically one of
      ``passed | failed | skipped | xfailed | xpassed | errored``. The set
      is intentionally not enum-locked at v1 to keep new engines from forcing
      schema bumps; validation belongs at the boundary.
    - `duration_ms` is the wall-clock test duration in milliseconds when the
      native engine reports it.
    - `failure_reference` is an opaque handle (path or blob hash) into the
      stored Native Result for callers that need the full failure payload.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION
    __test__: ClassVar[bool] = False

    node_id: str
    outcome: str
    duration_ms: int | None = None
    failure_reference: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "outcome": self.outcome,
            "duration_ms": self.duration_ms,
            "failure_reference": self.failure_reference,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        _require_keys(d, ("schema_version", "node_id", "outcome"), cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        duration_raw = d.get("duration_ms")
        failure_ref_raw = d.get("failure_reference")
        return cls(
            node_id=str(d["node_id"]),
            outcome=str(d["outcome"]),
            duration_ms=None if duration_raw is None else int(duration_raw),
            failure_reference=None if failure_ref_raw is None else str(failure_ref_raw),
            schema_version=int(schema_version),
        )


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
