"""``classify_replay_consistency`` — exhaustive table tests.

This is the most important test module for the Replay engine: the classifier
is a **pure function** (no I/O, no clock), so every case can be expressed as
a simple call-and-assert without any test setup cost.

Thresholding policy pinned here (strict, v1):
  ANY replay run whose run-level outcome differs from the original run's
  outcome makes the whole session ``inconsistent``.  One divergent rerun is
  sufficient — there is no majority-vote forgiveness.  Rationale: the user's
  mental model is a yes/no reproducibility question; a minority vote would
  silently hide real non-determinism.
"""

from __future__ import annotations

from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.replay.classifier import classify_replay_consistency


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref(run_id: str, *, created_at: int = 1_700_000_000_000) -> RunReference:
    """Return a minimal ``RunReference`` for the given ``run_id``."""
    return RunReference(run_id=run_id, created_at=created_at)


def _make_record(
    run_id: str,
    status: str,
    test_results: tuple[TestResult, ...] = (),
    *,
    created_at: int = 1_700_000_000_000,
) -> RunRecord:
    """Build a synthetic ``RunRecord`` with the given status and test results.

    Keeps the fixture minimal — only the fields the classifier touches.
    """
    return RunRecord(
        run_reference=_ref(run_id, created_at=created_at),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=created_at,
    )


def _make_record_with_tests(
    run_id: str,
    status: str,
    test_results: tuple[TestResult, ...],
    *,
    created_at: int = 1_700_000_000_000,
) -> RunRecord:
    """Build a ``RunRecord`` that carries test-level results (for focal-test tests)."""
    return RunRecord(
        run_reference=_ref(run_id, created_at=created_at),
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=created_at,
        test_results=test_results,
    )


# ---------------------------------------------------------------------------
# Case 1: original passed + all reruns passed → reproducible
# ---------------------------------------------------------------------------


def test_all_reruns_passed_reproducible() -> None:
    """original passed + all reruns passed → classification is ``reproducible``.

    - ``reruns_failed`` must be 0 (no divergence at all).
    - ``test_id`` must be ``None`` (no focal divergent test).
    - ``replayed_run_reference`` must equal the FIRST replayed record's reference.
    - ``per_rerun_outcomes`` must be all ``"passed"``.
    - ``reason`` must be ``None`` (not an ``unable_to_replay`` outcome).
    """
    original = _make_record("01ORIG0000000000000000AA", "passed")
    reruns = [
        _make_record("01RERUN000000000000000A1", "passed"),
        _make_record("01RERUN000000000000000A2", "passed"),
        _make_record("01RERUN000000000000000A3", "passed"),
    ]

    result = classify_replay_consistency(original, reruns, attempted_at=0)

    assert result.classification == "reproducible"
    assert result.reruns_total == 3
    assert result.reruns_failed == 0
    assert result.test_id is None
    assert result.reason is None
    assert result.per_rerun_outcomes == ("passed", "passed", "passed")
    assert result.replayed_run_reference == reruns[0].run_reference


# ---------------------------------------------------------------------------
# Case 2: original passed + one rerun failed → inconsistent (strict policy)
# ---------------------------------------------------------------------------


