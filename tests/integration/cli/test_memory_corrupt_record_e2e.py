"""Subprocess E2E for MEM-05 per-record isolation (W2/S41).

One torn (truncated) and one future-schema ``record.json`` are planted in a
multi-run Project Store, then the verbs that walk Run History are exercised as
real subprocesses:

- ``novetest memory list``   → healthy runs + a path-bearing warning per skip
- ``novetest memory show``   → healthy run readable; the corrupt run reports
  ``not-found`` (its record no longer parses) with the warning attached
- ``novetest regression latest``  → baseline resolution survives the corrupt
  sibling (scan-level isolation, no CLI warning channel there by design)
- ``novetest localization latest`` → latest-analyzable walk survives too

Before the isolation landed, ONE bad record killed every one of these with an
uncaught-exception ``cli-error`` envelope (exit 1) — the A/B proof for this
file is reverting ``_iter_all_records``'s isolation and watching all of it die
again. The warning code ``corrupt-run-record-skipped`` and its
path-in-message contract are pinned here.
"""

from __future__ import annotations

import json
from pathlib import Path

from novetest.memory.project_store import create_project_store
from novetest.memory.store import RECORD_FILENAME, RUN_DIR_PREFIX, store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult


WARNING_CODE = "corrupt-run-record-skipped"

_BASELINE_REF = RunReference(
    run_id="01MEMBASELINE000000000000A", created_at=1_700_000_000_000
)
_TARGET_REF = RunReference(
    run_id="01MEMTARGET00000000000000B", created_at=1_700_000_001_000
)
_TORN_REF = RunReference(
    run_id="01MEMTORN0000000000000000C", created_at=1_700_000_002_000
)
_FUTURE_REF = RunReference(
    run_id="01MEMFUTURE00000000000000D", created_at=1_700_000_003_000
)


def _run(ref: RunReference, *, status: str, outcome: str) -> RunRecord:
    return RunRecord(
        run_reference=ref,
        target_expression="tests/",
        target_type="dir",
        engine_name="pytest",
        engine_version="8.2.0",
        ecosystem="python",
        status=status,
        started_at=ref.created_at,
        completed_at=ref.created_at + 1_000,
        test_results=(
            TestResult(node_id="tests/x.py::test_a", outcome=outcome, duration_ms=7),
        ),
    )


def _record_path(store_path: Path, ref: RunReference) -> Path:
    matches = [
        p
        for p in (store_path / "memory" / "runs").rglob(RECORD_FILENAME)
        if p.parent.name == f"{RUN_DIR_PREFIX}{ref.run_id}"
    ]
    assert len(matches) == 1, matches
    return matches[0]


def _seed_store_with_corruption(workspace: Path) -> tuple[Path, Path]:
    """Two healthy runs (same target, fail→pass) + one torn + one future-schema.

    Returns ``(torn_record_path, future_record_path)``.
    """
    store = create_project_store(workspace)
    store_run_evidence(store, _run(_BASELINE_REF, status="failed", outcome="failed"))
    store_run_evidence(store, _run(_TARGET_REF, status="passed", outcome="passed"))
    store_run_evidence(store, _run(_TORN_REF, status="passed", outcome="passed"))
    store_run_evidence(store, _run(_FUTURE_REF, status="passed", outcome="passed"))

    torn_path = _record_path(store.path, _TORN_REF)
    torn_path.write_text('{"schema_version": 1, "run_refe', encoding="utf-8")

    future_path = _record_path(store.path, _FUTURE_REF)
    raw = json.loads(future_path.read_text(encoding="utf-8"))
    raw["schema_version"] = 2
    future_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return torn_path, future_path


def _skip_warnings(envelope: dict) -> list[dict]:
    return [w for w in envelope["warnings"] if w["code"] == WARNING_CODE]


def test_memory_list_survives_and_warns_with_paths(isolated_cwd, run_cli) -> None:
    torn_path, future_path = _seed_store_with_corruption(isolated_cwd)

    result = run_cli(["memory", "list", "--output", "json"])

    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is True
    data = envelope["data"]
    # Both healthy runs listed; both corrupt records skipped, not fatal.
    assert data["count"] == 2
    listed = {e["entry_id"] for e in data["entries"]}
    assert listed == {_BASELINE_REF.run_id, _TARGET_REF.run_id}

    warnings = _skip_warnings(envelope)
    assert len(warnings) == 2
    # The operator finds the corrupt file without grep: the PATH is in the
    # message (and in details.path, machine-readable).
    warned_paths = {w["details"]["path"] for w in warnings}
    assert warned_paths == {str(torn_path), str(future_path)}
    for warning in warnings:
        assert warning["details"]["path"] in warning["message"]

    # Wire-shape pin: the nested run_record projection does NOT grow the
    # persisted MEM-04 stored_at key; the stamp surfaces at the entry level.
    for entry in data["entries"]:
        assert "stored_at" not in entry["run_record"]
        assert isinstance(entry["stored_at"], int)


def test_memory_show_of_healthy_run_survives_and_warns(isolated_cwd, run_cli) -> None:
    torn_path, _ = _seed_store_with_corruption(isolated_cwd)

    result = run_cli(["memory", "show", _TARGET_REF.run_id, "--output", "json"])

    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is True
    entry = envelope["data"]["memory_entry"]
    assert entry["entry_id"] == _TARGET_REF.run_id
    assert str(torn_path) in {w["details"]["path"] for w in _skip_warnings(envelope)}


def test_memory_show_of_corrupt_run_reports_not_found_with_warning(
    isolated_cwd, run_cli
) -> None:
    """The corrupt run's own show: no longer a cli-error crash (exit 1) but a
    structured ``not-found`` (its record was skipped by the lookup scan) WITH
    the path-bearing warning telling the operator exactly why.

    The loud targeted-read path (``retrieve_run_evidence`` on a named
    reference) is pinned at the unit level in
    ``tests/unit/memory/test_store.py``.
    """
    torn_path, _ = _seed_store_with_corruption(isolated_cwd)

    result = run_cli(["memory", "show", _TORN_REF.run_id, "--output", "json"])

    assert result.returncode == 2, result.stderr
    envelope = result.envelope()
    assert envelope["ok"] is False
    assert envelope["errors"][0]["code"] == "not-found"
    assert str(torn_path) in {w["details"]["path"] for w in _skip_warnings(envelope)}


def test_regression_latest_survives_corrupt_sibling(isolated_cwd, run_cli) -> None:
    """Regression's baseline resolution walks the same scan interfaces —
    isolation applies without any regression-engine edit (scan-API-level
    seam; no warning channel outside the memory verbs by design)."""
    _seed_store_with_corruption(isolated_cwd)

    result = run_cli(["regression", "latest", "--output", "json"])

    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "regression.latest"
    assert envelope["ok"] is True
    outcome = envelope["data"]["regression_outcome"]
    # The two healthy runs (fail → pass, same target) still pair up.
    assert outcome["kind"] == "fact-set"


def test_localization_latest_survives_corrupt_sibling(isolated_cwd, run_cli) -> None:
    """Localization's latest-analyzable walk (list_run_history) must not die
    on the corrupt records; without coverage facts it reports a structured
    unavailable outcome — never an uncaught-exception cli-error."""
    _seed_store_with_corruption(isolated_cwd)

    result = run_cli(["localization", "latest", "--output", "json"])

    assert result.returncode == 0, result.stderr
    envelope = result.envelope()
    assert envelope["command"] == "localization.latest"
    assert envelope["ok"] is True
    assert not envelope["errors"]
