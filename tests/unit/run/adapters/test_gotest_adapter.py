"""Unit tests for the ``go test`` Native Engine adapter.

The adapter spawns ``go test -json`` as a subprocess. To avoid requiring
Go in every CI cell, every test here stubs the subprocess seam via
``monkeypatch`` on ``novetest.run.adapters.gotest_adapter.run_subprocess``,
and the ``_stub_go_on_path`` autouse fixture stubs ``shutil.which`` so
the adapter's up-front `go` resolution succeeds on a Go-less box.

The integration tests under ``tests/integration/run/`` exercise the real
binary and skip when Go is absent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from novetest.run.adapters.gotest_adapter import (
    EVENTS_JSONL_FILENAME,
    STDERR_LOG_FILENAME,
    STDOUT_LOG_FILENAME,
    run_gotest,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target
from novetest.utils.asyncio_subprocess import SubprocessResult


_FAKE_GO = "/usr/bin/go"


@pytest.fixture(autouse=True)
def _stub_go_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every adapter test run as if `go` is resolvable on PATH.

    `run_gotest` calls `shutil.which("go")` before spawning; on a Go-less
    box that returns ``None`` and the adapter raises `missing-binary`
    before the stubbed subprocess is ever reached. Default every test to
    a resolvable `go`; the missing-binary test overrides this.
    """

    monkeypatch.setattr(shutil, "which", lambda name: _FAKE_GO)


def _ndjson_bytes(events: list[dict[str, Any]]) -> bytes:
    """Serialize a list of go-test events as NDJSON bytes (one per line)."""

    return ("\n".join(json.dumps(e) for e in events) + "\n").encode("utf-8")


def _passing_events() -> list[dict[str, Any]]:
    """A canonical event stream for a single passing test."""

    return [
        {
            "Time": "2026-05-28T00:00:00Z",
            "Action": "run",
            "Package": "example.com/foo",
            "Test": "TestAdd",
        },
        {
            "Time": "2026-05-28T00:00:00Z",
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestAdd",
            "Output": "=== RUN   TestAdd\n",
        },
        {
            "Time": "2026-05-28T00:00:00Z",
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestAdd",
            "Output": "--- PASS: TestAdd (0.00s)\n",
        },
        {
            "Time": "2026-05-28T00:00:00Z",
            "Action": "pass",
            "Package": "example.com/foo",
            "Test": "TestAdd",
            "Elapsed": 0.001,
        },
        # Package-level terminal action (no Test field) — must be
        # captured in `events` but not attributed to any test row.
        {
            "Time": "2026-05-28T00:00:00Z",
            "Action": "pass",
            "Package": "example.com/foo",
            "Elapsed": 0.002,
        },
    ]


def _failing_events() -> list[dict[str, Any]]:
    """An event stream for a single failing test with multi-line output."""

    return [
        {"Action": "run", "Package": "example.com/foo", "Test": "TestSubtract"},
        {
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestSubtract",
            "Output": "=== RUN   TestSubtract\n",
        },
        {
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestSubtract",
            "Output": "    math_test.go:18: Subtract(10, 4) = 6, want 5\n",
        },
        {
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestSubtract",
            "Output": "--- FAIL: TestSubtract (0.00s)\n",
        },
        {
            "Action": "fail",
            "Package": "example.com/foo",
            "Test": "TestSubtract",
            "Elapsed": 0.001,
        },
        # Package-level fail (no Test).
        {"Action": "fail", "Package": "example.com/foo", "Elapsed": 0.001},
    ]


def _subtest_events() -> list[dict[str, Any]]:
    """An event stream covering one parent test with two passing subtests."""

    return [
        {"Action": "run", "Package": "example.com/foo", "Test": "TestParent"},
        {"Action": "run", "Package": "example.com/foo", "Test": "TestParent/zero"},
        {
            "Action": "output",
            "Package": "example.com/foo",
            "Test": "TestParent/zero",
            "Output": "    --- PASS: TestParent/zero (0.00s)\n",
        },
        {
            "Action": "pass",
            "Package": "example.com/foo",
            "Test": "TestParent/zero",
            "Elapsed": 0,
        },
        {"Action": "run", "Package": "example.com/foo", "Test": "TestParent/one"},
        {
            "Action": "pass",
            "Package": "example.com/foo",
            "Test": "TestParent/one",
            "Elapsed": 0,
        },
        {"Action": "pass", "Package": "example.com/foo", "Test": "TestParent", "Elapsed": 0.001},
    ]


