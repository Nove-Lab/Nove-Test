"""Persistence helpers — atomic write + raw read + Memory probe coupling."""

from __future__ import annotations

import json
from pathlib import Path

from novetest.localization.persistence import (
    invalidate_localization_findings,
    localization_findings_dir,
    localization_findings_path,
    read_localization_findings_raw,
    write_localization_findings,
)
from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


_REF = RunReference(run_id="01HPERSIST00000000000000XX", created_at=1_700_000_000_000)


def _location(line: int = 12) -> CodeLocation:
    return CodeLocation(
        kind="symbol",
        file="src/foo.py",
        symbol="foo",
        line_range=(10, 15),
        primary_line=line,
        evidence_lines=(line,),
    )


def _finding(run_reference: RunReference = _REF) -> LocalizationFinding:
    return LocalizationFinding(
        run_reference=run_reference,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("dstar2", "op2", "tarantula"),
        top_n=10,
        entries=(
            LocalizationEntry(
                rank=1,
                tied_with=(),
                code_location=_location(),
                score_raw=1.0,
                score_normalized=1.0,
                formula="ochiai",
                alternate_scores={"op2": 2.5, "dstar2": 4.0, "tarantula": 1.0},
                related_failed_tests=("tests/a.py::t",),
                evidence_citations=(
                    EvidenceCitation(
                        kind="test_result",
                        run_reference=run_reference,
                        selector={"test_id": "tests/a.py::t", "outcome": "failed"},
                    ),
                    EvidenceCitation(
                        kind="coverage_fact",
                        run_reference=run_reference,
                        selector={"file": "src/foo.py", "lines": [12]},
                    ),
                ),
            ),
        ),
        derived_at=run_reference.created_at + 500,
    )


def test_localization_findings_path_layout_is_load_bearing(tmp_path: Path) -> None:
    """The exact path Memory's ``_availability_flags`` probes must match.

    Memory checks: ``<store>/localization/findings/run_<run_id>/localization_findings.json``.
    """
    store = create_project_store(tmp_path)
    expected = (
        store.path
        / "localization"
        / "findings"
        / f"run_{_REF.run_id}"
        / "localization_findings.json"
    )
    assert localization_findings_path(store, _REF.run_id) == expected


def test_localization_findings_dir_matches_path_parent(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    assert (
        localization_findings_dir(store, _REF.run_id)
        == localization_findings_path(store, _REF.run_id).parent
    )


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    finding = _finding()
    write_path = write_localization_findings(store, finding)
    assert write_path == localization_findings_path(store, _REF.run_id)

    raw = read_localization_findings_raw(store, _REF.run_id)
    assert raw is not None
    restored = LocalizationFinding.from_dict(raw)
    assert restored == finding


def test_read_missing_returns_none(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    assert read_localization_findings_raw(store, "no-such-run") is None


def test_invalidate_removes_cache_and_missing_is_noop(tmp_path: Path) -> None:
    """S22-close rider: direct unit pin for the pinned cross-boundary API
    ``invalidate_localization_findings`` (the e2e rederive suite covers it
    end-to-end; this pins the two-line contract locally)."""
    store = create_project_store(tmp_path)
    write_localization_findings(store, _finding())
    invalidate_localization_findings(store, _REF.run_id)
    assert read_localization_findings_raw(store, _REF.run_id) is None
    # Missing cache is a no-op, not an error.
    invalidate_localization_findings(store, _REF.run_id)


def test_write_creates_parent_directory_on_demand(tmp_path: Path) -> None:
    store = create_project_store(tmp_path)
    # Directory does not exist yet — write must create it.
    target_dir = localization_findings_dir(store, _REF.run_id)
    assert not target_dir.exists()
    write_localization_findings(store, _finding())
    assert target_dir.is_dir()


def test_overwrite_existing_file(tmp_path: Path) -> None:
    """Re-writing replaces the payload — refreshed derivation works."""
    store = create_project_store(tmp_path)
    write_localization_findings(store, _finding())
    # Modify and rewrite.
    other = LocalizationFinding(
        run_reference=_REF,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="medium",  # different
        formula="ochiai",
        alternate_scores_available=(),
        top_n=10,
        entries=(),
        derived_at=_REF.created_at + 999,
    )
    write_localization_findings(store, other)
    raw = read_localization_findings_raw(store, _REF.run_id)
    assert raw is not None
    assert raw["confidence"] == "medium"


def test_write_atomic_via_tempfile_does_not_leak_partial(tmp_path: Path) -> None:
    """After a successful write the canonical file exists and no .tmp remains."""
    store = create_project_store(tmp_path)
    write_localization_findings(store, _finding())
    target_dir = localization_findings_dir(store, _REF.run_id)
    contents = list(target_dir.iterdir())
    # Should contain exactly the canonical file (no leftover .tmp).
    assert contents == [target_dir / "localization_findings.json"]


def test_memory_flag_auto_flips_after_write(tmp_path: Path) -> None:
    """Memory's ``has_localization_findings`` flag flips after the canonical write.

    This is the load-bearing coupling between Localization's persistence
    path and Memory's ``_availability_flags`` probe.
    """
    store = create_project_store(tmp_path)
    record = RunRecord(
        run_reference=_REF,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        ecosystem="python",
        status="failed",
        started_at=_REF.created_at,
        test_results=(
            TestResult(node_id="tests/a.py::t", outcome="failed", duration_ms=1),
        ),
    )
    entry = store_run_evidence(store, record)
    assert entry.has_localization_findings is False

    write_localization_findings(store, _finding())

    # Re-read availability via the same code path Memory uses.
    from novetest.memory.store import retrieve_run_evidence

    refreshed = retrieve_run_evidence(store, _REF)
    assert refreshed.has_localization_findings is True


def test_read_non_object_json_raises(tmp_path: Path) -> None:
    """A ``localization_findings.json`` whose root is not a JSON object is malformed."""
    store = create_project_store(tmp_path)
    target_dir = localization_findings_dir(store, _REF.run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "localization_findings.json").write_text(
        json.dumps(["not", "an", "object"]) + "\n", encoding="utf-8"
    )
    try:
        read_localization_findings_raw(store, _REF.run_id)
    except ValueError as exc:
        assert "not a JSON object" in str(exc)
    else:
        raise AssertionError("expected ValueError")
