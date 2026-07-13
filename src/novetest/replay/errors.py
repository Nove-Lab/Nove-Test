"""Shared result types for Replay engine operations.

Mirrors ``src/novetest/coverage/results.py`` / ``localization/results.py`` /
``regression/results.py``: an *unavailable* outcome is a discriminator-pattern
value (callers ``isinstance``-match ``ReplayUnavailable``) rather than an
exception, so the engine boundary stays total and composes without try/except.

``ReplayUnavailable`` marks a replay that **could not be attempted or whose
result cannot be served** — a user/engine error surface (bad run_id, missing
engine, empty cache). It is distinct from a *successful* ``unable_to_replay``
classification (a valid ``ReplayResult`` per REQ-REP-003): that one means
"we replayed and the run could not reproduce", and is NOT an error.

Channel policy (codified W2/S39, ``design/interace-contract/replay.md``):
``replay`` is an EXECUTABLE verb — like ``run`` / ``test`` it refuses engine
absence/misconfiguration on the ERRORS channel (``ok: false``, exit 4). The
pure read/derive verbs (``coverage`` / ``regression`` / ``localization``)
instead report unavailability on the DATA channel (``ok: true``, exit 0)
with a documented ``reason`` — replay only borrows that data-channel shape
for its non-error reasons below (exit 0), never for engine absence.

Closed ``reason`` vocabulary and the exit-code split each reason maps to in
``cli/app.py::_build_replay_envelope`` (rationale recorded in the handoff):

- ``original-not-found``            — no live/tombstoned record for the ref.
                                       **User error → exit 2** (stale run_id).
- ``tombstoned-original``           — the original run was deleted (tombstoned);
                                       it cannot be re-executed. **Structured
                                       outcome → exit 0** (``kind: unavailable``).
- ``context-reconstruction-failed`` — stored evidence exists but the replay
                                       context could not be rebuilt. **Structured
                                       outcome → exit 0**.
- ``engine-not-ready``              — the native engine is missing/misconfigured
                                       in the workspace at replay time.
                                       **Engine error → exit 4**.
- ``target-missing``                — the workspace itself can no longer resolve
                                       the Test Target's workspace path.
                                       **Engine error → exit 4**.
- ``missing-derived-facts``         — cache-only read found no
                                       ``replay_result.json`` (no Replay Attempt
                                       has been made). **Structured outcome →
                                       exit 0**; recoverable via ``replay_run``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from novetest.models.run_reference import RunReference


REASON_ORIGINAL_NOT_FOUND: Final[str] = "original-not-found"
REASON_TOMBSTONED_ORIGINAL: Final[str] = "tombstoned-original"
REASON_CONTEXT_RECONSTRUCTION_FAILED: Final[str] = "context-reconstruction-failed"
REASON_ENGINE_NOT_READY: Final[str] = "engine-not-ready"
REASON_TARGET_MISSING: Final[str] = "target-missing"
REASON_MISSING_DERIVED_FACTS: Final[str] = "missing-derived-facts"

KNOWN_REASONS: frozenset[str] = frozenset(
    {
        REASON_ORIGINAL_NOT_FOUND,
        REASON_TOMBSTONED_ORIGINAL,
        REASON_CONTEXT_RECONSTRUCTION_FAILED,
        REASON_ENGINE_NOT_READY,
        REASON_TARGET_MISSING,
        REASON_MISSING_DERIVED_FACTS,
    }
)


@dataclass(slots=True, frozen=True)
class ReplayUnavailable:
    """Explicit unavailable outcome for a Replay operation.

    Returned (not raised) by ``replay_run`` / ``reconstruct_replay_context`` /
    ``get_replay_result`` when a Replay Result cannot be produced or served.
    ``run_reference`` is the **original** run's reference, populated when
    known; it is ``None`` only when the reference itself could not be
    resolved.
    """

    run_reference: RunReference | None
    reason: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.reason not in KNOWN_REASONS:
            raise ValueError(
                f"Invalid ReplayUnavailable.reason={self.reason!r}; "
                f"expected one of {sorted(KNOWN_REASONS)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a 3-key dict for envelope projection.

        All three keys are ALWAYS present — ``run_reference`` and ``detail``
        are emitted as ``null`` when ``None`` rather than omitted, so
        consumers can rely on key presence and only branch on value
        nullability. Mirrors ``LocalizationUnavailable.to_dict()``.
        """
        return {
            "run_reference": (
                None if self.run_reference is None else self.run_reference.to_dict()
            ),
            "reason": self.reason,
            "detail": self.detail,
        }
