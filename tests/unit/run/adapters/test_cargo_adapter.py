"""Unit tests for the ``cargo nextest`` Native Engine adapter.

The adapter spawns ``cargo nextest run --message-format=libtest-json``
(or ``cargo llvm-cov nextest --lcov`` in coverage mode) as a subprocess.
To avoid requiring Rust + nextest in every CI cell, every test here
stubs the subprocess seam via ``monkeypatch`` on
``novetest.run.adapters.cargo_adapter.run_subprocess``, and the
``_stub_cargo_on_path`` autouse fixture stubs ``shutil.which`` so the
adapter's up-front ``cargo`` resolution succeeds on a Rust-less box.

The integration tests under ``tests/integration/run/`` exercise the
real binary and skip when ``cargo`` is absent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from novetest.run.adapters.cargo_adapter import (
    COVERAGE_LCOV_FILENAME,
    EVENTS_JSONL_FILENAME,
    STDERR_LOG_FILENAME,
    STDOUT_LOG_FILENAME,
    _build_child_env,
    run_cargo,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target
from novetest.utils.asyncio_subprocess import SubprocessResult


_FAKE_CARGO = "/usr/bin/cargo"


@pytest.fixture(autouse=True)
def _stub_cargo_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every adapter test run as if `cargo` is resolvable on PATH.

    `run_cargo` calls `shutil.which("cargo")` before spawning; on a
    Rust-less box that returns ``None`` and the adapter raises
    `missing-binary` before the stubbed subprocess is ever reached.
    Default every test to a resolvable `cargo`; the missing-binary test
    overrides this.
    """

    monkeypatch.setattr(shutil, "which", lambda name: _FAKE_CARGO)


def _ndjson_bytes(events: list[dict[str, Any]]) -> bytes:
    """Serialize libtest-json events as NDJSON bytes (one per line)."""

    return ("\n".join(json.dumps(e) for e in events) + "\n").encode("utf-8")


def _passing_events() -> list[dict[str, Any]]:
    """A canonical event stream for a single passing test."""

    return [
        {"type": "suite", "event": "started", "test_count": 1},
        {"type": "test", "event": "started", "name": "cargo_test_basic::tests::test_add_passes"},
        {
            "type": "test",
            "event": "ok",
            "name": "cargo_test_basic::tests::test_add_passes",
            "exec_time": 0.001,
        },
        {
            "type": "suite",
            "event": "ok",
            "passed": 1,
            "failed": 0,
            "ignored": 0,
            "exec_time": 0.01,
        },
    ]


def _failing_events() -> list[dict[str, Any]]:
    """An event stream for one passing + one failing test with stdout capture."""

    return [
        {"type": "suite", "event": "started", "test_count": 2},
        {"type": "test", "event": "started", "name": "cargo_test_basic::tests::test_add_passes"},
        {
            "type": "test",
            "event": "ok",
            "name": "cargo_test_basic::tests::test_add_passes",
            "exec_time": 0.001,
        },
        {
            "type": "test",
            "event": "started",
            "name": "cargo_test_basic::tests::test_subtract_intentionally_fails",
        },
        {
            "type": "test",
            "event": "failed",
            "name": "cargo_test_basic::tests::test_subtract_intentionally_fails",
            "stdout": (
                "thread 'tests::test_subtract_intentionally_fails' panicked at "
                "'subtract(10, 4) should equal 5: 6 != 5', src/lib.rs:28:9\n"
                "note: run with `RUST_BACKTRACE=1` environment variable to display "
                "a backtrace\n"
            ),
            "exec_time": 0.002,
        },
        {
            "type": "suite",
            "event": "failed",
            "passed": 1,
            "failed": 1,
            "ignored": 0,
            "exec_time": 0.05,
        },
    ]


def _integration_test_events() -> list[dict[str, Any]]:
    """An event stream for a test in a separate integration-test binary."""

    return [
        {
            "type": "suite",
            "event": "started",
            "test_count": 1,
            "binary": "cargo_test_basic--integration_test",
        },
        {
            "type": "test",
            "event": "started",
            "name": "cargo_test_basic--integration_test::test_add_via_integration",
            "binary": "cargo_test_basic--integration_test",
        },
        {
            "type": "test",
            "event": "ok",
            "name": "cargo_test_basic--integration_test::test_add_via_integration",
            "binary": "cargo_test_basic--integration_test",
            "exec_time": 0.001,
        },
        {"type": "suite", "event": "ok", "passed": 1, "failed": 0, "ignored": 0},
    ]


