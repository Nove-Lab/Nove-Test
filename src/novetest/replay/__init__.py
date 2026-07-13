"""Replay engine — re-execute a prior Run and classify reproducibility.

Replay reconstructs a prior run's context from stored evidence, re-executes
it through the **same governed Run path** (``run/execute_with_engine_context``,
REQ-REP-002) one or more times (``--reruns``), and classifies the result as
``reproducible`` / ``inconsistent`` / ``unable_to_replay`` (REQ-REP-003).
Replay produces facts only — it neither prescribes a fix nor implements an
independent test runner.

"Reproducible" means **reproducible under reconstructed conditions**, not a
guarantee against arbitrary future workspace state (see
``models/replay_result.py``).

Public API mirrors the other engines' surfaces
(``coverage/__init__.py`` / ``localization/__init__.py``):

- ``replay_run``                — engine entry point (reconstruct → rerun
                                   loop → classify → persist).
- ``reconstruct_replay_context`` — resolve target + native engine context.
- ``classify_replay_consistency`` — pure classification over rerun
                                   attempts (Run Records + crashed-rerun
                                   markers).
- ``get_replay_result``         — cache-only read.
- ``check_replay_availability`` — eligibility probe (bool).

Plus the discriminator type callers ``isinstance``-match for the unavailable
outcome (``ReplayUnavailable`` + its ``REASON_*`` constants) and the
``ReplayContext`` reconstruction value.

The canonical ``ReplayResult`` model lives at ``models/replay_result.py``.
"""

from novetest.replay.classifier import classify_replay_consistency
from novetest.replay.context import ReplayContext, reconstruct_replay_context
from novetest.replay.engine import replay_run
from novetest.replay.errors import (
    KNOWN_REASONS,
    REASON_CONTEXT_RECONSTRUCTION_FAILED,
    REASON_ENGINE_NOT_READY,
    REASON_MISSING_DERIVED_FACTS,
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    REASON_TOMBSTONED_ORIGINAL,
    ReplayUnavailable,
)
from novetest.replay.persistence import (
    read_replay_result_raw,
    replay_result_path,
    write_replay_result,
)
from novetest.replay.retrieval import check_replay_availability, get_replay_result


__all__ = [
    "KNOWN_REASONS",
    "REASON_CONTEXT_RECONSTRUCTION_FAILED",
    "REASON_ENGINE_NOT_READY",
    "REASON_MISSING_DERIVED_FACTS",
    "REASON_ORIGINAL_NOT_FOUND",
    "REASON_TARGET_MISSING",
    "REASON_TOMBSTONED_ORIGINAL",
    "ReplayContext",
    "ReplayUnavailable",
    "check_replay_availability",
    "classify_replay_consistency",
    "get_replay_result",
    "read_replay_result_raw",
    "reconstruct_replay_context",
    "replay_result_path",
    "replay_run",
    "write_replay_result",
]
