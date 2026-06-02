"""``get_replay_result`` + ``check_replay_availability`` unit tests.

Uses a real ``tmp_path``-backed Project Store and ``store_run_evidence`` /
``delete_run_evidence`` through the public Memory seams — no mocking.

Mirrors ``tests/unit/localization/test_retrieval.py`` in structure.
"""

from __future__ import annotations

from pathlib import Path

from novetest.memory.project_store import create_project_store
from novetest.memory.store import delete_run_evidence, store_run_evidence
from novetest.models.replay_result import ReplayResult
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.replay.errors import REASON_MISSING_DERIVED_FACTS, ReplayUnavailable
from novetest.replay.persistence import write_replay_result
from novetest.replay.retrieval import check_replay_availability, get_replay_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_REF = RunReference(
    run_id="01HRETRIEVE0000000000000RR", created_at=1_700_000_000_000
)


def _make_run_record(ref: RunReference, status: str = "passed") -> RunRecord:
    """Build a minimal live ``RunRecord`` for the given reference."""
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status=status,
        started_at=ref.created_at,
        test_results=(
            TestResult(node_id="tests/a.py::test_it", outcome=status, duration_ms=5),
        ),
    )


def _make_replay_result(ref: RunReference) -> ReplayResult:
    """Build a minimal valid ``ReplayResult`` for the given reference."""
    return ReplayResult(
        run_reference=ref,
        classification="reproducible",
        reruns_total=2,
        reruns_failed=0,
        per_rerun_outcomes=("passed", "passed"),
        consistency_summary={
            "original_passed": 1,
            "original_failed": 0,
            "replay_passed": 2,
            "replay_failed": 0,
            "replay_errored": 0,
        },
        attempted_at=1_748_000_000_000,
    )


def _seed_live_run(
    store_path: Path, ref: RunReference, status: str = "passed"
) -> None:
    """Store a live run record in the Project Store at ``store_path``."""
    from novetest.memory.project_store import get_project_store_state

    store = get_project_store_state(store_path)
    store_run_evidence(store, _make_run_record(ref, status=status))


# ---------------------------------------------------------------------------
# get_replay_result — cache absent → ReplayUnavailable(missing-derived-facts)
# ---------------------------------------------------------------------------


def test_get_returns_unavailable_when_no_file(tmp_path: Path) -> None:
    """``get_replay_result`` returns ``ReplayUnavailable(reason="missing-derived-facts")``
    when no ``replay_result.json`` exists for the run.

    This is the "no Replay Attempt has been made" path; the caller should
    invoke ``replay_run`` to produce one.
    """
    store = create_project_store(tmp_path)
    result = get_replay_result(store, _DEFAULT_REF)

    assert isinstance(result, ReplayUnavailable)
    assert result.reason == REASON_MISSING_DERIVED_FACTS
    assert result.run_reference == _DEFAULT_REF


def test_get_unavailable_has_populated_run_reference(tmp_path: Path) -> None:
    """The cache-empty ``ReplayUnavailable`` has ``run_reference`` set so the
    caller can identify which run needs a Replay Attempt."""
    store = create_project_store(tmp_path)
    ref = RunReference(run_id="01HRET0000000000000000R2", created_at=1_700_000_000_001)
    result = get_replay_result(store, ref)

    assert isinstance(result, ReplayUnavailable)
    assert result.run_reference == ref


# ---------------------------------------------------------------------------
# get_replay_result — cache present → ReplayResult
# ---------------------------------------------------------------------------


def test_get_returns_replay_result_after_write(tmp_path: Path) -> None:
    """``get_replay_result`` returns the stored ``ReplayResult`` after a write."""
    store = create_project_store(tmp_path)
    expected = _make_replay_result(_DEFAULT_REF)
    write_replay_result(store, _DEFAULT_REF, expected)

    result = get_replay_result(store, _DEFAULT_REF)

    assert isinstance(result, ReplayResult)
    assert result == expected


def test_get_returns_correct_classification(tmp_path: Path) -> None:
    """Classification is preserved across write → read."""
    store = create_project_store(tmp_path)
    ref = RunReference(run_id="01HRET0000000000000000R3", created_at=1_700_000_000_002)
    replay = ReplayResult(
        run_reference=ref,
        classification="inconsistent",
        reruns_total=3,
        reruns_failed=1,
        test_id="tests/test_flaky.py::test_flaky",
        per_rerun_outcomes=("passed", "failed", "passed"),
        consistency_summary={"original_passed": 1, "replay_passed": 2, "replay_failed": 1},
        attempted_at=1_748_000_000_000,
    )
    write_replay_result(store, ref, replay)

    result = get_replay_result(store, ref)

    assert isinstance(result, ReplayResult)
    assert result.classification == "inconsistent"
    assert result.test_id == "tests/test_flaky.py::test_flaky"


# ---------------------------------------------------------------------------
# check_replay_availability — unknown run → False
# ---------------------------------------------------------------------------


def test_availability_unknown_run_returns_false(tmp_path: Path) -> None:
    """``check_replay_availability`` returns ``False`` for a run with no evidence."""
    store = create_project_store(tmp_path)
    unknown = RunReference(
        run_id="01HUNKNOWN0000000000000ZZ", created_at=1_700_000_000_000
    )
    assert check_replay_availability(store, unknown) is False


# ---------------------------------------------------------------------------
# check_replay_availability — live stored run → True
# ---------------------------------------------------------------------------


def test_availability_stored_live_run_returns_true(tmp_path: Path) -> None:
    """A non-tombstoned live run → ``check_replay_availability`` returns ``True``.

    The workspace path must exist (it is the parent of the ``.novetest/``
    store directory, which is ``tmp_path`` in this case).
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = RunReference(run_id="01HRET0000000000000000R4", created_at=1_700_000_000_003)
    store_run_evidence(store, _make_run_record(ref))

    assert check_replay_availability(store, ref) is True


# ---------------------------------------------------------------------------
# check_replay_availability — tombstoned run → False
# ---------------------------------------------------------------------------


def test_availability_tombstoned_run_returns_false(tmp_path: Path) -> None:
    """A tombstoned run → ``check_replay_availability`` returns ``False``.

    Tombstoned runs are intentionally non-replayable (the original run was
    deleted); ``reconstruct_replay_context`` maps this to
    ``ReplayUnavailable(reason="tombstoned-original")``.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = RunReference(run_id="01HRET0000000000000000R5", created_at=1_700_000_000_004)
    store_run_evidence(store, _make_run_record(ref))
    # Tombstone the run via the Memory seam.
    delete_run_evidence(store, ref)

    assert check_replay_availability(store, ref) is False
