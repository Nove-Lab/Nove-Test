"""End-to-end integration-style tests for `novetest.run.engine.execute`.

These exercise the full happy path: pinned readiness probe → adapter
dispatch → normalization → run-reference assignment. They intentionally
spawn real pytest subprocesses against the fixture projects because the
workflow's value is the wiring, not the individual steps.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from novetest.run import engine as engine_module
from novetest.run import readiness as readiness_module
from novetest.run.engine import execute, execute_with_engine_context
from novetest.run.engine_selector import list_supported_engine_pairs
from novetest.run.errors import EngineNotReadyError, EngineNotSupportedError
from novetest.run.target_resolver import resolve_test_target
from novetest.run.types import (
    EngineReadinessResult,
    NativeEngineContext,
    NativeResult,
)


async def test_execute_pytest_basic_returns_all_passed(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    # Per 2026-06-06 envelope-warnings-projection slice, ``execute``
    # returns ``(RunRecord, adapter_warnings)``; pytest emits zero
    # warnings today so the tuple's second element is the empty tuple.
    record, warnings = await execute(
        target, artifact_dir=tmp_path, engine=("python", "pytest"), timeout=60.0
    )
    assert warnings == ()
    assert record.status == "passed"
    assert record.engine_name == "pytest"
    assert record.ecosystem == "python"
    assert len(record.run_reference.run_id) == 26  # raw ULID
    assert record.summary_counts["passed"] == 3
    assert record.summary_counts["total"] == 3
    assert all(tr.outcome == "passed" for tr in record.test_results)
    # Native artifacts were captured under the per-run artifact_dir.
    json_report = Path(record.artifact_paths["pytest_json_report"])
    assert json_report.is_file()


async def test_execute_pytest_failing_captures_failure(
    failing_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", failing_workspace)
    record, warnings = await execute(
        target, artifact_dir=tmp_path, engine=("python", "pytest"), timeout=60.0
    )
    assert warnings == ()
    assert record.status == "failed"
    failed = [tr for tr in record.test_results if tr.outcome == "failed"]
    assert len(failed) == 1
    assert failed[0].failure_reference is not None


async def test_execute_short_circuits_for_empty_no_engine(
    empty_workspace: Path, tmp_path: Path
) -> None:
    """A pin naming an engine the workspace does not carry short-circuits
    at the readiness probe (`probe_engine` finds no pytest configuration
    in the empty fixture) — EngineNotReadyError before any subprocess."""

    target = resolve_test_target("", empty_workspace)
    artifact_dir = tmp_path / "should-not-be-created"
    with pytest.raises(EngineNotReadyError) as exc_info:
        await execute(
            target,
            artifact_dir=artifact_dir,
            engine=("python", "pytest"),
            timeout=10.0,
        )
    assert exc_info.value.readiness.state == "engine-missing"
    # No subprocess spawned → no native artifacts laid down.
    assert not artifact_dir.exists()


async def test_execute_with_engine_context_runs_pytest(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="python", engine_name="pytest")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=60.0
    )
    assert warnings == ()
    assert record.status == "passed"
    assert record.engine_name == "pytest"


async def test_execute_with_engine_context_rejects_unimplemented_engine(
    basic_workspace: Path, tmp_path: Path
) -> None:
    """All 6 native engines (pytest / jest / go-test / cargo-test / junit /
    xunit) are now implemented at Phase 2.5 close. To still exercise the
    "engine not implemented" raise path we synthesize an
    ``EngineNotSupportedError`` via a hypothetical future engine name
    (``"phpunit"``); the contract is "every unrecognized name raises",
    which stays load-bearing for forward compatibility with Phase 3+
    adapter additions.
    """

    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="php", engine_name="phpunit")
    with pytest.raises(EngineNotSupportedError):
        await execute_with_engine_context(
            target, context, artifact_dir=tmp_path, timeout=10.0
        )


async def test_execute_with_engine_context_dispatches_jest(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='jest')` must call ``run_jest``.

    Stubs the ``jest`` entry of the dispatch dict so we observe dispatch
    without requiring Node.js. The same NativeResult-fake pattern as the
    pytest `test_execute_threads_collect_coverage_kwarg_into_adapter` case.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_jest(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "jest-results.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="jest",
            # One passing test so the normalized record is passed-*non-empty*:
            # this dispatch test is about "engine_name='jest' calls run_jest",
            # not about the W1/S4 zero-collection site, so keep it off the
            # passed-empty path that legitimately appends a warning.
            payload={
                "success": True,
                "numPassedTests": 1,
                "numFailedTests": 0,
                "numPendingTests": 0,
                "numTodoTests": 0,
                "numTotalTests": 1,
                "testResults": [
                    {
                        "name": "/x.test.js",
                        "status": "passed",
                        "testResults": [
                            {
                                "ancestorTitles": [],
                                "title": "adds",
                                "status": "passed",
                                "duration": 1,
                            }
                        ],
                    }
                ],
            },
            artifact_paths={"jest_json_report": report_path},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="29.7.0",
        )

    monkeypatch.setitem(engine_module._ADAPTER_ENTRY_POINTS, "jest", fake_run_jest)
    target = resolve_test_target("__tests__/", jest_basic_workspace)
    context = NativeEngineContext(
        ecosystem="javascript-typescript", engine_name="jest"
    )
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "jest"
    assert record.ecosystem == "javascript-typescript"
    assert record.engine_version == "29.7.0"


async def test_run_id_can_be_pinned(
    basic_workspace: Path, tmp_path: Path
) -> None:
    target = resolve_test_target("", basic_workspace)
    record, _ = await execute(
        target,
        artifact_dir=tmp_path,
        engine=("python", "pytest"),
        run_id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
        timeout=60.0,
    )
    assert record.run_reference.run_id == "01HZZZZZZZZZZZZZZZZZZZZZZZ"


async def test_execute_threads_collect_coverage_kwarg_into_adapter(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute(collect_coverage=True)` must pass-through to ``run_pytest``.

    Stubs the ``pytest`` entry of the dispatch dict so we observe the
    kwarg without actually invoking pytest (which would need ``pytest-cov``
    plumbing that's exercised by the integration suite, not this unit test).
    """

    seen_kwargs: dict[str, Any] = {}

    async def fake_run_pytest(test_target: Any, **kwargs: Any) -> NativeResult:
        seen_kwargs.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "pytest-report.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="pytest",
            payload={
                "exitcode": 0,
                "summary": {"passed": 0, "total": 0},
                "tests": [],
                "duration": 0.0,
            },
            artifact_paths={"pytest_json_report": report_path},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="stub",
        )

    monkeypatch.setitem(
        engine_module._ADAPTER_ENTRY_POINTS, "pytest", fake_run_pytest
    )
    target = resolve_test_target("", basic_workspace)
    await execute(
        target,
        artifact_dir=tmp_path,
        engine=("python", "pytest"),
        timeout=10.0,
        collect_coverage=True,
    )
    assert seen_kwargs.get("collect_coverage") is True


