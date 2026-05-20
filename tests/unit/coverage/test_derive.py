"""Unit tests for `novetest.coverage.derive`."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from novetest.coverage import derive_coverage_facts
from novetest.coverage.persistence import coverage_facts_path
from novetest.coverage.results import (
    REASON_MISSING_NATIVE_PAYLOAD,
    REASON_NATIVE_PAYLOAD_CORRUPT,
    REASON_RUN_NOT_FOUND,
    CoverageUnavailable,
)
from novetest.memory.project_store import get_project_store_state
from novetest.memory.store import store_run_evidence
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference


def test_derive_returns_fact_set_for_run_with_native_payload(
    initialized_store: Path,
    sample_coverage_payload: dict[str, Any],
    sample_run_reference: RunReference,
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)

    result = derive_coverage_facts(store, sample_run_reference)

    assert isinstance(result, CoverageFactSet)
    assert result.run_reference == sample_run_reference
    assert result.engine_name == "pytest"
    assert result.ecosystem == "python"
    assert result.mapping_granularity == "per-test"
    # Summary mirrors top-level "totals" from the sample.
    assert result.summary.num_statements == 10
    assert result.summary.covered_statements == 8


def test_derive_persists_facts_at_load_bearing_path(
    initialized_store: Path,
    sample_coverage_payload: dict[str, Any],
    sample_run_reference: RunReference,
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    """The persisted file is what Memory's `_availability_flags` probes.

    Asserting this contract explicitly is what gives Memory's
    has_coverage_facts flag its auto-flip behavior.
    """
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)

    derive_coverage_facts(store, sample_run_reference)

    expected = coverage_facts_path(store, sample_run_reference.run_id)
    assert expected.is_file()
    # Memory's flag uses raw .is_file() — confirm via the same check.
    assert (
        store.path
        / "coverage"
        / "facts"
        / f"run_{sample_run_reference.run_id}"
        / "coverage_facts.json"
    ).is_file()


def test_derive_missing_run_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
) -> None:
    store = get_project_store_state(initialized_store)
    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_RUN_NOT_FOUND
    assert result.run_reference == sample_run_reference


def test_derive_run_without_coverage_artifact_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    store = get_project_store_state(initialized_store)
    # Run exists but lacks a "coverage_json" artifact (Phase 1 default).
    store_run_evidence(
        store, make_run_record(run_reference=sample_run_reference)
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_MISSING_NATIVE_PAYLOAD
    assert "coverage_json" in (result.detail or "")


def test_derive_native_payload_path_missing_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """RunRecord registers coverage_json but the file was removed/never written."""
    store = get_project_store_state(initialized_store)
    rel = f"run/artifacts/run_{sample_run_reference.run_id}/native/coverage.json"
    store_run_evidence(
        store,
        make_run_record(
            run_reference=sample_run_reference,
            artifact_paths={"coverage_json": rel},
        ),
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_MISSING_NATIVE_PAYLOAD


def test_derive_corrupt_json_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    store = get_project_store_state(initialized_store)
    rel = f"run/artifacts/run_{sample_run_reference.run_id}/native/coverage.json"
    target = store.path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{ not valid json", encoding="utf-8")
    store_run_evidence(
        store,
        make_run_record(
            run_reference=sample_run_reference,
            artifact_paths={"coverage_json": rel},
        ),
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_NATIVE_PAYLOAD_CORRUPT


def test_derive_payload_with_missing_files_block_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """Parser-level shape error is surfaced as `native-payload-corrupt`.

    Keeps the engine total at the boundary even when the JSON parses but
    is not a coverage.py report.
    """
    store = get_project_store_state(initialized_store)
    rel = f"run/artifacts/run_{sample_run_reference.run_id}/native/coverage.json"
    target = store.path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    store_run_evidence(
        store,
        make_run_record(
            run_reference=sample_run_reference,
            artifact_paths={"coverage_json": rel},
        ),
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_NATIVE_PAYLOAD_CORRUPT


def test_derive_is_idempotent_overwrites_persisted_facts(
    initialized_store: Path,
    sample_coverage_payload: dict[str, Any],
    sample_run_reference: RunReference,
    seed_run_with_coverage: Callable[..., RunRecord],
) -> None:
    seed_run_with_coverage(
        initialized_store,
        run_reference=sample_run_reference,
        coverage_json_payload=sample_coverage_payload,
    )
    store = get_project_store_state(initialized_store)

    first = derive_coverage_facts(store, sample_run_reference)
    second = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(first, CoverageFactSet)
    assert isinstance(second, CoverageFactSet)
    # Same inputs => same facts modulo derived_at.
    assert first.summary == second.summary
    assert first.files == second.files


def _seed_jest_run(
    store: Any,
    *,
    run_reference: RunReference,
    payload: dict[str, Any],
    make_run_record: Callable[..., RunRecord],
) -> None:
    """Persist a jest RunRecord with an Istanbul `coverage-final.json` payload."""
    rel = f"run/artifacts/run_{run_reference.run_id}/native/coverage/coverage-final.json"
    target = store.path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
    store_run_evidence(
        store,
        make_run_record(
            run_reference=run_reference,
            artifact_paths={"coverage_json": rel},
            engine_name="jest",
            ecosystem="javascript-typescript",
        ),
    )


def test_derive_routes_jest_engine_through_istanbul_parser(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """A `jest` Run Record's Istanbul payload yields a real CoverageFactSet.

    Confirms `derive_coverage_facts` dispatches on `engine_name` and that
    Istanbul's absolute paths are relativized against the workspace root
    (`store.path.parent`).
    """
    store = get_project_store_state(initialized_store)
    workspace = store.path.parent
    payload = {
        str(workspace / "src" / "calc.js"): {
            "path": str(workspace / "src" / "calc.js"),
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 10},
                },
                "1": {
                    "start": {"line": 4, "column": 2},
                    "end": {"line": 4, "column": 18},
                },
            },
            "s": {"0": 2, "1": 0},
        }
    }
    _seed_jest_run(
        store,
        run_reference=sample_run_reference,
        payload=payload,
        make_run_record=make_run_record,
    )

    result = derive_coverage_facts(store, sample_run_reference)

    assert isinstance(result, CoverageFactSet)
    assert result.engine_name == "jest"
    assert result.ecosystem == "javascript-typescript"
    assert result.mapping_granularity == "aggregate"
    assert [f.file_path for f in result.files] == ["src/calc.js"]
    assert result.files[0].executed_lines == (1,)
    assert result.files[0].missing_lines == (4,)
    assert result.summary.num_statements == 2
    assert result.summary.covered_statements == 1


def test_derive_jest_persists_facts_at_load_bearing_path(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """The jest path writes the same load-bearing `coverage_facts.json`."""
    store = get_project_store_state(initialized_store)
    workspace = store.path.parent
    payload = {
        str(workspace / "src" / "a.js"): {
            "path": str(workspace / "src" / "a.js"),
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 5},
                }
            },
            "s": {"0": 1},
        }
    }
    _seed_jest_run(
        store,
        run_reference=sample_run_reference,
        payload=payload,
        make_run_record=make_run_record,
    )

    derive_coverage_facts(store, sample_run_reference)

    assert coverage_facts_path(store, sample_run_reference.run_id).is_file()


def test_derive_jest_malformed_istanbul_entry_returns_unavailable(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    """An Istanbul entry missing `statementMap` surfaces as corrupt."""
    store = get_project_store_state(initialized_store)
    workspace = store.path.parent
    payload = {str(workspace / "src" / "a.js"): {"s": {}}}
    _seed_jest_run(
        store,
        run_reference=sample_run_reference,
        payload=payload,
        make_run_record=make_run_record,
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_NATIVE_PAYLOAD_CORRUPT


def test_derive_handles_top_level_json_array_as_corrupt(
    initialized_store: Path,
    sample_run_reference: RunReference,
    make_run_record: Callable[..., RunRecord],
) -> None:
    store = get_project_store_state(initialized_store)
    rel = f"run/artifacts/run_{sample_run_reference.run_id}/native/coverage.json"
    target = store.path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[1, 2, 3]", encoding="utf-8")
    store_run_evidence(
        store,
        make_run_record(
            run_reference=sample_run_reference,
            artifact_paths={"coverage_json": rel},
        ),
    )

    result = derive_coverage_facts(store, sample_run_reference)
    assert isinstance(result, CoverageUnavailable)
    assert result.reason == REASON_NATIVE_PAYLOAD_CORRUPT