def test_one_rerun_failed_is_inconsistent() -> None:
    """original passed + one rerun failed (strict) → ``inconsistent``.

    Strict threshold: even a single divergent rerun makes the session
    ``inconsistent``.  ``reruns_failed`` must be exactly 1.
    """
    original = _make_record("01ORIG0000000000000000BB", "passed")
    reruns = [
        _make_record("01RERUN000000000000000B1", "passed"),
        _make_record("01RERUN000000000000000B2", "failed"),  # one diverges
        _make_record("01RERUN000000000000000B3", "passed"),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.classification == "inconsistent"
    assert result.reruns_total == 3
    assert result.reruns_failed == 1
    assert result.replayed_run_reference == reruns[0].run_reference


# ---------------------------------------------------------------------------
# Case 3: exactly one diverging test nodeid → inconsistent with focal test_id
# ---------------------------------------------------------------------------


def test_single_diverging_test_sets_test_id() -> None:
    """original passed + exactly one diverging nodeid → test_id = that nodeid.

    When every divergence across all replay runs traces back to a single test
    nodeid, ``test_id`` names it so the AI consumer can act on it.
    """
    original = _make_record_with_tests(
        "01ORIG0000000000000000CC",
        "passed",
        (
            TestResult(node_id="tests/test_a.py::test_stable", outcome="passed"),
            TestResult(node_id="tests/test_a.py::test_flaky", outcome="passed"),
        ),
    )
    # Both reruns diverge on the same nodeid → focal test resolved.
    reruns = [
        _make_record_with_tests(
            "01RERUN000000000000000C1",
            "failed",
            (
                TestResult(node_id="tests/test_a.py::test_stable", outcome="passed"),
                TestResult(node_id="tests/test_a.py::test_flaky", outcome="failed"),
            ),
        ),
        _make_record_with_tests(
            "01RERUN000000000000000C2",
            "failed",
            (
                TestResult(node_id="tests/test_a.py::test_stable", outcome="passed"),
                TestResult(node_id="tests/test_a.py::test_flaky", outcome="failed"),
            ),
        ),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.classification == "inconsistent"
    assert result.test_id == "tests/test_a.py::test_flaky"


# ---------------------------------------------------------------------------
# Case 4: multiple diverging nodeids → inconsistent with test_id=None
# ---------------------------------------------------------------------------


def test_multiple_diverging_tests_yields_no_focal_test_id() -> None:
    """original passed + multiple diverging nodeids → ``test_id`` is ``None``.

    When more than one test contributes to the divergence the classifier
    cannot name a single focal test; ``test_id`` stays ``None`` so the AI
    consumer is not misled.
    """
    original = _make_record_with_tests(
        "01ORIG0000000000000000DD",
        "passed",
        (
            TestResult(node_id="tests/test_a.py::test_one", outcome="passed"),
            TestResult(node_id="tests/test_a.py::test_two", outcome="passed"),
        ),
    )
    reruns = [
        _make_record_with_tests(
            "01RERUN000000000000000D1",
            "failed",
            (
                TestResult(node_id="tests/test_a.py::test_one", outcome="failed"),
                TestResult(node_id="tests/test_a.py::test_two", outcome="failed"),
            ),
        ),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.classification == "inconsistent"
    assert result.test_id is None


# ---------------------------------------------------------------------------
# Case 5: empty replayed_records → unable_to_replay (no-replayed-runs)
# ---------------------------------------------------------------------------


def test_empty_replayed_records_unable_to_replay() -> None:
    """No replay run produced at all → ``unable_to_replay`` with ``no-replayed-runs``.

    ``reruns_total`` must be 0 and ``replayed_run_reference`` must be ``None``
    because there is no first replay run to reference.
    """
    original = _make_record("01ORIG0000000000000000EE", "passed")

    result = classify_replay_consistency(original, [])

    assert result.classification == "unable_to_replay"
    assert result.reason == "no-replayed-runs"
    assert result.reruns_total == 0
    assert result.reruns_failed == 0
    assert result.replayed_run_reference is None
    assert result.per_rerun_outcomes == ()


# ---------------------------------------------------------------------------
# Case 6: all reruns errored → unable_to_replay (replay-run-errored)
# ---------------------------------------------------------------------------


def test_all_reruns_errored_unable_to_replay() -> None:
    """Every replay run has status ``errored`` → ``unable_to_replay`` with
    ``replay-run-errored``.

    ``errored`` status collapses to the ``errored`` run-level outcome via
    ``_overall_outcome``.  When ALL reruns are errored there is nothing
    meaningful to compare against the original — the classification is
    ``unable_to_replay``, not ``inconsistent``.

    ``replayed_run_reference`` must still be the FIRST replay run's reference
    (the reference is useful for audit even though the run errored).
    ``reruns_failed`` is 0 because the errored-all branch does not count
    divergences — these runs could not produce comparable results.
    """
    original = _make_record("01ORIG0000000000000000FF", "passed")
    reruns = [
        _make_record("01RERUN000000000000000F1", "errored"),
        _make_record("01RERUN000000000000000F2", "errored"),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.classification == "unable_to_replay"
    assert result.reason == "replay-run-errored"
    assert result.reruns_total == 2
    assert result.reruns_failed == 0
    assert result.replayed_run_reference == reruns[0].run_reference
    assert result.per_rerun_outcomes == ("errored", "errored")


# ---------------------------------------------------------------------------
# Case 7: consistency_summary counts are correct for a mixed case
# ---------------------------------------------------------------------------


def test_consistency_summary_counts_mixed_case() -> None:
    """``consistency_summary`` must accurately count original + replay outcomes.

    Mixed case: original passed, two reruns passed, one failed, one errored.
    Expected:
      original_passed=1, original_failed=0,
      replay_passed=2, replay_failed=1, replay_errored=1.
    """
    original = _make_record("01ORIG0000000000000000GG", "passed")
    reruns = [
        _make_record("01RERUN000000000000000G1", "passed"),
        _make_record("01RERUN000000000000000G2", "passed"),
        _make_record("01RERUN000000000000000G3", "failed"),
        _make_record("01RERUN000000000000000G4", "errored"),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.consistency_summary["original_passed"] == 1
    assert result.consistency_summary["original_failed"] == 0
    assert result.consistency_summary["replay_passed"] == 2
    assert result.consistency_summary["replay_failed"] == 1
    assert result.consistency_summary["replay_errored"] == 1


def test_consistency_summary_original_failed_counted() -> None:
    """``original_failed=1`` when the original run's status is ``failed``."""
    original = _make_record("01ORIG0000000000000000GH", "failed")
    reruns = [_make_record("01RERUN000000000000000H1", "failed")]

    result = classify_replay_consistency(original, reruns)

    assert result.consistency_summary["original_failed"] == 1
    assert result.consistency_summary["original_passed"] == 0


# ---------------------------------------------------------------------------
# Case 8: attempted_at passes through
# ---------------------------------------------------------------------------


def test_attempted_at_passes_through() -> None:
    """``attempted_at`` argument is forwarded verbatim into ``ReplayResult``."""
    original = _make_record("01ORIG0000000000000000HH", "passed")
    reruns = [_make_record("01RERUN000000000000000I1", "passed")]

    result = classify_replay_consistency(original, reruns, attempted_at=1_748_000_000_000)

    assert result.attempted_at == 1_748_000_000_000


def test_attempted_at_defaults_to_zero() -> None:
    """When ``attempted_at`` is not supplied it defaults to 0 (pure-classifier default)."""
    original = _make_record("01ORIG0000000000000000II", "passed")
    reruns = [_make_record("01RERUN000000000000000J1", "passed")]

    result = classify_replay_consistency(original, reruns)

    assert result.attempted_at == 0


# ---------------------------------------------------------------------------
# Case 9: original FAILED + all reruns failed → reproducible
# ---------------------------------------------------------------------------


def test_original_failed_all_reruns_failed_reproducible() -> None:
    """original failed + all reruns failed → ``reproducible``.

    Reproducibility is not a "did it pass?" question — it is a
    "did the reruns match the original?" question.  A consistently-failing
    run is just as reproducible as a consistently-passing one.
    """
    original = _make_record("01ORIG0000000000000000JJ", "failed")
    reruns = [
        _make_record("01RERUN000000000000000K1", "failed"),
        _make_record("01RERUN000000000000000K2", "failed"),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.classification == "reproducible"
    assert result.reruns_failed == 0
    assert result.test_id is None
    assert result.reason is None


# ---------------------------------------------------------------------------
# Case 10: replayed_run_reference equals the FIRST replayed record's reference
# ---------------------------------------------------------------------------


def test_replayed_run_reference_is_first_replay_record() -> None:
    """``replayed_run_reference`` MUST equal the first replayed record's reference.

    The classifier records the first replay run as the authoritative anchor
    for downstream consumers that want to drill into replay artifacts.
    """
    original = _make_record("01ORIG0000000000000000KK", "passed")
    first = _make_record("01RERUN000000000000000L1", "passed", created_at=1_700_000_001_000)
    second = _make_record("01RERUN000000000000000L2", "passed", created_at=1_700_000_002_000)
    third = _make_record("01RERUN000000000000000L3", "passed", created_at=1_700_000_003_000)

    result = classify_replay_consistency(original, [first, second, third])

    assert result.replayed_run_reference == first.run_reference
    assert result.replayed_run_reference != second.run_reference
    assert result.replayed_run_reference != third.run_reference


# ---------------------------------------------------------------------------
# Case 11: run_reference on the result equals the ORIGINAL run's reference
# ---------------------------------------------------------------------------


def test_result_run_reference_is_original() -> None:
    """``ReplayResult.run_reference`` must be the ORIGINAL run's reference.

    This is the run being *replayed* (the comparison baseline), not the
    replay-execution run.
    """
    original = _make_record("01ORIG0000000000000000LL", "passed")
    reruns = [_make_record("01RERUN000000000000000M1", "passed")]

    result = classify_replay_consistency(original, reruns)

    assert result.run_reference == original.run_reference
    assert result.run_reference != reruns[0].run_reference


# ---------------------------------------------------------------------------
# Case 12: per_rerun_outcomes tuple matches the order of replayed_records
# ---------------------------------------------------------------------------


def test_per_rerun_outcomes_ordering() -> None:
    """``per_rerun_outcomes`` mirrors the order of ``replayed_records``."""
    original = _make_record("01ORIG0000000000000000MM", "passed")
    reruns = [
        _make_record("01RERUN000000000000000N1", "passed"),
        _make_record("01RERUN000000000000000N2", "failed"),
        _make_record("01RERUN000000000000000N3", "passed"),
        _make_record("01RERUN000000000000000N4", "errored"),
    ]

    result = classify_replay_consistency(original, reruns)

    assert result.per_rerun_outcomes == ("passed", "failed", "passed", "errored")


# ---------------------------------------------------------------------------
# Case 13: non-errored mixed with errored reruns → inconsistent, not unable_to_replay
# ---------------------------------------------------------------------------


def test_one_errored_one_passed_not_unable_to_replay() -> None:
    """If at least one rerun is non-errored, the all-errored gate is not triggered.

    One errored + one passed (original passed): only the non-errored outcome
    matters for classification → ``reproducible`` (passed matches passed).
    The errored run does not contribute to ``reruns_failed`` because its
    outcome is not compared against the original.

    Wait — actually the errored rerun outcome != original ("passed") so it
    DOES contribute to reruns_failed under the strict divergence count.
    Verify this boundary precisely.
    """
    original = _make_record("01ORIG0000000000000000NN", "passed")
    reruns = [
        _make_record("01RERUN000000000000000O1", "passed"),
        _make_record("01RERUN000000000000000O2", "errored"),
    ]

    result = classify_replay_consistency(original, reruns)

    # Not all errored → all-errored gate not triggered.
    assert result.classification != "unable_to_replay"
    # The errored run's outcome ("errored") != original ("passed") → reruns_failed=1.
    assert result.reruns_failed == 1
    assert result.classification == "inconsistent"