def _make_stub_subprocess(
    *,
    returncode: int = 0,
    events: list[dict[str, Any]] | None = None,
    write_cover_profile: bool = False,
    stdout_bytes: bytes | None = None,
    stderr_bytes: bytes = b"",
    timed_out: bool = False,
    raise_file_not_found: bool = False,
) -> Any:
    """Build an async stub for `run_subprocess` that emulates one go-test run.

    The stub inspects argv for ``-coverprofile=`` and writes a minimal
    ``mode: atomic`` file there if ``write_cover_profile`` is True — same
    pattern as the jest adapter's coverage stub.
    """

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if raise_file_not_found:
            raise FileNotFoundError(2, "No such file or directory: 'go'")
        # Distinguish the `go version` subprocess from the `go test` one.
        # The version probe argv is exactly `[<go>, "version"]`.
        if (
            isinstance(argv, (list, tuple))
            and len(argv) == 2
            and argv[-1] == "version"
        ):
            return SubprocessResult(
                returncode=0,
                stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"",
                timed_out=False,
            )
        if write_cover_profile:
            cover_arg = next(
                (a for a in argv if isinstance(a, str) and a.startswith("-coverprofile=")),
                None,
            )
            assert cover_arg is not None, "stub go-test invocation missing -coverprofile"
            cover_path = Path(cover_arg.split("=", 1)[1])
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_text(
                "mode: atomic\n"
                "example.com/foo/bar.go:3.13,5.2 1 1\n",
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
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(events=_passing_events()),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    assert result.engine_name == "go-test"
    assert result.returncode == 0
    payload = result.payload
    assert isinstance(payload["events"], list)
    assert payload["packages"] == ["example.com/foo"]
    assert "failure_logs" in payload

    events_path = result.artifact_paths["gotest_events_jsonl"]
    assert events_path.name == EVENTS_JSONL_FILENAME
    assert events_path.is_file()
    # The on-disk NDJSON file must round-trip cleanly.
    written_events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(written_events) == len(_passing_events())

    stdout_path = result.artifact_paths["stdout"]
    stderr_path = result.artifact_paths["stderr"]
    assert stdout_path.name == STDOUT_LOG_FILENAME
    assert stderr_path.name == STDERR_LOG_FILENAME
    assert result.engine_version == "1.23.4"


async def test_argv_uses_default_target_when_expression_empty(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty `target_expression` defaults to `./...` (all packages)."""

    import novetest.run.adapters.gotest_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"", timed_out=False,
            )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target("", gotest_basic_workspace)
    await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    # Canonical flags + default target.
    assert "test" in captured_argv
    assert "-json" in captured_argv
    assert "-count=1" in captured_argv
    assert any(a.startswith("-timeout=") for a in captured_argv)
    assert captured_argv[-1] == "./..."


async def test_argv_go_timeout_is_below_subprocess_budget(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUN-20 regression pin. go's ``-timeout`` is set strictly BELOW the
    subprocess wall-clock budget (a 10% reserve, floored at 1s) so go's
    graceful panic-dump self-termination wins the race against the parent's
    hard ``proc.kill()``. With a 60s caller budget the derived flag is
    ``-timeout=54s`` (``int(60 * 0.9)``); a ``timeout=None`` caller (no
    subprocess wall clock) keeps go's ``-timeout=600s`` default as the sole
    guard.

    A/B honesty proof: restore ``int(timeout)`` for go's ``-timeout`` →
    the 54s assertion fails (the flag equals the 60s subprocess budget).
    """

    import novetest.run.adapters.gotest_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"", timed_out=False,
            )
        captured_argv.clear()
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)
    target = resolve_test_target("", gotest_basic_workspace)

    await run_gotest(target, artifact_dir=tmp_path / "a", timeout=60.0)
    assert "-timeout=54s" in captured_argv
    assert "-timeout=60s" not in captured_argv

    # timeout=None → no subprocess wall clock; go's -timeout is the sole
    # guard and keeps the 600s default.
    await run_gotest(target, artifact_dir=tmp_path / "b", timeout=None)
    assert "-timeout=600s" in captured_argv


