"""Replay Result domain model.

Canonical persisted result of a Replay Attempt: re-executing a prior Run
under reconstructed conditions and classifying reproducibility against the
original Run (REQ-REP-003 / REQ-REP-004).

Promoted from the transient placeholder that lived in
``orchestration/recommendation/fact_bundle.py`` (Phase 6 entry slice) to a
first-class model here (Phase 5 entry slice). The five binding fields
(``run_reference`` / ``classification`` / ``reruns_total`` /
``reruns_failed`` / ``test_id``) are pinned by the recommendation
synthesizer's ``categories.py::match_flaky_suspected`` matcher; the
``fact_bundle.py`` module now re-imports this type so existing callers of
``from ...fact_bundle import ReplayResult`` keep working.

Persisted at
``<store>/replay/results/run_<original_run_id>/replay_result.json`` — this
filename is **load-bearing**: Memory's ``_availability_flags`` probe checks
for exactly this path to auto-flip ``MemoryEntry.has_replay_result``.

"Reproducible" here means **reproducible under reconstructed conditions** —
the same governed Native Engine path against the original Test Target — NOT
"reproducible against arbitrary future workspace state". A run classified
``reproducible`` may still diverge if the workspace is later mutated; the
classification is a statement about the replay session, not a guarantee.

Source of truth for attributes:
- ``design/requirements-analysis/domain-model.md`` (Replay Result + Replay Attempt)
- ``design/interace-contract/replay.md``
- ``agent-comms/tasks/replay-team-2026-06-02-phase5-entry-replay-engine.md`` §1.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

from novetest.models.run_reference import RunReference


SCHEMA_VERSION: int = 1

# Closed classification vocabulary (REQ-REP-003). Kept here as the single
# source of truth; ``fact_bundle.py`` re-exports it for the synthesizer.
REPLAY_CLASSIFICATIONS: frozenset[str] = frozenset(
    {"reproducible", "inconsistent", "unable_to_replay"}
)

# Closed reason vocabulary for the ``unable_to_replay`` classification. These
# are distinct from ``replay.errors.ReplayUnavailable`` reasons: those mark a
# replay that could NOT be attempted (a user/engine error surface), while
# these annotate a *successful* ``unable_to_replay`` classification — a valid
# REQ-REP-003 outcome, not an error.
REPLAY_UNABLE_REASONS: frozenset[str] = frozenset(
    {
        # No rerun was attempted at all (``reruns=0`` requested).
        "no-replayed-runs",
        # Every rerun attempt errored: parsed reruns with an errored status
        # (e.g. the Test Target no longer resolves, so the native engine
        # collects nothing) and/or reruns that crashed without producing a
        # parseable native result (counted as errored attempts per Q2
        # Option A, W2/S38).
        "replay-run-errored",
    }
)


@dataclass(slots=True, frozen=True)
class ReplayResult:
    """Classification of a Replay Attempt against its original Run.

    The five required fields are the binding minimum the recommendation
    synthesizer pins. The remaining fields are additive context for AI
    agents and downstream consumers — they MUST NOT be removed without a
    synchronized synthesizer change (a PM decision).

    - ``run_reference``           — the **original** Run's reference (the run
                                     being replayed). Always present.
    - ``classification``          — closed enum (``REPLAY_CLASSIFICATIONS``).
    - ``reruns_total``            — number of rerun ATTEMPTS in this session
                                     (>= 0). Includes attempts that crashed
                                     without a parseable native result (Q2
                                     Option A, W2/S38); only parsed reruns
                                     are persisted as Memory Entries.
    - ``reruns_failed``           — count of rerun attempts whose run-level
                                     outcome differed from the original
                                     (0 <= reruns_failed <= reruns_total).
    - ``test_id``                 — focal divergent test nodeid when exactly
                                     one test caused an ``inconsistent``
                                     result; ``None`` otherwise.
    - ``replayed_run_reference``  — the reference of the first PARSED
                                     replay-execution Run Record (``None``
                                     when no parseable replay run was
                                     produced). REQ-REP-004 slot.
    - ``per_rerun_outcomes``      — run-level outcome per rerun attempt, in
                                     order (e.g. ``("passed", "errored",
                                     "passed")``; crashed attempts appear as
                                     ``"errored"``).
    - ``consistency_summary``     — counts powering the classification
                                     (``original_passed`` / ``replay_passed`` /
                                     ``replay_failed`` / ``replay_errored`` ...).
    - ``attempted_at``            — epoch-millisecond timestamp of the replay
                                     attempt (0 when produced by the pure
                                     classifier without a clock).
    - ``reason``                  — closed enum (``REPLAY_UNABLE_REASONS``) when
                                     ``classification == "unable_to_replay"``;
                                     ``None`` otherwise.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_reference: RunReference
    classification: str
    reruns_total: int
    reruns_failed: int
    test_id: str | None = None
    replayed_run_reference: RunReference | None = None
    per_rerun_outcomes: tuple[str, ...] = ()
    consistency_summary: dict[str, int] = field(default_factory=dict)
    attempted_at: int = 0
    reason: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.classification not in REPLAY_CLASSIFICATIONS:
            raise ValueError(
                f"Invalid ReplayResult.classification={self.classification!r}; "
                f"expected one of {sorted(REPLAY_CLASSIFICATIONS)!r}"
            )
        if self.reruns_total < 0:
            raise ValueError(
                f"ReplayResult.reruns_total must be >= 0, got {self.reruns_total!r}"
            )
        if not 0 <= self.reruns_failed <= self.reruns_total:
            raise ValueError(
                f"ReplayResult.reruns_failed={self.reruns_failed!r} out of range "
                f"[0, reruns_total={self.reruns_total!r}]"
            )
        if self.reason is not None and self.reason not in REPLAY_UNABLE_REASONS:
            raise ValueError(
                f"Invalid ReplayResult.reason={self.reason!r}; expected None or "
                f"one of {sorted(REPLAY_UNABLE_REASONS)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_reference": self.run_reference.to_dict(),
            "classification": self.classification,
            "reruns_total": self.reruns_total,
            "reruns_failed": self.reruns_failed,
            "test_id": self.test_id,
            "replayed_run_reference": (
                None
                if self.replayed_run_reference is None
                else self.replayed_run_reference.to_dict()
            ),
            "per_rerun_outcomes": list(self.per_rerun_outcomes),
            "consistency_summary": dict(self.consistency_summary),
            "attempted_at": self.attempted_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "run_reference",
            "classification",
            "reruns_total",
            "reruns_failed",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        replayed_raw = d.get("replayed_run_reference")
        test_id_raw = d.get("test_id")
        reason_raw = d.get("reason")
        per_rerun_raw = d.get("per_rerun_outcomes") or []
        summary_raw = d.get("consistency_summary") or {}
        return cls(
            run_reference=RunReference.from_dict(dict(d["run_reference"])),
            classification=str(d["classification"]),
            reruns_total=int(d["reruns_total"]),
            reruns_failed=int(d["reruns_failed"]),
            test_id=None if test_id_raw is None else str(test_id_raw),
            replayed_run_reference=(
                None
                if replayed_raw is None
                else RunReference.from_dict(dict(replayed_raw))
            ),
            per_rerun_outcomes=tuple(str(o) for o in per_rerun_raw),
            consistency_summary={str(k): int(v) for k, v in summary_raw.items()},
            attempted_at=int(d.get("attempted_at", 0)),
            reason=None if reason_raw is None else str(reason_raw),
            schema_version=int(schema_version),
        )


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