async def test_execute_with_engine_context_dispatches_gotest(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='go-test')` must call ``run_gotest``.

    Stubs the ``go-test`` entry of the dispatch dict so we observe dispatch
    without requiring Go to be installed. Same fake-NativeResult pattern as
    the jest dispatch test.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_gotest(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        events_path = native_dir / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        return NativeResult(
            engine_name="go-test",
            # One passing test keeps this off the passed-empty path (the
            # W1/S4 zero-collection site) so the assertion stays about
            # dispatch, not about the warning.
            payload={
                "events": [
                    {
                        "Action": "pass",
                        "Package": "example.com/gotestbasic",
                        "Test": "TestAdd",
                        "Elapsed": 0.001,
                    }
                ],
                "packages": ["example.com/gotestbasic"],
                "failure_logs": {},
            },
            artifact_paths={
                "gotest_events_jsonl": events_path,
                "stdout": native_dir / "stdout.log",
                "stderr": native_dir / "stderr.log",
            },
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="1.23.4",
        )

    monkeypatch.setitem(
        engine_module._ADAPTER_ENTRY_POINTS, "go-test", fake_run_gotest
    )
    target = resolve_test_target("", gotest_basic_workspace)
    context = NativeEngineContext(ecosystem="go", engine_name="go-test")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "go-test"
    assert record.ecosystem == "go"
    assert record.engine_version == "1.23.4"


async def test_execute_with_engine_context_dispatches_cargo(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute_with_engine_context(engine_name='cargo-test')` must call
    ``run_cargo``.

    Stubs the ``cargo-test`` entry of the dispatch dict so we observe
    dispatch without requiring the Rust toolchain to be installed. Same
    fake-NativeResult pattern as the gotest dispatch test.
    """

    called_with: dict[str, Any] = {}

    async def fake_run_cargo(test_target: Any, **kwargs: Any) -> NativeResult:
        called_with["test_target"] = test_target
        called_with.update(kwargs)
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        events_path = native_dir / "events.jsonl"
        events_path.write_text("", encoding="utf-8")
        return NativeResult(
            engine_name="cargo-test",
            # One passing test keeps this off the passed-empty path (the
            # W1/S4 zero-collection site) so the assertion stays about
            # dispatch, not about the warning.
            payload={
                "events": [
                    {
                        "type": "test",
                        "event": "ok",
                        "name": "cargo_test_basic::tests::it_works",
                    }
                ],
                "binaries": [],
                "failure_logs": {},
            },
            artifact_paths={
                "cargo_events_jsonl": events_path,
                "stdout": native_dir / "stdout.log",
                "stderr": native_dir / "stderr.log",
            },
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
            engine_version="1.74.0",
            # `nextest_version` rides the typed metadata slot post the
            # 2026-05-30 migration (was previously stashed in
            # `payload[...]` and silently dropped at the normalizer
            # seam — Issue 2 of the cargo E2E sweep).
            metadata={"nextest_version": "0.9.70"},
        )

    monkeypatch.setitem(
        engine_module._ADAPTER_ENTRY_POINTS, "cargo-test", fake_run_cargo
    )
    target = resolve_test_target("", cargo_test_basic_workspace)
    context = NativeEngineContext(ecosystem="rust", engine_name="cargo-test")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert called_with.get("collect_coverage") is False
    assert warnings == ()
    assert record.engine_name == "cargo-test"
    assert record.ecosystem == "rust"
    assert record.engine_version == "1.74.0"


# ---------------------------------------------------------------------------
# execute(engine=...) — pin-driven dispatch
# (2026-07-03 pin-driven-dispatch slice, decision engine-selection-policy D3;
# engine REQUIRED + dict dispatch since W2/S16, RUN-25)
# ---------------------------------------------------------------------------


def _bomb(name: str) -> Any:
    """A stand-in that fails the test if the patched seam is reached."""

    def _explode(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"{name} must not run on the pinned path")

    return _explode


def test_execute_engine_parameter_is_required_keyword_only() -> None:
    """Debt b (W2/S16, RUN-25): ``engine`` is a REQUIRED keyword-only
    parameter — the legacy ``engine=None`` auto-detect branch is deleted,
    and the auto-detect seams are gone from the engine module. Restoring
    ``engine: tuple[str, str] | None = None`` must fail here by name."""

    param = inspect.signature(execute).parameters["engine"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    # The deleted auto-detect seams must not resurface on the module.
    assert not hasattr(engine_module, "select_native_engine")
    assert not hasattr(engine_module, "assess_engine_readiness")


def test_adapter_dispatch_matches_supported_engine_matrix() -> None:
    """Debt d (W2/S16) divergence guard: the dispatch dict's key set must
    equal the engine names of the supported matrix. A seventh engine added
    to `_ENGINE_MARKER_TABLE` without an adapter entry (or an adapter
    entry without a matrix row) fails here at test time, not in
    production. The expectation derives from `list_supported_engine_pairs()`
    — deliberately not a second hardcoded list."""

    assert set(engine_module._ADAPTER_ENTRY_POINTS) == {
        engine_name for _, engine_name in list_supported_engine_pairs()
    }


async def test_execute_with_explicit_engine_skips_detection(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`execute(engine=(eco, name))` must not detect: no marker scan runs
    on the pinned path. With `probe_engine` stubbed at the engine seam,
    any surviving detection would have to reach the readiness module's
    bound scan seams (`detect_engine_candidates` /
    `assess_engine_readiness`) — both are bombed. Readiness is probed for
    exactly the supplied pair and its ready context (version included)
    feeds dispatch.
    """

    monkeypatch.setattr(
        readiness_module,
        "assess_engine_readiness",
        _bomb("assess_engine_readiness"),
    )
    monkeypatch.setattr(
        readiness_module,
        "detect_engine_candidates",
        _bomb("detect_engine_candidates"),
    )

    probed_with: dict[str, Any] = {}

    async def fake_probe_engine(
        workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        probed_with["pair"] = (ecosystem, engine_name)
        return EngineReadinessResult(
            state="ready",
            engine_context=NativeEngineContext(
                ecosystem=ecosystem, engine_name=engine_name, engine_version="8.0.0"
            ),
            evidence=("pyproject.toml",),
            issues=(),
        )

    async def fake_run_pytest(test_target: Any, **kwargs: Any) -> NativeResult:
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "pytest-report.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="pytest",
            # One passing test keeps this off the passed-empty path (the
            # W1/S4 zero-collection site) so ``warnings == ()`` still asserts
            # "no adapter/engine warnings on the pinned dispatch path".
            payload={
                "exitcode": 0,
                "summary": {"passed": 1, "total": 1},
                "tests": [
                    {
                        "nodeid": "t.py::test_ok",
                        "outcome": "passed",
                        "call": {"duration": 0.001},
                    }
                ],
                "duration": 0.0,
            },
            artifact_paths={"pytest_json_report": report_path},
            returncode=0,
            started_at_ms=0,
            completed_at_ms=0,
        )

    monkeypatch.setattr(engine_module, "probe_engine", fake_probe_engine)
    monkeypatch.setitem(
        engine_module._ADAPTER_ENTRY_POINTS, "pytest", fake_run_pytest
    )

    target = resolve_test_target("", basic_workspace)
    record, warnings = await execute(
        target, artifact_dir=tmp_path, engine=("python", "pytest"), timeout=10.0
    )
    assert probed_with["pair"] == ("python", "pytest")
    assert warnings == ()
    assert record.engine_name == "pytest"
    assert record.ecosystem == "python"
    # Record version stays adapter-observed (the normalizer's existing
    # contract); the probe's "8.0.0" only rides the context handoff.
    assert record.engine_version is None