async def test_argv_converts_directory_dot_to_recursive_wildcard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUN-01 wiring: a `.` directory target reaches `go test` as `./...`.

    Pre-fix, `.` was appended verbatim → `go test -json … .` ran the ROOT
    package only, non-recursively — a module whose tests live in
    subpackages ran zero tests, exited 0, and normalized to
    ``status="passed"`` (silent false green).
    """

    import novetest.run.adapters.gotest_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"", timed_out=False,
            )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    workspace = tmp_path / "ws"
    workspace.mkdir()
    artifact_dir = tmp_path / "artifacts"
    target = resolve_test_target(".", workspace)
    assert target.target_type == "directory"
    await run_gotest(target, artifact_dir=artifact_dir, timeout=60.0)

    assert captured_argv[-1] == "./..."


# ---------------------------------------------------------------------------
# `_go_target_args` conversion table (RUN-01, W1/S1)
# ---------------------------------------------------------------------------
#
# The pure conversion function is tested directly against `TestTarget`s
# produced by the real `resolve_test_target` classifier, so the table
# below pins the adapter-visible contract end to end (classification →
# argv elements) without a subprocess. The wiring into `run_gotest`'s
# argv is covered by `test_argv_converts_directory_dot_to_recursive_wildcard`
# above and by `tests/integration/run/test_gotest_subpackages.py` against
# a real `go` binary.


def _workspace_with_pkg(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "pkg" / "sub").mkdir(parents=True)
    return workspace


def test_target_args_empty_expression_defaults_to_recursive(tmp_path: Path) -> None:
    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("", _workspace_with_pkg(tmp_path))
    assert _go_target_args(target) == ["./..."]


def test_target_args_directory_dot_converts_to_recursive(tmp_path: Path) -> None:
    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target(".", _workspace_with_pkg(tmp_path))
    assert target.target_type == "directory"
    assert _go_target_args(target) == ["./..."]


def test_target_args_directory_converts_to_relative_recursive(tmp_path: Path) -> None:
    """`pkg` (the normalized form of `./pkg`) → `./pkg/...`.

    Pre-fix the bare `pkg` reached `go test` verbatim, was read as an
    IMPORT PATH (`package pkg is not in std`), failed before compiling,
    and surfaced as a fake `unparseable-output` build failure.
    """

    from novetest.run.adapters.gotest_adapter import _go_target_args

    workspace = _workspace_with_pkg(tmp_path)
    target = resolve_test_target("pkg", workspace)
    assert target.target_type == "directory"
    assert _go_target_args(target) == ["./pkg/..."]

    nested = resolve_test_target("pkg/sub", workspace)
    assert nested.target_type == "directory"
    assert _go_target_args(nested) == ["./pkg/sub/..."]


def test_target_args_directory_with_dot_slash_prefix_normalizes(tmp_path: Path) -> None:
    """Direct workflow-API callers may pass `./pkg` unnormalized."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("./pkg", _workspace_with_pkg(tmp_path))
    assert target.target_type == "directory"
    assert _go_target_args(target) == ["./pkg/..."]


def test_target_args_nodeid_decomposes_to_run_filter(tmp_path: Path) -> None:
    """`pkg::TestAdd` → `-run '^TestAdd$' ./pkg` (anchored, dir-form pkg)."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("pkg::TestAdd", _workspace_with_pkg(tmp_path))
    assert target.target_type == "nodeid"
    assert _go_target_args(target) == ["-run", "^TestAdd$", "./pkg"]


def test_target_args_nodeid_import_path_package_passes_verbatim(
    tmp_path: Path,
) -> None:
    """RunRecord node ids carry full import paths — valid selectors as-is."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target(
        "example.com/foo::TestAdd", _workspace_with_pkg(tmp_path)
    )
    assert _go_target_args(target) == ["-run", "^TestAdd$", "example.com/foo"]