def _make_stub_subprocess(
    *,
    returncode: int = 0,
    events: list[dict[str, Any]] | None = None,
    write_coverage_lcov: bool = False,
    stdout_bytes: bytes | None = None,
    stderr_bytes: bytes = b"",
    timed_out: bool = False,
    raise_file_not_found: bool = False,
) -> Any:
    """Build an async stub for `run_subprocess` that emulates one cargo-test
    run.

    The stub inspects argv for ``--output-path <path>`` (the cargo-llvm-cov
    LCOV path) and writes a minimal LCOV file there if
    ``write_coverage_lcov`` is True. Mirrors the gotest adapter's
    coverage stub pattern.

    Three subprocess shapes are recognized:
    1. ``cargo --version`` (argv[1] == "--version") → returns canonical bytes.
    2. ``cargo nextest --version`` (argv[1] == "nextest" and argv[2] ==
       "--version") → returns canonical bytes.
    3. Anything else → the main test invocation, returns the configured
       stdout/stderr/returncode + writes coverage if requested.
    """

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if raise_file_not_found:
            raise FileNotFoundError(2, "No such file or directory: 'cargo'")
        # `cargo --version` shape: [<cargo>, "--version"]
        if (
            isinstance(argv, (list, tuple))
            and len(argv) == 2
            and argv[-1] == "--version"
        ):
            return SubprocessResult(
                returncode=0,
                stdout=b"cargo 1.74.0 (ecb9851af 2023-10-18)\n",
                stderr=b"",
                timed_out=False,
            )
        # `cargo nextest --version` shape: [<cargo>, "nextest", "--version"]
        if (
            isinstance(argv, (list, tuple))
            and len(argv) == 3
            and argv[1] == "nextest"
            and argv[-1] == "--version"
        ):
            return SubprocessResult(
                returncode=0,
                stdout=b"cargo-nextest 0.9.70\n",
                stderr=b"",
                timed_out=False,
            )
        # Main invocation. Honor coverage-write request.
        if write_coverage_lcov:
            # Coverage argv carries --output-path <path> (NOT
            # --output-path=<path>) per the brief.
            output_path = None
            for i, a in enumerate(argv):
                if isinstance(a, str) and a == "--output-path" and i + 1 < len(argv):
                    output_path = argv[i + 1]
                    break
            assert output_path is not None, "stub cargo invocation missing --output-path"
            coverage_path = Path(output_path)
            coverage_path.parent.mkdir(parents=True, exist_ok=True)
            coverage_path.write_text(
                "TN:\n"
                "SF:src/lib.rs\n"
                "DA:1,1\n"
                "DA:2,0\n"
                "LF:2\n"
                "LH:1\n"
                "end_of_record\n",
                encoding="utf-8",
            )
        stdout_payload = (
            stdout_bytes
            if stdout_bytes is not None
            else _ndjson_bytes(events or [])
        )
        return SubprocessResult(
            returncode=returncode,
            stdout=stdout_payload,
            stderr=stderr_bytes,
            timed_out=timed_out,
        )

    return stub