async def test_execute_with_explicit_engine_not_ready_raises(
    basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-ready pin short-circuits with EngineNotReadyError before any
    subprocess — same exit-code-4 contract as the auto-detect path."""

    async def fake_probe_engine(
        workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        return EngineReadinessResult(
            state="engine-misconfigured",
            engine_context=NativeEngineContext(
                ecosystem=ecosystem, engine_name=engine_name
            ),
            evidence=(),
            issues=("jest is declared in package.json but not installed; run: npm install",),
        )

    monkeypatch.setattr(engine_module, "probe_engine", fake_probe_engine)
    target = resolve_test_target("", basic_workspace)
    artifact_dir = tmp_path / "should-not-be-created"
    with pytest.raises(EngineNotReadyError) as exc_info:
        await execute(
            target,
            artifact_dir=artifact_dir,
            engine=("javascript-typescript", "jest"),
            timeout=10.0,
        )
    assert exc_info.value.readiness.state == "engine-misconfigured"
    assert not artifact_dir.exists()


async def test_execute_with_explicit_engine_runs_pytest_end_to_end(
    basic_workspace: Path, tmp_path: Path
) -> None:
    """The pinned path against a real workspace: probe → dispatch → run.

    No stubs — the real `probe_engine` gates and the real pytest adapter
    executes, proving the pin threads through the whole workflow exactly
    like the auto-detect path does.
    """

    target = resolve_test_target("", basic_workspace)
    record, warnings = await execute(
        target,
        artifact_dir=tmp_path,
        engine=("python", "pytest"),
        timeout=60.0,
    )
    assert warnings == ()
    assert record.status == "passed"
    assert record.engine_name == "pytest"
    assert record.ecosystem == "python"
    assert record.summary_counts["passed"] == 3


async def test_execute_with_unsupported_explicit_engine_raises(
    basic_workspace: Path, tmp_path: Path
) -> None:
    """Pins outside the six-engine matrix raise EngineNotSupportedError
    (the CLI's `--engine` validation is the user-facing gate; this is the
    programming-error surface behind it)."""

    target = resolve_test_target("", basic_workspace)
    with pytest.raises(EngineNotSupportedError):
        await execute(
            target,
            artifact_dir=tmp_path,
            engine=("php", "phpunit"),
            timeout=10.0,
        )


# ---------------------------------------------------------------------------
# W1/S4 — zero-collection warning (silent-green visibility, RUN-12 / C1)
# The single engine-agnostic emit site in ``execute_with_engine_context``
# keys purely on the normalized ``RunRecord`` (``status`` + ``test_results``),
# so pytest is a sufficient unit-level carrier to exercise all three
# branches; the go / junit / xunit *live* paths are covered by the
# integration suite (``test_zero_collection_warning.py`` +
# ``test_junit_warnings.py`` + ``test_dotnet_warnings.py``).
# ---------------------------------------------------------------------------


def _stub_pytest_native_result(
    monkeypatch: pytest.MonkeyPatch,
    *,
    exitcode: int,
    summary: dict[str, int],
    tests: list[dict[str, Any]],
) -> None:
    """Patch the dispatch dict's ``pytest`` entry to return a controlled
    pytest payload.

    ``exitcode`` doubles as the ``NativeResult.returncode`` and rides the
    payload's ``exitcode`` field so the normalizer derives status from a
    single source (pytest exit 5 → ``errored`` via
    ``_aggregate_pytest_status``).
    """

    async def fake_run_pytest(test_target: Any, **kwargs: Any) -> NativeResult:
        artifact_dir = kwargs["artifact_dir"]
        native_dir = Path(artifact_dir) / "native"
        native_dir.mkdir(parents=True, exist_ok=True)
        report_path = native_dir / "pytest-report.json"
        report_path.write_text("{}", encoding="utf-8")
        return NativeResult(
            engine_name="pytest",
            payload={
                "exitcode": exitcode,
                "summary": summary,
                "tests": tests,
                "duration": 0.0,
            },
            artifact_paths={"pytest_json_report": report_path},
            returncode=exitcode,
            started_at_ms=0,
            completed_at_ms=0,
        )

    monkeypatch.setitem(
        engine_module._ADAPTER_ENTRY_POINTS, "pytest", fake_run_pytest
    )


async def test_zero_collection_passed_empty_emits_warning(
    basic_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(1) A ``passed`` run that collected zero tests carries exactly one
    ``zero-tests-collected`` warning — the silent-green visibility fix."""

    _stub_pytest_native_result(
        monkeypatch, exitcode=0, summary={"passed": 0, "total": 0}, tests=[]
    )
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="python", engine_name="pytest")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert record.status == "passed"
    assert record.test_results == ()
    # Envelope-decoration only — nothing persisted on the record.
    assert "zero_tests_collected" not in record.metadata
    assert [w.code for w in warnings] == ["zero-tests-collected"]
    warning = warnings[0]
    assert warning.details == {"engine_name": "pytest"}
    assert "collected zero tests" in warning.message