def test_target_args_nodeid_subtest_anchors_each_level(tmp_path: Path) -> None:
    """`go test -run` splits on `/` per subtest level; each level anchored."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target(
        "pkg::TestParent/zero_left", _workspace_with_pkg(tmp_path)
    )
    assert _go_target_args(target) == [
        "-run",
        "^TestParent$/^zero_left$",
        "./pkg",
    ]


def test_target_args_nodeid_escapes_regex_metacharacters(tmp_path: Path) -> None:
    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("pkg::TestAdd(x+1)", _workspace_with_pkg(tmp_path))
    args = _go_target_args(target)
    assert args[0] == "-run"
    assert args[1] == r"^TestAdd\(x\+1\)$"
    assert args[2] == "./pkg"


def test_target_args_degenerate_nodeid_without_test_half_runs_package(
    tmp_path: Path,
) -> None:
    """`pkg::` has no test half — run the package (never `-run '^$'`,
    which would silently select zero tests)."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("pkg::", _workspace_with_pkg(tmp_path))
    assert _go_target_args(target) == ["./pkg"]


def test_target_args_engine_native_patterns_pass_verbatim(tmp_path: Path) -> None:
    """All-dots components are go wildcard syntax — never converted.

    The check is lexical (before the `target_type` dispatch) because
    Win32 strips trailing dots from path components, so `./...` can be
    misclassified as a directory there — same trap as
    `normalize_target_expression`'s guard (2026-07-04).
    """

    from novetest.run.adapters.gotest_adapter import _go_target_args

    workspace = _workspace_with_pkg(tmp_path)
    for pattern in ("./...", "pkg/...", "..."):
        target = resolve_test_target(pattern, workspace)
        assert _go_target_args(target) == [pattern], pattern


def test_target_args_file_target_passes_verbatim(tmp_path: Path) -> None:
    """File targets keep pre-W1/S1 verbatim behavior (out of slice scope)."""

    from novetest.run.adapters.gotest_adapter import _go_target_args

    target = resolve_test_target("math_test.go", _workspace_with_pkg(tmp_path))
    assert target.target_type == "file"
    assert _go_target_args(target) == ["math_test.go"]


async def test_failing_test_writes_failure_log(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing test's buffered Output events land in a per-test log file."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=1, events=_failing_events()),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    failure_logs = result.payload["failure_logs"]
    assert isinstance(failure_logs, dict)
    assert "example.com/foo::TestSubtract" in failure_logs
    rel_path = failure_logs["example.com/foo::TestSubtract"]
    assert isinstance(rel_path, str)
    # The relative path resolves under the artifact_dir.
    abs_failure_log = tmp_path / rel_path
    assert abs_failure_log.is_file()
    body = abs_failure_log.read_text(encoding="utf-8")
    # Multi-line buffered output was concatenated in event order.
    assert "=== RUN   TestSubtract" in body
    assert "Subtract(10, 4) = 6, want 5" in body
    assert "--- FAIL: TestSubtract" in body
    # Filename safety: `/` in the package path replaced with `_`,
    # and `::` between Package and Test replaced with `__`.
    assert abs_failure_log.name == "example.com_foo__TestSubtract.log"


async def test_subtests_produce_parent_and_child_node_ids(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subtests appear as ``<Package>::<Parent>/<Child>`` in the events; both
    the parent and each subtest yield events (the normalizer turns those
    into TestResult rows — verified via the test_normalizer suite — but
    here we only assert the adapter preserves the event shape faithfully).
    """

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(events=_subtest_events()),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    events = result.payload["events"]
    assert isinstance(events, list)
    seen_tests = {
        e["Test"]
        for e in events
        if isinstance(e, dict) and isinstance(e.get("Test"), str)
    }
    assert "TestParent" in seen_tests
    assert "TestParent/zero" in seen_tests
    assert "TestParent/one" in seen_tests


async def test_build_failure_returns_payload_that_normalizes_to_errored(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build failure (corrupt `go.mod`, syntax error in the SuT —
    empty stdout + non-zero exit, no `run` action) is a USER error, not
    an adapter failure (W2/S15 rider, routed from the W1/S8 close;
    morally identical to a pytest import error): the adapter returns a
    NativeResult whose payload normalizes to a persisted ``errored``
    Run Record (zero test results) → exit 3, with the build detail
    preserved in the stderr artifact.

    Pre-S15 this shape raised ``AdapterInvocationError`` kind
    ``unparseable-output`` (exit 4) — reverting the classification in
    `run_gotest` fails this test with that raise (the A/B proof for
    wire delta C).
    """

    from novetest.run.normalizer import normalize_native_result
    from novetest.run.types import NativeEngineContext

    import novetest.run.adapters.gotest_adapter as adapter

    build_stderr = (
        b"./broken.go:4:12: undefined: notAnIdentifier\n"
        b"FAIL\texample.com/broken [build failed]\n"
    )
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=2,
            stdout_bytes=b"",
            stderr_bytes=build_stderr,
        ),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    assert result.returncode == 2
    assert result.payload["events"] == []
    # Build detail preserved in the stderr artifact.
    assert result.artifact_paths["stderr"].read_bytes() == build_stderr

    record = normalize_native_result(
        result,
        NativeEngineContext(ecosystem="go", engine_name="go-test"),
        target_expression="",
        target_type="workspace",
    )
    assert record.status == "errored"
    assert record.test_results == ()


async def test_build_failure_with_coverage_omits_profile_and_does_not_raise(
    gotest_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build failure + ``collect_coverage=True``: no cover profile was
    written, but that is a consequence of the USER-side build failure —
    the missing-profile `unparseable-output` raise must NOT fire, and the
    ``coverage_profile`` artifact key is omitted (downstream `coverage`
    verbs report unavailable for this run)."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=1,
            stdout_bytes=b"",
            stderr_bytes=b"go: errors parsing go.mod:\n"
            b"go.mod:1: unknown directive: modle\n",
            write_cover_profile=False,
        ),
    )

    target = resolve_test_target("", gotest_basic_coverage_workspace)
    result = await run_gotest(
        target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
    )
    assert result.returncode == 1
    assert "coverage_profile" not in result.artifact_paths


