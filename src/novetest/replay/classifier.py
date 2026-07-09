"""``classify_replay_consistency`` — pure reproducibility classification.

Compares the original Run Record against the replay-execution Run Records
and produces a ``ReplayResult`` (REQ-REP-003). This is a **pure function**:
no I/O, no clock (the ``attempted_at`` stamp is injected by the caller), so
exhaustive table tests are cheap and the determinism contract is trivially
satisfied.

Thresholding policy (closed; v2-bumpable — see the brief §6.2):

  **strict** — ANY replay run whose run-level outcome differs from the
  original's outcome makes the whole session ``inconsistent``. One flake is
  enough for the answer to "is this run reproducible?" to be "no". Rationale:
  the user's mental model is a yes/no reproducibility question; a majority
  vote would hide real non-determinism.

Run-level outcome collapse (``_overall_outcome``): a Run Record's ``status``
is mapped to ``passed`` / ``failed`` / ``errored``. ``errored`` means the run
could not execute or collect meaningfully (e.g. the Test Target vanished, so
the native engine collected nothing) — distinct from a run that executed and
reported test failures.

Classification precedence:

1. ``unable_to_replay`` — no replay run was produced at all, OR **every**
   replay run errored. The original could not be reproduced because the
   replay could not run, not because outcomes diverged.
2. ``reproducible``     — every replay run's outcome matches the original's.
3. ``inconsistent``     — at least one replay run's outcome differs (strict).

When ``inconsistent`` and **exactly one** test nodeid is responsible for the
divergence across all replay runs, ``test_id`` names it; otherwise ``None``.
"""

from __future__ import annotations

from novetest.models import FAIL_LIKE_OUTCOMES
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


CLASSIFICATION_REPRODUCIBLE = "reproducible"
CLASSIFICATION_INCONSISTENT = "inconsistent"
CLASSIFICATION_UNABLE_TO_REPLAY = "unable_to_replay"

REASON_NO_REPLAYED_RUNS = "no-replayed-runs"
REASON_REPLAY_RUN_ERRORED = "replay-run-errored"

# Run-level outcomes a comparison ranges over. Anything that is not a clean
# pass/fail collapses to "errored".
_RUN_PASS = "passed"
_RUN_FAIL = "failed"
_RUN_ERRORED = "errored"

_FAILED_TEST_OUTCOMES: frozenset[str] = FAIL_LIKE_OUTCOMES  # SSoT: novetest.models (S25)


def classify_replay_consistency(
    original_record: RunRecord,
    replayed_records: list[RunRecord],
    *,
    attempted_at: int = 0,
) -> ReplayResult:
    """Classify replay reproducibility from the original + replay records.

    ``attempted_at`` is injected (epoch ms) so this function stays pure;
    the pure-classifier callers (unit tests) pass ``0``.
    """
    original_ref = original_record.run_reference
    replayed_ref: RunReference | None = (
        replayed_records[0].run_reference if replayed_records else None
    )

    original_outcome = _overall_outcome(original_record)
    rerun_outcomes = tuple(_overall_outcome(r) for r in replayed_records)

    consistency_summary = {
        "original_passed": 1 if original_outcome == _RUN_PASS else 0,
        "original_failed": 1 if original_outcome == _RUN_FAIL else 0,
        "replay_passed": sum(1 for o in rerun_outcomes if o == _RUN_PASS),
        "replay_failed": sum(1 for o in rerun_outcomes if o == _RUN_FAIL),
        "replay_errored": sum(1 for o in rerun_outcomes if o == _RUN_ERRORED),
    }

    # (1) unable_to_replay — nothing to compare, or every replay run errored.
    if not rerun_outcomes:
        return ReplayResult(
            run_reference=original_ref,
            classification=CLASSIFICATION_UNABLE_TO_REPLAY,
            reruns_total=0,
            reruns_failed=0,
            test_id=None,
            replayed_run_reference=None,
            per_rerun_outcomes=(),
            consistency_summary=consistency_summary,
            attempted_at=attempted_at,
            reason=REASON_NO_REPLAYED_RUNS,
        )
    if all(o == _RUN_ERRORED for o in rerun_outcomes):
        return ReplayResult(
            run_reference=original_ref,
            classification=CLASSIFICATION_UNABLE_TO_REPLAY,
            reruns_total=len(replayed_records),
            reruns_failed=0,
            test_id=None,
            replayed_run_reference=replayed_ref,
            per_rerun_outcomes=rerun_outcomes,
            consistency_summary=consistency_summary,
            attempted_at=attempted_at,
            reason=REASON_REPLAY_RUN_ERRORED,
        )

    # (2)/(3) strict divergence count: any rerun differing from the original.
    reruns_failed = sum(1 for o in rerun_outcomes if o != original_outcome)
    if reruns_failed == 0:
        classification = CLASSIFICATION_REPRODUCIBLE
        test_id: str | None = None
    else:
        classification = CLASSIFICATION_INCONSISTENT
        test_id = _focal_divergent_test(original_record, replayed_records)

    return ReplayResult(
        run_reference=original_ref,
        classification=classification,
        reruns_total=len(replayed_records),
        reruns_failed=reruns_failed,
        test_id=test_id,
        replayed_run_reference=replayed_ref,
        per_rerun_outcomes=rerun_outcomes,
        consistency_summary=consistency_summary,
        attempted_at=attempted_at,
        reason=None,
    )


def _overall_outcome(record: RunRecord) -> str:
    """Collapse a Run Record to a single run-level outcome token.

    ``passed`` / ``failed`` are taken from the normalized ``status``; any
    other status (notably ``errored`` from pytest's no-tests-collected /
    usage-error exit codes) collapses to ``errored``.
    """
    if record.status == _RUN_PASS:
        return _RUN_PASS
    if record.status == _RUN_FAIL:
        return _RUN_FAIL
    return _RUN_ERRORED


def _focal_divergent_test(
    original_record: RunRecord,
    replayed_records: list[RunRecord],
) -> str | None:
    """Return the single test nodeid responsible for divergence, else None.

    A test is "divergent" when its outcome in some replay run differs from
    its outcome in the original run (both runs must contain the nodeid).
    When exactly one nodeid diverges across all replay runs, it is the focal
    test; otherwise the divergence is spread (or untraceable) and we return
    ``None``.
    """
    original_outcomes = {
        tr.node_id: tr.outcome for tr in original_record.test_results
    }
    divergent: set[str] = set()
    for record in replayed_records:
        for tr in record.test_results:
            original = original_outcomes.get(tr.node_id)
            if original is not None and tr.outcome != original:
                divergent.add(tr.node_id)
    if len(divergent) == 1:
        return next(iter(divergent))
    return None