async def test_zero_collection_passed_with_results_no_warning(
    basic_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(2) A ``passed`` run that DID collect tests emits no zero-collection
    warning — the condition requires an *empty* results tuple."""

    _stub_pytest_native_result(
        monkeypatch,
        exitcode=0,
        summary={"passed": 1, "total": 1},
        tests=[
            {"nodeid": "t.py::test_ok", "outcome": "passed", "call": {"duration": 0.001}}
        ],
    )
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="python", engine_name="pytest")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert record.status == "passed"
    assert len(record.test_results) == 1
    assert warnings == ()


async def test_zero_collection_non_passed_empty_no_warning(
    basic_workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(3) A non-``passed`` empty run emits no zero-collection warning — the
    site keys on ``status == "passed"``, so an already-loud ``errored`` /
    ``failed`` empty run is not double-flagged.

    Uses pytest exit code 5 (no-tests-collected), which
    ``_aggregate_pytest_status`` maps to ``errored`` — the exact pytest
    branch C1 calls out as a *separate* concern from this warning.
    """

    _stub_pytest_native_result(
        monkeypatch, exitcode=5, summary={"total": 0}, tests=[]
    )
    target = resolve_test_target("", basic_workspace)
    context = NativeEngineContext(ecosystem="python", engine_name="pytest")
    record, warnings = await execute_with_engine_context(
        target, context, artifact_dir=tmp_path, timeout=10.0
    )
    assert record.status == "errored"
    assert record.test_results == ()
    assert warnings == ()