async def test_happy_path_parses_payload_and_returns_native_result(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(events=_passing_events()),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    assert result.engine_name == "cargo-test"
    assert result.returncode == 0
    payload = result.payload
    assert isinstance(payload["events"], list)
    assert isinstance(payload["binaries"], list)
    assert "failure_logs" in payload
    # `nextest_version` is probed and surfaced via the typed metadata
    # slot (NOT `payload[...]`) so the persisted `RunRecord.metadata`
    # carries it — Issue 2 of the 2026-05-30 cargo sweep, resolved by
    # `decisions/2026-05-30-native-result-metadata-slot.md`. The
    # primary engine version (cargo itself) stays on
    # `engine_version`; the secondary runner lives on `metadata`.
    assert "nextest_version" not in payload
    assert result.metadata["nextest_version"] == "0.9.70"

    events_path = result.artifact_paths["cargo_events_jsonl"]
    assert events_path.name == EVENTS_JSONL_FILENAME
    assert events_path.is_file()
    # The on-disk NDJSON file must round-trip cleanly.
    written_events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(written_events) == len(_passing_events())

    stdout_path = result.artifact_paths["stdout"]
    stderr_path = result.artifact_paths["stderr"]
    assert stdout_path.name == STDOUT_LOG_FILENAME
    assert stderr_path.name == STDERR_LOG_FILENAME
    assert result.engine_version == "1.74.0"


async def test_argv_uses_default_workspace_when_expression_empty(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `target_expression` produces a `--workspace`-only argv —
    nextest walks every crate in the workspace by default."""

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        # Forward version probes to the canonical responder.
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0 (ecb9851af 2023-10-18)\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target("", cargo_test_basic_workspace)
    await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # Canonical flags for the nextest execution path.
    assert "nextest" in captured_argv
    assert "run" in captured_argv
    assert "--message-format=libtest-json" in captured_argv
    assert "--no-fail-fast" in captured_argv
    assert "--workspace" in captured_argv
    # No trailing filter expression when target is empty.
    assert captured_argv[-1] == "--workspace"


async def test_argv_passes_target_expression_through_verbatim(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty `target_expression` is appended verbatim (no rewrite)."""

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target("tests::test_add", cargo_test_basic_workspace)
    await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    assert captured_argv[-1] == "tests::test_add"


async def test_argv_omits_directory_target_expression(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix A regression pin (2026-06-05 cargo CLI orchestration defect).

    ``target_resolver`` classifies ``novetest run .`` as
    ``target_type="directory"`` with ``target_expression="."`` because
    ``workspace_context / "."`` resolves to a directory. The adapter
    MUST NOT pass directory-type expressions to ``cargo nextest`` as
    positional arguments — nextest interprets the positional as a
    filter DSL token, and the literal ``"."`` matches a test whose ID
    equals ``"."`` (none in any realistic workspace), yielding exit 4
    with ``Starting 0 tests across … (3 tests skipped)`` and
    ``error: no tests to run``. ``--workspace`` already covers the
    workspace root, so suppressing the append produces the same
    invocation as ``novetest run`` bare — matching the user's intent.

    See ``agent-comms/findings/manual-test-team-2026-06-04-host-equip.md``
    §"Cargo adapter — CLI vs adapter-direct discrepancy" for the
    field-captured stderr that motivated this regression pin.

    The negative assertion (``"." not in captured_argv``) is the load-
    bearing guard. The positive ``--workspace in captured_argv`` is a
    cross-check that the non-positional flag still lands.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        # Route version probes to canned responses so the captured
        # argv carries ONLY the main invocation's flags (same pattern
        # as ``test_argv_uses_default_workspace_when_expression_empty``).
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    # ``resolve_test_target(".", workspace)`` produces
    # ``target_type="directory"`` because ``workspace / "."`` is a dir.
    # This is the exact code path Manual Test exercised on 2026-06-04
    # via ``uv run novetest run .``.
    target = resolve_test_target(".", cargo_test_basic_workspace)
    assert target.target_type == "directory"
    assert target.target_expression == "."

    await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # Load-bearing: the literal "." must NOT be appended as a positional
    # filter. Pre-fix it sat at ``captured_argv[-1]``; post-fix the argv
    # tail is ``--workspace`` (same as the empty-expression case).
    assert "." not in captured_argv, (
        f"directory-type target_expression '.' must not reach nextest as "
        f"a positional filter (Fix A regression — see cargo_adapter.run_cargo "
        f"docstring). Got argv: {captured_argv!r}"
    )
    assert captured_argv[-1] == "--workspace"
    # Sanity guards against the test stub being mis-routed.
    assert "nextest" in captured_argv
    assert "run" in captured_argv


async def test_argv_appends_file_target_expression_verbatim(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix A scope guard (2026-06-05 cargo CLI orchestration defect).

    The directory-type suppression must NOT affect non-directory
    target types. ``target_type="file"`` (or ``"workspace"`` /
    ``"nodeid"``) keeps the pre-fix verbatim-append contract. This
    test pins the ``"file"`` case explicitly so a future refactor of
    Fix A that over-broadly suppresses (e.g. by accident gating on
    ``target_type in {"directory", "file"}``) is caught.

    We construct the ``TestTarget`` directly rather than relying on
    ``resolve_test_target`` because ``resolve_test_target("nonexistent.rs",
    workspace)`` returns ``target_type="file"`` only when the path does
    NOT resolve as a directory. Constructing it explicitly makes the
    test independent of fixture filesystem state.
    """

    import novetest.run.adapters.cargo_adapter as adapter
    from novetest.run.types import TestTarget

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = TestTarget(
        target_expression="tests/integration_test.rs",
        target_type="file",
        workspace_path=cargo_test_basic_workspace,
    )
    await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # File-type targets keep the verbatim append (parity with pre-fix
    # contract). The engine surfaces its own error if the path doesn't
    # match anything — that's the user's signal, not a Run-team
    # responsibility to pre-validate.
    assert captured_argv[-1] == "tests/integration_test.rs"


async def test_no_tests_match_stderr_surfaces_distinct_message(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix B regression pin (2026-06-05 cargo CLI orchestration defect).

    When nextest's stderr contains BOTH ``Starting 0 tests across`` AND
    ``error: no tests to run``, the adapter must surface a distinct
    diagnostic that names "filter matched zero tests" — NOT the
    misleading "likely build failure" wording. The pre-fix branch
    surfaced both true compile failures and filter-mismatches with the
    same prose; users whose stderr clearly showed ``Finished test
    profile … target(s)`` (i.e. build succeeded) were misdirected to
    investigate compile errors that did not exist.

    The stderr literal used here is verbatim from Manual Test's
    2026-06-04 host-equip findings — the exact bytes nextest 0.9.137
    emits when the filter resolves to zero tests across two binaries
    with three discovered-then-skipped tests.

    The post-fix message MUST:
    1. Include the words "filter matched zero tests" (the accurate
       root-cause framing).
    2. NOT include "likely build failure" (the misleading pre-fix
       wording — the negative assertion is the load-bearing guard
       against a future refactor accidentally falling through to the
       generic branch).
    3. Carry the offending ``target_expression`` repr so the user can
       correlate the diagnosis with what they typed.
    4. Carry the ``target_type`` repr so an AI consumer can disambiguate
       the directory-vs-explicit-filter case at one glance.
    5. Stay on ``kind="unparseable-output"`` per task brief §2 —
       adding a new kind would require a ``questions/`` entry first.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    # Verbatim stderr from the Manual Test 2026-06-04 findings file
    # §"Cargo adapter — CLI vs adapter-direct discrepancy", trimmed
    # to the load-bearing literals + surrounding context. The
    # ``Finished test profile`` line is included to prove the
    # heuristic still fires even when stderr contains positive
    # build-success markers — the pre-fix code treated this as a
    # build failure anyway.
    no_tests_stderr = (
        b"   Compiling cargo_test_basic v0.1.0\n"
        b"    Finished `test` profile [unoptimized + debuginfo] "
        b"target(s) in 0.31s\n"
        b"------------\n"
        b" Nextest run ID 640954a3 with nextest profile: default\n"
        b"    Starting 0 tests across 2 binaries (3 tests skipped)\n"
        b"------------\n"
        b"     Summary [   0.001s] 0 tests run: 0 passed, 3 skipped\n"
        b"error: no tests to run\n"
        b"(hint: use `--no-tests` to customize)\n"
    )
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=4,
            stdout_bytes=b"",
            stderr_bytes=no_tests_stderr,
        ),
    )

    # Use a non-empty filter expression with ``target_type="nodeid"`` so
    # Fix A's directory-suppression does NOT intercept — we want Fix
    # B's heuristic to actually run against an argv that DID carry a
    # filter. (A directory-typed target would yield zero tests via
    # ``--workspace`` matching the full workspace, not via the
    # no-tests-match path; that case is owned by Fix A's test above.)
    from novetest.run.types import TestTarget

    target = TestTarget(
        target_expression="tests::definitely_does_not_exist",
        target_type="nodeid",
        workspace_path=cargo_test_basic_workspace,
    )
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # Kind contract: still ``unparseable-output`` per task brief §2 —
    # disambiguation lives in the message text, not in a new kind.
    assert exc_info.value.kind == "unparseable-output"

    message = str(exc_info.value)

    # Positive: the accurate root-cause framing.
    assert "filter matched zero tests" in message, (
        f"post-fix message must name the actual cause; got: {message!r}"
    )
    # Negative (load-bearing): the misleading pre-fix wording must be
    # gone. A future refactor that re-introduces it (e.g. by falling
    # through to the generic branch) is caught here.
    assert "likely build failure" not in message, (
        f"misleading 'likely build failure' wording must not appear in "
        f"the no-tests-match branch; got: {message!r}"
    )
    # Diagnostic context: the offending filter expression and
    # target_type appear in the message so a user can correlate the
    # diagnosis with what they typed.
    assert "tests::definitely_does_not_exist" in message
    assert "nodeid" in message


async def test_no_tests_match_heuristic_does_not_fire_on_true_compile_failure(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix B scope guard (2026-06-05 cargo CLI orchestration defect).

    True compile failures (exit 101 with ``error[E####]`` in stderr,
    no ``Starting 0 tests across`` line) must still surface as the
    generic "likely build failure" diagnostic. The no-tests-match
    carve-out fires ONLY on the conjunction of both nextest literals.

    Without this scope guard, a refactor that broadened the carve-out
    (e.g. dropped the second literal from the conjunction) could
    silently re-classify compile failures, breaking the diagnostic
    contract in the other direction.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=101,
            stdout_bytes=b"",
            stderr_bytes=(
                b"error[E0425]: cannot find function `nonexistent` in this scope\n"
                b"error: aborting due to previous error\n"
                b"error: could not compile `cargo_test_basic` (lib test) "
                b"due to 1 previous error\n"
            ),
        ),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    assert exc_info.value.kind == "unparseable-output"
    # Generic branch fired: the message DOES say "build failure" and
    # does NOT say "filter matched zero tests".
    message = str(exc_info.value)
    assert "build failure" in message.lower()
    assert "filter matched zero tests" not in message


async def test_failing_test_writes_failure_log(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing test's buffered `stdout` lands in a per-test log file."""

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=1, events=_failing_events()),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    failure_logs = result.payload["failure_logs"]
    assert isinstance(failure_logs, dict)
    failing_name = "cargo_test_basic::tests::test_subtract_intentionally_fails"
    assert failing_name in failure_logs
    rel_path = failure_logs[failing_name]
    assert isinstance(rel_path, str)
    # The relative path resolves under the artifact_dir.
    abs_failure_log = tmp_path / rel_path
    assert abs_failure_log.is_file()
    body = abs_failure_log.read_text(encoding="utf-8")
    assert "panicked" in body
    assert "test_subtract_intentionally_fails" in body
    # Filename safety: `::` becomes `__` via the colon-replace pass.
    assert abs_failure_log.name == (
        "cargo_test_basic__tests__test_subtract_intentionally_fails.log"
    )


async def test_integration_test_binary_node_id_preserved(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration tests in `tests/foo.rs` arrive with a binary-prefixed
    name; the adapter preserves that in events (and the normalizer uses
    ``name`` directly as node_id). Suite-level `binary` is collected
    into payload["binaries"].
    """

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(events=_integration_test_events()),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    events = result.payload["events"]
    assert isinstance(events, list)
    seen_names = {
        e["name"]
        for e in events
        if isinstance(e, dict) and isinstance(e.get("name"), str)
    }
    assert (
        "cargo_test_basic--integration_test::test_add_via_integration" in seen_names
    )
    # The binary identifier appeared on suite + test events.
    binaries = result.payload["binaries"]
    assert isinstance(binaries, list)
    assert "cargo_test_basic--integration_test" in binaries


async def test_build_failure_shape_raises_unparseable(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build failure produces empty stdout + non-zero exit, which the
    adapter must surface as a typed `unparseable-output` error — the
    same precedent as the gotest adapter's build-failure path.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=101,
            stdout_bytes=b"",
            stderr_bytes=(
                b"error[E0425]: cannot find function `nonexistent` in this scope\n"
                b"error: aborting due to previous error\n"
                b"error: could not compile `cargo_test_basic` (lib test) due to 1 previous error\n"
            ),
        ),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    assert exc_info.value.kind == "unparseable-output"
    assert "build failure" in str(exc_info.value).lower()


async def test_build_failure_heuristic_surfaces_env_var_literal(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When nextest's stderr contains ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON``,
    the build-failure heuristic surfaces a specific
    ``misconfigured-environment`` kind instead of the generic
    ``unparseable-output`` (which would mislead consumers into
    diagnosing this as a compile failure).

    The 2026-05-31 env-var hotfix (`_build_child_env`) sets the env
    var unconditionally so this symptom should not surface in normal
    operation, but if a parent process / shell strips it or a future
    nextest version renames the gate, the adapter should still emit a
    diagnostic that points at the env var by name. Heuristic polish
    per `tasks/run-team-2026-05-31-build-failure-heuristic-polish.md`.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    # The literal nextest 0.9.137 error sentence on the env-var-missing
    # path — keep this as the realistic shape the substring check has
    # to recognize. We only assert on the env-var literal itself
    # because nextest's exact wording is upstream-owned.
    nextest_env_missing_stderr = (
        b"error: libtest JSON output is an experimental feature and "
        b"must be enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1\n"
    )
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=95,
            stdout_bytes=b"",
            stderr_bytes=nextest_env_missing_stderr,
        ),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # Specific kind, not the generic build-failure kind.
    assert exc_info.value.kind == "misconfigured-environment"
    message = str(exc_info.value)
    # Message names the env-var literal so AI consumers and humans
    # can map the symptom to the cause without re-reading stderr.
    assert "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" in message
    # Message carries the override-diagnosis prose so the next step
    # is obvious.
    assert "parent process or shell hasn't pre-unset" in message
    # Spawn-path identifier is "nextest" (plain run), not the
    # coverage-path "llvm-cov nextest" — guards against the two
    # branches being mis-wired to the same mode label.
    assert "cargo nextest exited 95" in message


async def test_skip_action_does_not_trigger_build_failure(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workspace with no tests emits suite-start + suite-ok and exits 0 —
    must NOT be flagged as a build failure. (Discriminant: build
    failure requires non-zero returncode.)
    """

    import novetest.run.adapters.cargo_adapter as adapter

    events = [
        {"type": "suite", "event": "started", "test_count": 0},
        {"type": "suite", "event": "ok", "passed": 0, "failed": 0, "ignored": 0},
    ]
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=events),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.returncode == 0
    assert result.payload["events"] == events


async def test_unresolvable_cargo_raises_typed_error(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `shutil.which("cargo")` returns None, the adapter raises
    ``missing-binary`` up front — before any subprocess spawn."""

    monkeypatch.setattr(shutil, "which", lambda name: None)

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"
    assert exc_info.value.install_hint is not None
    assert "rustup.rs" in exc_info.value.install_hint


async def test_launcher_exec_failure_maps_to_missing_binary(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `FileNotFoundError` from the spawn itself (TOCTOU race) still
    maps to ``missing-binary``."""

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(raise_file_not_found=True),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"


async def test_timeout_maps_to_typed_error(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=-9, stdout_bytes=b"", timed_out=True,
        ),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path, timeout=0.1)
    assert exc_info.value.kind == "timed-out"


async def test_malformed_json_lines_are_skipped(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive parsing: a malformed line in the middle of the stream
    must not abort the rest. Surrounding valid events still parse.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    valid_event = {
        "type": "test", "event": "ok",
        "name": "my_crate::tests::test_x",
    }
    started_event = {
        "type": "test", "event": "started",
        "name": "my_crate::tests::test_x",
    }
    valid_started = json.dumps(started_event)
    valid_line = json.dumps(valid_event)
    stdout_bytes = (
        valid_started + "\n" + "{not valid json\n" + valid_line + "\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, stdout_bytes=stdout_bytes),
    )

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    events = result.payload["events"]
    assert isinstance(events, list)
    assert len(events) == 2  # malformed line dropped, two valid survive


async def test_collect_coverage_false_omits_flags_and_artifact(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default path: no `cargo llvm-cov` invocation; no `coverage_lcov` key."""

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)

    # In execution mode, the second token is "nextest", NOT "llvm-cov".
    assert "llvm-cov" not in captured_argv
    assert "--lcov" not in captured_argv
    assert "coverage_lcov" not in result.artifact_paths


async def test_collect_coverage_adds_flags_and_registers_artifact(
    cargo_test_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``collect_coverage=True`` invokes ``cargo llvm-cov nextest --lcov`` and
    registers ``coverage.lcov`` under the ``coverage_lcov`` key.

    The key is deliberately NOT ``coverage_json`` (Istanbul / coverage.py)
    and NOT ``coverage_profile`` (Go cover-profile) — see the cargo
    adapter docstring.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        # Honor coverage write.
        output_path = None
        for i, a in enumerate(argv):
            if isinstance(a, str) and a == "--output-path" and i + 1 < len(argv):
                output_path = argv[i + 1]
                break
        assert output_path is not None
        coverage_path = Path(output_path)
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        coverage_path.write_text(
            "TN:\nSF:src/lib.rs\nDA:1,1\nLF:1\nLH:1\nend_of_record\n",
            encoding="utf-8",
        )
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", cargo_test_basic_coverage_workspace)
    result = await run_cargo(
        target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
    )

    # Coverage argv shape — see cargo_adapter.run_cargo().
    assert "llvm-cov" in captured_argv
    assert "nextest" in captured_argv
    assert "--lcov" in captured_argv
    assert "--output-path" in captured_argv
    # `--ignore-run-fail`, NOT `--no-fail-fast` — see the swap-rationale
    # docstring in `cargo_adapter.run_cargo` (coverage branch) and the
    # focused test `test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail`
    # below for the load-bearing regression pin.
    assert "--ignore-run-fail" in captured_argv
    assert "--workspace" in captured_argv

    coverage_path = result.artifact_paths["coverage_lcov"]
    assert coverage_path.name == COVERAGE_LCOV_FILENAME
    assert coverage_path.is_file()
    assert coverage_path.read_text(encoding="utf-8").startswith("TN:")


async def test_coverage_argv_swaps_no_fail_fast_for_ignore_run_fail(
    cargo_test_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cargo-llvm-cov argv must use ``--ignore-run-fail`` and NOT
    ``--no-fail-fast``.

    Empirical evidence in `agent-comms/questions/main-branch-team-
    2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`
    §Defect 1: cargo-llvm-cov with ``--no-fail-fast`` refuses to emit
    the LCOV report when the inner cargo-nextest exits non-zero (i.e.,
    any failing test). ``--ignore-run-fail`` is cargo-llvm-cov's flag
    that internally implies ``--no-fail-fast`` AND commits to writing
    the LCOV report even when nextest exits non-zero. The two flags
    are mutually exclusive on cargo-llvm-cov's CLI.

    This test pins both invariants in isolation so a future
    refactor cannot regress the flag swap silently. The non-coverage
    path's separate `test_argv_*` tests pin ``--no-fail-fast`` on
    plain ``cargo nextest run`` (where ``--ignore-run-fail`` would
    error — it is a cargo-llvm-cov-only flag).
    """

    import novetest.run.adapters.cargo_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        # Route the `cargo --version` and `cargo nextest --version`
        # probes to canned responses (identical to other tests'
        # version-probe handling) so the captured argv contains ONLY
        # the main spawn's flags — not the version-probe argvs.
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.74.0\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        captured_argv.extend(argv)
        # Honor coverage write so the post-spawn LCOV-exists check
        # doesn't fire the symmetric ``misconfigured-environment`` or
        # ``unparseable-output`` raises (those have their own tests).
        output_path = None
        for i, a in enumerate(argv):
            if isinstance(a, str) and a == "--output-path" and i + 1 < len(argv):
                output_path = argv[i + 1]
                break
        assert output_path is not None
        coverage_path = Path(output_path)
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        coverage_path.write_text(
            "TN:\nSF:src/lib.rs\nDA:1,1\nLF:1\nLH:1\nend_of_record\n",
            encoding="utf-8",
        )
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", cargo_test_basic_coverage_workspace)
    await run_cargo(
        target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
    )

    # Both invariants. The negative assertion is the load-bearing one
    # — without it, a future polish that added BOTH flags (mutually
    # exclusive on cargo-llvm-cov's CLI; would error at runtime) could
    # pass the positive assertion alone.
    assert "--ignore-run-fail" in captured_argv
    assert "--no-fail-fast" not in captured_argv
    # Confirm we captured the coverage spawn, not the non-coverage
    # one (paranoia guard against a stub-routing bug).
    assert "llvm-cov" in captured_argv


async def test_collect_coverage_missing_lcov_raises_unparseable(
    cargo_test_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `cargo llvm-cov` doesn't write the LCOV file (e.g. missing
    `llvm-tools-preview` rustup component), surface a typed
    ``unparseable-output`` error rather than registering a missing
    artifact."""

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=0, events=_passing_events(), write_coverage_lcov=False,
        ),
    )

    target = resolve_test_target("", cargo_test_basic_coverage_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(
            target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
        )
    assert exc_info.value.kind == "unparseable-output"


async def test_collect_coverage_env_var_literal_surfaces_misconfigured_environment(
    cargo_test_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The coverage path applies the symmetric env-var-literal detection.

    ``cargo llvm-cov nextest`` forwards ``--message-format=libtest-json``
    to nextest internally; the env-var gate fires identically, so the
    coverage-path branch raises ``misconfigured-environment`` (NOT the
    generic ``unparseable-output`` from "llvm-cov did not write the
    LCOV file") when the literal surfaces in stderr. Spawn-path
    identifier in the message is ``llvm-cov nextest``, distinguishing
    this branch from the plain-run branch above.
    """

    import novetest.run.adapters.cargo_adapter as adapter

    nextest_env_missing_stderr = (
        b"error: libtest JSON output is an experimental feature and "
        b"must be enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1\n"
    )
    # write_coverage_lcov=False → coverage_path.exists() is False on
    # entry to the post-events check, which triggers the symmetric
    # branch. Non-zero returncode mirrors the real-world failure
    # shape (nextest exits 95 when the env var is missing).
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=95,
            stdout_bytes=b"",
            stderr_bytes=nextest_env_missing_stderr,
            write_coverage_lcov=False,
        ),
    )

    target = resolve_test_target("", cargo_test_basic_coverage_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(
            target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
        )

    assert exc_info.value.kind == "misconfigured-environment"
    message = str(exc_info.value)
    assert "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" in message
    assert "parent process or shell hasn't pre-unset" in message
    # Coverage spawn path → mode label is "llvm-cov nextest", not
    # "nextest" — proves the helper's mode kwarg is wired through
    # correctly from the coverage call site.
    assert "cargo llvm-cov nextest exited 95" in message


async def test_engine_version_parsed_from_cargo_version_output(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cargo --version` → engine_version stripped to '1.74.0'."""

    import novetest.run.adapters.cargo_adapter as adapter

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=0,
                        stdout=b"cargo 1.78.0 (54d8815d0 2024-03-26)\n",
                        stderr=b"",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=0,
                    stdout=b"cargo-nextest 0.9.70\n",
                    stderr=b"",
                    timed_out=False,
                )
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.engine_version == "1.78.0"


async def test_engine_version_returns_none_on_unparseable_output(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`cargo --version` failures / weird output → engine_version=None (silent)."""

    import novetest.run.adapters.cargo_adapter as adapter

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) >= 2:
            if argv[-1] == "--version" and (len(argv) == 2 or argv[1] == "nextest"):
                if len(argv) == 2:
                    return SubprocessResult(
                        returncode=1,
                        stdout=b"",
                        stderr=b"cargo: command not found\n",
                        timed_out=False,
                    )
                return SubprocessResult(
                    returncode=1,
                    stdout=b"",
                    stderr=b"",
                    timed_out=False,
                )
        return SubprocessResult(
            returncode=0,
            stdout=_ndjson_bytes(_passing_events()),
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.engine_version is None
    # `nextest_version` is omitted from `metadata` entirely when its
    # probe fails — the typed slot is `dict[str, str]` so a `None`
    # value is not representable, and absence is more informative than
    # a literal ``"None"`` string. The payload no longer carries the
    # key in any form post the 2026-05-30 typed-slot migration.
    assert "nextest_version" not in result.metadata
    assert "nextest_version" not in result.payload


def test_build_child_env_pins_nextest_libtest_json_gate() -> None:
    """`_build_child_env()` must set the env var nextest needs to accept
    ``--message-format=libtest-json``.

    `cargo-nextest` ≥ 0.9.50 (our supported floor — see
    `decisions/2026-05-25-supported-engine-matrix.md`) gates the
    ``--message-format=libtest-json`` flag behind
    ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1``. Without it, nextest exits
    95 with a runtime error, the adapter writes zero events, and the
    build-failure heuristic misclassifies the failure as
    ``adapter-unparseable-output``. Pin the env var's presence so the
    gate cannot regress silently. The other three determinism env vars
    (``CARGO_TERM_COLOR`` / ``RUST_BACKTRACE`` / ``NO_COLOR``) are
    pinned in the same assertion block for symmetry.
    """

    env = _build_child_env()

    assert env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] == "1"
    assert env["CARGO_TERM_COLOR"] == "never"
    assert env["RUST_BACKTRACE"] == "1"
    assert env["NO_COLOR"] == "1"


# ---------------------------------------------------------------------------
# artifact_dir.resolve() hardening (2026-06-08, B2-4 cycle)
# ---------------------------------------------------------------------------
#
# `run_cargo` calls ``artifact_dir = artifact_dir.resolve()`` as the
# first line of the function body. See ``test_pytest_adapter.py``'s
# parallel block for the long-form rationale.


async def test_relative_artifact_dir_resolves_against_cwd(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative ``artifact_dir`` should resolve against the test's cwd."""

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=_passing_events()),
    )
    monkeypatch.chdir(tmp_path)
    rel_artifact_dir = Path("rel-art")
    expected_root = (tmp_path / "rel-art").resolve()

    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=rel_artifact_dir, timeout=60.0)

    assert (expected_root / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert expected_root in path.parents, (
            f"{key} → {path} is not under {expected_root}"
        )


async def test_absolute_artifact_dir_unchanged_after_resolve(
    cargo_test_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute ``artifact_dir`` should round-trip through resolve."""

    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=_passing_events()),
    )
    abs_artifact_dir = (tmp_path / "abs-art").resolve()
    target = resolve_test_target("", cargo_test_basic_workspace)
    result = await run_cargo(target, artifact_dir=abs_artifact_dir, timeout=60.0)

    assert (abs_artifact_dir / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert abs_artifact_dir in path.parents, (
            f"{key} → {path} is not under {abs_artifact_dir}"
        )
