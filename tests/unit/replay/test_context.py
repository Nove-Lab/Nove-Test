"""``reconstruct_replay_context`` unit tests.

Tests the three outcomes documented in ``context.py``:

1. Success → ``ReplayContext`` with matching ``test_target`` and ``engine_context``.
2. Unknown run (no evidence) → ``ReplayUnavailable(reason="original-not-found")``.
3. Tombstoned run → ``ReplayUnavailable(reason="tombstoned-original")``.

All tests use a real ``tmp_path``-backed Project Store and the public Memory
seams (``store_run_evidence``, ``delete_run_evidence``).  The workspace path
must exist because ``reconstruct_replay_context`` checks ``workspace_path.is_dir()``.
"""

from __future__ import annotations

from pathlib import Path

from novetest.memory.project_store import create_project_store
from novetest.memory.store import delete_run_evidence, store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult
from novetest.replay.context import ReplayContext, reconstruct_replay_context
from novetest.replay.errors import (
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TOMBSTONED_ORIGINAL,
    ReplayUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_record(
    ref: RunReference,
    *,
    target_expression: str = "tests/",
    target_type: str = "dir",
    engine_name: str = "pytest",
    ecosystem: str = "python",
    engine_version: str | None = "8.2.0",
    status: str = "passed",
) -> RunRecord:
    """Build a minimal ``RunRecord`` for the given reference."""
    return RunRecord(
        run_reference=ref,
        target_expression=target_expression,
        target_type=target_type,
        engine_name=engine_name,
        engine_version=engine_version,
        ecosystem=ecosystem,
        status=status,
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/a.py::test_it", outcome="passed", duration_ms=5),
        ),
    )


def _ref(run_id: str, *, created_at: int = 1_700_000_000_000) -> RunReference:
    return RunReference(run_id=run_id, created_at=created_at)


# ---------------------------------------------------------------------------
# Success path: ReplayContext fields match the stored record
# ---------------------------------------------------------------------------


def test_success_returns_replay_context(tmp_path: Path) -> None:
    """A live, non-tombstoned run in a live workspace → ``ReplayContext`` returned."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AA")
    record = _make_run_record(ref)
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)

    assert isinstance(outcome, ReplayContext)


def test_success_original_record_is_stored_record(tmp_path: Path) -> None:
    """``ReplayContext.original_record`` must equal the record from store evidence."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AB")
    record = _make_run_record(ref, target_expression="tests/unit/", target_type="dir")
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)
    assert isinstance(outcome, ReplayContext)
    assert outcome.original_record.run_reference == ref


def test_success_test_target_expression_matches(tmp_path: Path) -> None:
    """``ReplayContext.test_target.target_expression`` matches the stored record."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AC")
    record = _make_run_record(ref, target_expression="tests/")
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)
    assert isinstance(outcome, ReplayContext)
    assert outcome.test_target.target_expression == "tests/"


def test_success_engine_context_engine_name_matches(tmp_path: Path) -> None:
    """``ReplayContext.engine_context.engine_name`` matches the stored record."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AD")
    record = _make_run_record(ref, engine_name="pytest")
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)
    assert isinstance(outcome, ReplayContext)
    assert outcome.engine_context.engine_name == "pytest"


def test_success_engine_context_ecosystem_matches(tmp_path: Path) -> None:
    """``ReplayContext.engine_context.ecosystem`` matches the stored record."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AE")
    record = _make_run_record(ref, ecosystem="python")
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)
    assert isinstance(outcome, ReplayContext)
    assert outcome.engine_context.ecosystem == "python"


def test_success_non_python_ecosystem(tmp_path: Path) -> None:
    """``ReplayContext`` is correctly constructed for a non-Python engine."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000AF")
    record = _make_run_record(ref, engine_name="cargo-test", ecosystem="rust")
    store_run_evidence(store, record)

    outcome = reconstruct_replay_context(store, ref)
    assert isinstance(outcome, ReplayContext)
    assert outcome.engine_context.engine_name == "cargo-test"
    assert outcome.engine_context.ecosystem == "rust"


# ---------------------------------------------------------------------------
# Unknown run → ReplayUnavailable(original-not-found)
# ---------------------------------------------------------------------------


def test_unknown_run_returns_original_not_found(tmp_path: Path) -> None:
    """No evidence for the reference → ``ReplayUnavailable(reason="original-not-found")``."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    unknown = _ref("01HUNKNOWN0000000000000ZZ")

    outcome = reconstruct_replay_context(store, unknown)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.reason == REASON_ORIGINAL_NOT_FOUND


def test_unknown_run_unavailable_has_run_reference(tmp_path: Path) -> None:
    """The ``ReplayUnavailable`` for an unknown run carries the supplied reference."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    unknown = _ref("01HUNKNOWN0000000000000ZZ")

    outcome = reconstruct_replay_context(store, unknown)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.run_reference == unknown


# ---------------------------------------------------------------------------
# Tombstoned run → ReplayUnavailable(tombstoned-original)
# ---------------------------------------------------------------------------


def test_tombstoned_run_returns_tombstoned_original(tmp_path: Path) -> None:
    """A tombstoned run → ``ReplayUnavailable(reason="tombstoned-original")``."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000BA")
    record = _make_run_record(ref)
    store_run_evidence(store, record)
    # Tombstone via Memory seam.
    delete_run_evidence(store, ref)

    outcome = reconstruct_replay_context(store, ref)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.reason == REASON_TOMBSTONED_ORIGINAL


def test_tombstoned_run_unavailable_has_run_reference(tmp_path: Path) -> None:
    """The ``ReplayUnavailable`` for a tombstoned run carries the original reference."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    ref = _ref("01HCTX0000000000000000BB")
    record = _make_run_record(ref)
    store_run_evidence(store, record)
    delete_run_evidence(store, ref)

    outcome = reconstruct_replay_context(store, ref)

    assert isinstance(outcome, ReplayUnavailable)
    assert outcome.run_reference == ref