async def test_skip_action_does_not_trigger_build_failure(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A package with no tests emits ``Action: skip`` at the package level
    and exits 0 — must NOT be flagged as a build failure. (Discriminant:
    build failure requires non-zero returncode.)
    """

    import novetest.run.adapters.gotest_adapter as adapter

    events = [{"Action": "skip", "Package": "example.com/foo"}]
    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=events),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.returncode == 0
    assert result.payload["events"] == events


async def test_unresolvable_go_raises_typed_error(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `shutil.which("go")` returns None, the adapter raises
    ``missing-binary`` up front — before any subprocess spawn."""

    monkeypatch.setattr(shutil, "which", lambda name: None)

    target = resolve_test_target("", gotest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_gotest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"
    assert exc_info.value.install_hint is not None
    assert "Go 1.21" in exc_info.value.install_hint


async def test_launcher_exec_failure_maps_to_missing_binary(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `FileNotFoundError` from the spawn itself (TOCTOU race) still
    maps to ``missing-binary``."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(raise_file_not_found=True),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_gotest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"


async def test_timeout_maps_to_typed_error(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=-9, stdout_bytes=b"", timed_out=True,
        ),
    )

    target = resolve_test_target("", gotest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_gotest(target, artifact_dir=tmp_path, timeout=0.1)
    assert exc_info.value.kind == "timed-out"


async def test_malformed_json_lines_are_skipped(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive parsing: a malformed line in the middle of the stream
    must not abort the rest. Surrounding valid events still parse.
    """

    import novetest.run.adapters.gotest_adapter as adapter

    valid_event = {"Action": "pass", "Package": "example.com/foo", "Test": "TestX"}
    valid_line = json.dumps(valid_event)
    stdout_bytes = (
        valid_line + "\n" + "{not valid json\n" + valid_line + "\n"
    ).encode("utf-8")

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, stdout_bytes=stdout_bytes),
    )
    # The first event is `pass` not `run`, so the build-failure
    # short-circuit would trigger if returncode != 0; the stub uses 0
    # here to isolate the malformed-line behaviour.
    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)
    events = result.payload["events"]
    assert isinstance(events, list)
    assert len(events) == 2  # malformed line dropped, two valid survive


async def test_collect_coverage_false_omits_flags_and_artifact(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default path: no `-cover` flags in argv; no `coverage_profile` key."""

    import novetest.run.adapters.gotest_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"", timed_out=False,
            )
        captured_argv.extend(argv)
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)

    assert not any(arg.startswith("-cover") for arg in captured_argv)
    assert "coverage_profile" not in result.artifact_paths


async def test_collect_coverage_adds_flags_and_registers_artifact(
    gotest_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``collect_coverage=True`` adds the cover-profile flags and registers
    `cover.out` under the ``coverage_profile`` key.

    The key is deliberately NOT ``coverage_json`` (that's reserved for
    Istanbul / coverage.py JSON) — see the gotest adapter docstring.
    """

    import novetest.run.adapters.gotest_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.23.4 linux/amd64\n",
                stderr=b"", timed_out=False,
            )
        captured_argv.extend(argv)
        cover_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("-coverprofile=")),
            None,
        )
        assert cover_arg is not None
        cover_path = Path(cover_arg.split("=", 1)[1])
        cover_path.parent.mkdir(parents=True, exist_ok=True)
        cover_path.write_text("mode: atomic\nx.go:1.1,2.2 1 1\n", encoding="utf-8")
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", gotest_basic_coverage_workspace)
    result = await run_gotest(
        target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
    )

    assert "-cover" in captured_argv
    assert any(a.startswith("-coverprofile=") for a in captured_argv)
    assert "-covermode=atomic" in captured_argv
    assert "-coverpkg=./..." in captured_argv

    coverage_path = result.artifact_paths["coverage_profile"]
    assert coverage_path.name == "cover.out"
    assert coverage_path.is_file()
    assert coverage_path.read_text(encoding="utf-8").startswith("mode: atomic")


async def test_collect_coverage_missing_profile_raises_unparseable(
    gotest_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the cover profile does not land (misconfigured `go test` or a
    workspace permission issue), surface a typed ``unparseable-output``
    error rather than registering a missing file."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=0, events=_passing_events(), write_cover_profile=False,
        ),
    )

    target = resolve_test_target("", gotest_basic_coverage_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_gotest(
            target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
        )
    assert exc_info.value.kind == "unparseable-output"


async def test_engine_version_parsed_from_go_version_output(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`go version` → engine_version stripped of the leading "go" prefix."""

    import novetest.run.adapters.gotest_adapter as adapter

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=0, stdout=b"go version go1.22.0 darwin/arm64\n",
                stderr=b"", timed_out=False,
            )
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.engine_version == "1.22.0"


async def test_engine_version_returns_none_on_unparseable_output(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`go version` failures / weird output → engine_version=None (silent)."""

    import novetest.run.adapters.gotest_adapter as adapter

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and len(argv) == 2 and argv[-1] == "version":
            return SubprocessResult(
                returncode=1, stdout=b"", stderr=b"go: command not found\n",
                timed_out=False,
            )
        return SubprocessResult(
            returncode=0, stdout=_ndjson_bytes(_passing_events()),
            stderr=b"", timed_out=False,
        )

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=tmp_path, timeout=60.0)
    assert result.engine_version is None


# ---------------------------------------------------------------------------
# artifact_dir.resolve() hardening (2026-06-08, B2-4 cycle)
# ---------------------------------------------------------------------------
#
# `run_gotest` calls ``artifact_dir = artifact_dir.resolve()`` as the
# first line of the function body. See ``test_pytest_adapter.py``'s
# parallel block for the long-form rationale.


async def test_relative_artifact_dir_resolves_against_cwd(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative ``artifact_dir`` should resolve against the test's cwd."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=_passing_events()),
    )
    monkeypatch.chdir(tmp_path)
    rel_artifact_dir = Path("rel-art")
    expected_root = (tmp_path / "rel-art").resolve()

    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=rel_artifact_dir, timeout=60.0)

    assert (expected_root / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert expected_root in path.parents, (
            f"{key} → {path} is not under {expected_root}"
        )


async def test_absolute_artifact_dir_unchanged_after_resolve(
    gotest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute ``artifact_dir`` should round-trip through resolve."""

    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, events=_passing_events()),
    )
    abs_artifact_dir = (tmp_path / "abs-art").resolve()
    target = resolve_test_target("", gotest_basic_workspace)
    result = await run_gotest(target, artifact_dir=abs_artifact_dir, timeout=60.0)

    assert (abs_artifact_dir / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert abs_artifact_dir in path.parents, (
            f"{key} → {path} is not under {abs_artifact_dir}"
        )
