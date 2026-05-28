"""``resolve_latest_analyzable_run`` + ``derive_latest_localization`` unit tests.

Mirrors ``tests/unit/regression/test_baseline_resolution.py`` in shape:
each test seeds a real Project Store via ``create_project_store`` +
``store_run_evidence`` + (optional) ``write_coverage_facts`` +
``delete_run_evidence`` — no Memory / Coverage mocks. The probe
``check_localization_availability`` (consumed by
``resolve_latest_analyzable_run``) is itself unit-tested in
``test_retrieval.py``; here we exercise the composition.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from novetest.localization import derive as derive_module
from novetest.localization.derive import (
    derive_latest_localization,
    resolve_latest_analyzable_run,
)
from novetest.localization.persistence import localization_findings_path
from novetest.localization.results import (
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.localization.symbol_resolver import clear_resolver_cache
from novetest.memory.project_store import (
    create_project_store,
    get_project_store_state,
)
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet, FileCoverage
from novetest.models.localization_finding import LocalizationFinding
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


# Hand-picked timestamps so insertion order is independent of
# chronological order (OLD < MID < NEW).
_TS_OLD = 1_700_000_000_000
_TS_MID = 1_700_000_001_000
_TS_NEW = 1_700_000_002_000


# Three-function Python module with a deliberate bug on line 5 (in
# ``buggy``), used by the happy-path tests. Mirrors the ``_BUGGY_SOURCE``
# in ``test_derive.py``.
_BUGGY_SOURCE = (
    "def safe(x):\n"          # line 1
    "    return x + 1\n"      # line 2
    "\n"
    "def buggy(x):\n"         # line 4
    "    return x * 0\n"      # line 5 — the bug
    "\n"
    "def neutral(x):\n"       # line 7
    "    return x\n"          # line 8
)


def _ref(run_id: str, created_at: int) -> RunReference:
    return RunReference(run_id=run_id, created_at=created_at)


def _seed_analyzable_run(
    *,
    workspace: Path,
    run_reference: RunReference,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
) -> None:
    """Seed a single analyzable run on the given workspace + run_reference.

    Writes the buggy source, builds a 3-test ``RunRecord`` (2 passing +
    1 failing) with per-test coverage attribution. The store is created
    on first call; subsequent calls reuse it.
    """
    source_file = workspace / "src" / "calc.py"
    if not source_file.exists():
        write_python_module(source_file, _BUGGY_SOURCE)
        clear_resolver_cache()

    test_results = (
        TestResult(node_id="tests/test_calc.py::test_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_other_safe", outcome="passed", duration_ms=1),
        TestResult(node_id="tests/test_calc.py::test_buggy", outcome="failed", duration_ms=1),
    )
    record = make_record(test_results=test_results, run_reference=run_reference)
    coverage = make_coverage(
        files=(
            make_file(
                "src/calc.py",
                {
                    1: ("tests/test_calc.py::test_safe", "tests/test_calc.py::test_other_safe"),
                    2: ("tests/test_calc.py::test_safe", "tests/test_calc.py::test_other_safe"),
                    4: ("tests/test_calc.py::test_buggy",),
                    5: ("tests/test_calc.py::test_buggy",),
                },
            ),
        ),
        run_reference=run_reference,
    )

    if not (workspace / ".novetest").exists():
        store = create_project_store(workspace)
    else:
        store = get_project_store_state(workspace / ".novetest")
    store_run_evidence(store, record)
    # Coverage Facts are owned by the Coverage engine's persistence layer.
    from novetest.coverage.persistence import write_coverage_facts

    write_coverage_facts(store, coverage)


def _seed_unanalyzable_run(
    *,
    workspace: Path,
    run_reference: RunReference,
    make_record: Callable[..., RunRecord],
) -> None:
    """Seed a run with a failed test but NO coverage facts → unanalyzable."""
    record = make_record(
        test_results=(
            TestResult(
                node_id="tests/a.py::t", outcome="failed", duration_ms=1
            ),
        ),
        run_reference=run_reference,
    )
    if not (workspace / ".novetest").exists():
        store = create_project_store(workspace)
    else:
        store = get_project_store_state(workspace / ".novetest")
    store_run_evidence(store, record)


# --- resolve_latest_analyzable_run -------------------------------------------


def test_resolve_empty_store_returns_no_run_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    result = resolve_latest_analyzable_run(store)
    assert isinstance(result, LocalizationUnavailable)
    assert result.run_reference is None
    assert result.reason == REASON_NO_RUN_EVIDENCE
    assert result.detail == "no runs in store"


def test_resolve_all_non_analyzable_returns_run_not_analyzable_with_count(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
) -> None:
    """Three runs in the store, none with coverage → unavailable with the
    count of probed candidates in the detail."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_unanalyzable_run(
        workspace=workspace,
        run_reference=_ref("01OLDUN0000000000000000001", _TS_OLD),
        make_record=make_record,
    )
    _seed_unanalyzable_run(
        workspace=workspace,
        run_reference=_ref("01MIDUN0000000000000000002", _TS_MID),
        make_record=make_record,
    )
    _seed_unanalyzable_run(
        workspace=workspace,
        run_reference=_ref("01NEWUN0000000000000000003", _TS_NEW),
        make_record=make_record,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = resolve_latest_analyzable_run(store)
    assert isinstance(result, LocalizationUnavailable)
    assert result.run_reference is None
    assert result.reason == REASON_RUN_NOT_ANALYZABLE
    assert result.detail is not None
    assert "3" in result.detail  # 3 candidates probed


def test_resolve_returns_latest_analyzable_run(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
) -> None:
    """Two analyzable runs → newest is returned."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=_ref("01OLDAN0000000000000000001", _TS_OLD),
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=_ref("01NEWAN0000000000000000002", _TS_NEW),
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = resolve_latest_analyzable_run(store)
    assert isinstance(result, RunReference)
    assert result.run_id == "01NEWAN0000000000000000002"


def test_resolve_skips_tombstoned_latest_and_returns_next_analyzable(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
) -> None:
    """The newest run is tombstoned → resolver returns the prior analyzable."""
    from novetest.memory.store import delete_run_evidence

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=_ref("01OLDAN0000000000000000010", _TS_OLD),
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    latest_ref = _ref("01NEWAN0000000000000000020", _TS_NEW)
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=latest_ref,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    store = get_project_store_state(workspace / ".novetest")
    delete_run_evidence(store, latest_ref)

    result = resolve_latest_analyzable_run(store)
    assert isinstance(result, RunReference)
    assert result.run_id == "01OLDAN0000000000000000010"


def test_resolve_does_not_invoke_derive(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe is cheap — it must never trigger derivation or a cache write.

    Two assertions: the ``derive_localization_findings`` symbol is
    monkey-patched to raise (call sites would fail loudly), and no
    ``localization_findings.json`` exists under the canonical path
    after the resolver returns.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    analyzable_ref = _ref("01SOLEAN0000000000000000001", _TS_NEW)
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=analyzable_ref,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    store = get_project_store_state(workspace / ".novetest")

    def _must_not_be_called(*args: object, **kwargs: object) -> object:
        raise AssertionError(
            "derive_localization_findings must not be called by the resolver"
        )

    monkeypatch.setattr(
        derive_module, "derive_localization_findings", _must_not_be_called
    )

    result = resolve_latest_analyzable_run(store)
    assert isinstance(result, RunReference)
    # No findings file written.
    findings_path = localization_findings_path(store, analyzable_ref.run_id)
    assert not findings_path.exists()


# --- derive_latest_localization ----------------------------------------------


def test_derive_latest_happy_path_returns_finding(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
) -> None:
    """One analyzable run → derive_latest returns a populated finding."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    analyzable_ref = _ref("01HAPPYRUN0000000000000001", _TS_NEW)
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=analyzable_ref,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_latest_localization(store)
    assert isinstance(result, LocalizationFinding)
    assert result.run_reference == analyzable_ref
    assert result.formula == "ochiai"
    assert result.top_n == 10


def test_derive_latest_empty_store_returns_no_run_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    store = create_project_store(workspace)
    result = derive_latest_localization(store)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_NO_RUN_EVIDENCE


def test_derive_latest_all_non_analyzable_returns_run_not_analyzable(
    tmp_path: Path,
    make_record: Callable[..., RunRecord],
) -> None:
    """Store has runs but none are analyzable → ``run_not_analyzable``
    propagates from the resolver (the §X-split narrowed semantic — the
    runs are structurally non-derivable from the localization POV)."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _seed_unanalyzable_run(
        workspace=workspace,
        run_reference=_ref("01UN0000000000000000000001", _TS_NEW),
        make_record=make_record,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_latest_localization(store)
    assert isinstance(result, LocalizationUnavailable)
    assert result.reason == REASON_RUN_NOT_ANALYZABLE


def test_derive_latest_forwards_formula_and_top_n_to_underlying_call(
    tmp_path: Path,
    write_python_module: Callable[[Path, str], None],
    make_record: Callable[..., RunRecord],
    make_coverage: Callable[..., CoverageFactSet],
    make_file: Callable[[str, dict[int, tuple[str, ...]]], FileCoverage],
) -> None:
    """``formula="op2"`` and ``top_n=5`` reach the underlying derivation —
    verified via the finding's ``formula`` field and the entry-count cap."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    analyzable_ref = _ref("01FWD000000000000000000001", _TS_NEW)
    _seed_analyzable_run(
        workspace=workspace,
        run_reference=analyzable_ref,
        write_python_module=write_python_module,
        make_record=make_record,
        make_coverage=make_coverage,
        make_file=make_file,
    )
    store = get_project_store_state(workspace / ".novetest")
    result = derive_latest_localization(store, formula="op2", top_n=5)
    assert isinstance(result, LocalizationFinding)
    assert result.formula == "op2"
    assert result.top_n == 5
    assert len(result.entries) <= 5
    # Ochiai (default) is now in alternate_scores, not the primary.
    assert "ochiai" in result.alternate_scores_available
    assert "op2" not in result.alternate_scores_available
