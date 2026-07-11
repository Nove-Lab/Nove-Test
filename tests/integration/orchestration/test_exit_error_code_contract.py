"""W1/S8 subprocess-level exit & error-code contract (ORC-03/04/23).

End-to-end demonstrations through the REAL ``novetest`` CLI (subprocess
boundary — nothing monkeypatched):

- an **errored** suite (pytest collection error from a syntactically
  broken test file) is a USER result: exit 3 / ``ok: true`` for BOTH
  ``novetest run`` and ``novetest test`` (ORC-04);
- an engine-missing workspace emits the readiness state as the COMPLETE
  error-code token — ``engine-missing``, never the doubled
  ``engine-engine-missing`` (ORC-03);
- a markerless anchor behind a pin-less legacy store emits the D7
  standard ``no-engine-detected`` token, matching ``init`` (ORC-23).

The monkeypatched handler-level matrix lives in
``tests/unit/cli/test_exit_error_code_contract.py``.
"""

from __future__ import annotations

from pathlib import Path

from novetest.memory import create_project_store


def _write_broken_test_file(workspace: Path) -> None:
    """Plant a syntactically broken test module → pytest collection error.

    pytest exits 2 on a collection error; the adapter still receives the
    JSON report and the normalizer maps exit 2 to Run Record status
    ``errored`` — a normally-normalized, persisted user result.
    """
    (workspace / "tests" / "test_broken_syntax.py").write_text(
        "def broken(:\n    pass\n", encoding="utf-8"
    )


def _assert_no_doubled_prefix(envelope: dict[str, object]) -> None:
    errors = envelope["errors"]
    assert isinstance(errors, list)
    for error in errors:
        assert isinstance(error, dict)
        code = error["code"]
        assert isinstance(code, str)
        assert not code.startswith("engine-engine-"), code


def test_errored_suite_run_is_a_user_result(
    basic_workspace: Path, run_cli_in
) -> None:
    """ORC-04 e2e (``run`` verb): a pytest collection error (exit 2 →
    status ``errored``) is a USER result — exit 3 / ok=true, NOT exit 1."""

    init_result = run_cli_in(basic_workspace, ["init"])
    assert init_result.returncode == 0, init_result.stderr
    _write_broken_test_file(basic_workspace)

    run_result = run_cli_in(basic_workspace, ["run"])
    # exit 3 = user tests failed/errored; NOT exit 1 (tool failure).
    assert run_result.returncode == 3, run_result.stderr
    run_envelope = run_result.envelope()
    assert run_envelope["ok"] is True
    assert run_envelope["errors"] == []
    run_data = run_envelope["data"]
    assert isinstance(run_data, dict)
    memory_entry = run_data["memory_entry"]
    assert isinstance(memory_entry, dict)
    run_record = memory_entry["run_record"]
    assert isinstance(run_record, dict)
    assert run_record["status"] == "errored"


def test_errored_suite_test_is_a_user_result(
    basic_workspace: Path, run_cli_in
) -> None:
    """ORC-04 e2e (``test`` verb): an errored suite through the FULL
    integrated workflow is a USER result — exit 3 / ok=true.

    Errored shape used here: pytest exit 5 (no tests collected — the
    fixture's only test module is removed, its ``tests/`` dir kept so the
    pytest configuration stays detectable). Exit 5 emits both the JSON
    report AND the coverage files (verified empirically, pytest 9.0.3 /
    pytest-cov 7.0.0), so the errored record flows through the whole
    chain with coverage facts intact.

    The other errored shape — a pytest collection error under coverage,
    where pytest-cov writes no coverage JSON — ALSO persists an errored
    record and exits 3 since W2/S15 (pre-S15 it aborted inside the pytest
    adapter as exit 4 ``adapter-unparseable-output``; the boundary is now
    gated on the subprocess return code). That shape's end-to-end
    contract, including the omitted coverage artifacts, is pinned in
    ``tests/integration/run/test_error_classification.py``; this test
    keeps the coverage-bearing exit-5 variant so both errored shapes stay
    covered.
    """

    init_result = run_cli_in(basic_workspace, ["init"])
    assert init_result.returncode == 0, init_result.stderr
    (basic_workspace / "tests" / "test_math_utils.py").unlink()

    test_result = run_cli_in(basic_workspace, ["test"])
    assert test_result.returncode == 3, test_result.stderr
    test_envelope = test_result.envelope()
    assert test_envelope["ok"] is True
    assert test_envelope["errors"] == []
    test_data = test_envelope["data"]
    assert isinstance(test_data, dict)
    assert "recommendations" in test_data
    run_reference = test_data["run_reference"]
    assert isinstance(run_reference, dict)
    run_id = run_reference["run_id"]
    assert isinstance(run_id, str)

    # The persisted Run Record really is `errored` (not a masked failure).
    show_result = run_cli_in(basic_workspace, ["memory", "show", run_id])
    assert show_result.returncode == 0, show_result.stderr
    show_data = show_result.envelope()["data"]
    assert isinstance(show_data, dict)
    shown_entry = show_data["memory_entry"]
    assert isinstance(shown_entry, dict)
    shown_record = shown_entry["run_record"]
    assert isinstance(shown_record, dict)
    assert shown_record["status"] == "errored"


def test_engine_missing_emits_complete_token_for_run_and_test(
    empty_workspace: Path, run_cli_in
) -> None:
    """ORC-03 e2e: the readiness state IS the wire code — no doubled prefix.

    ``empty-no-engine`` carries a bare Python marker without any pytest
    configuration, so init pins pytest (readiness informational,
    NFR-RUN-004) and the execution verbs then fail readiness with the
    per-engine ``engine-missing`` verdict.
    """

    init_result = run_cli_in(empty_workspace, ["init"])
    assert init_result.returncode == 0, init_result.stderr

    for verb in ("run", "test"):
        result = run_cli_in(empty_workspace, [verb])
        assert result.returncode == 4, result.stderr
        envelope = result.envelope()
        assert envelope["ok"] is False
        errors = envelope["errors"]
        assert isinstance(errors, list) and errors
        first_error = errors[0]
        assert isinstance(first_error, dict)
        assert first_error["code"] == "engine-missing"
        _assert_no_doubled_prefix(envelope)
        data = envelope["data"]
        assert isinstance(data, dict)
        readiness = data["engine_readiness"]
        assert isinstance(readiness, dict)
        assert readiness["state"] == "engine-missing"


def test_markerless_legacy_store_emits_no_engine_detected(
    tmp_path: Path, run_cli_in
) -> None:
    """ORC-23 e2e: markerless anchor + pin-less legacy store → the D7
    standard ``no-engine-detected`` token (exit 4) on BOTH verbs."""

    workspace = tmp_path / "markerless"
    workspace.mkdir()
    # A pre-anchored-pin (legacy) store: no engine pin, no marker files.
    create_project_store(workspace)

    for verb in ("run", "test"):
        result = run_cli_in(workspace, [verb])
        assert result.returncode == 4, result.stderr
        envelope = result.envelope()
        assert envelope["ok"] is False
        errors = envelope["errors"]
        assert isinstance(errors, list) and errors
        first_error = errors[0]
        assert isinstance(first_error, dict)
        assert first_error["code"] == "no-engine-detected"
        _assert_no_doubled_prefix(envelope)
        # The readiness payload stays within run's three-state vocabulary.
        data = envelope["data"]
        assert isinstance(data, dict)
        readiness = data["engine_readiness"]
        assert isinstance(readiness, dict)
        assert readiness["state"] == "engine-missing"
