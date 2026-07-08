"""Unit tests for the jest Native Engine adapter.

The adapter spawns ``npx jest`` as a subprocess. To avoid requiring Node.js
in the CI matrix, every test here stubs the subprocess seam via
``monkeypatch`` on ``novetest.run.adapters.jest_adapter.run_subprocess``,
and the ``_stub_npx_on_path`` autouse fixture stubs ``shutil.which`` so the
adapter's up-front `npx` resolution succeeds on a Node-less box.

The integration test under ``tests/integration/run/`` exercises the real
binary and skips when Node.js is absent.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from novetest.run.adapters.jest_adapter import (
    JEST_REPORT_FILENAME,
    STDERR_LOG_FILENAME,
    STDOUT_LOG_FILENAME,
    _npx_launcher,
    run_jest,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target
from novetest.utils.asyncio_subprocess import SubprocessResult


_FAKE_NPX = "/usr/bin/npx"


@pytest.fixture(autouse=True)
def _stub_npx_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every adapter test run as if `npx` is resolvable on PATH.

    `run_jest` calls `shutil.which("npx")` before spawning; on a Node-less
    box that returns ``None`` and the adapter raises `missing-binary`
    before the stubbed subprocess is ever reached. Default every test to a
    resolvable `npx`; the missing-binary test overrides this.
    """

    monkeypatch.setattr(shutil, "which", lambda name: _FAKE_NPX)


def _sample_jest_payload(success: bool = True, num_failed: int = 0) -> dict[str, Any]:
    return {
        "success": success,
        "numPassedTests": 3 - num_failed,
        "numFailedTests": num_failed,
        "numPendingTests": 0,
        "numTodoTests": 0,
        "numTotalTests": 3,
        "startTime": 1700000000000,
        "testResults": [
            {
                "name": "/abs/path/__tests__/math.test.js",
                "status": "failed" if num_failed else "passed",
                "testFilePath": "/abs/path/__tests__/math.test.js",
                "testResults": [
                    {
                        "ancestorTitles": ["math"],
                        "title": "add returns the sum of two integers",
                        "fullName": "math add returns the sum of two integers",
                        "status": "passed",
                        "duration": 5,
                        "failureMessages": [],
                        "location": {"line": 4, "column": 3},
                    },
                    {
                        "ancestorTitles": ["math"],
                        "title": "subtract returns the difference of two integers",
                        "fullName": "math subtract returns the difference of two integers",
                        "status": "passed" if num_failed == 0 else "failed",
                        "duration": 3,
                        "failureMessages": ["Expected 6 but received 7"]
                        if num_failed
                        else [],
                        "location": {"line": 8, "column": 3},
                    },
                    {
                        "ancestorTitles": ["math"],
                        "title": "add is commutative",
                        "fullName": "math add is commutative",
                        "status": "passed",
                        "duration": 1,
                        "failureMessages": [],
                        "location": {"line": 12, "column": 3},
                    },
                ],
            }
        ],
    }


def _sample_istanbul_payload() -> dict[str, Any]:
    """A minimal Istanbul ``coverage-final.json`` body.

    Keyed by absolute file path, each entry carrying the canonical
    `statementMap` / `fnMap` / `branchMap` / `s` / `f` / `b` shape. The
    adapter never inspects this content — it only registers the raw file
    — so a single-file stub is enough to prove the artifact wiring.
    """

    return {
        "/abs/path/src/classifier.js": {
            "path": "/abs/path/src/classifier.js",
            "statementMap": {"0": {"start": {"line": 7, "column": 2}}},
            "fnMap": {},
            "branchMap": {},
            "s": {"0": 1},
            "f": {},
            "b": {},
        }
    }


def _make_stub_subprocess(
    *,
    returncode: int,
    write_report: bool,
    write_coverage: bool = False,
    report_payload: dict[str, Any] | None = None,
    stderr_bytes: bytes = b"",
    stdout_bytes: bytes = b"",
    timed_out: bool = False,
    raise_file_not_found: bool = False,
) -> Any:
    """Build an async stub for `run_subprocess` that emulates one jest run.

    The stub inspects argv for ``--outputFile=`` and writes the requested
    JSON payload there if ``write_report`` is True — that's how the real
    jest CLI lands its report on disk for the adapter to read after the
    process exits. When ``write_coverage`` is True it likewise inspects
    ``--coverageDirectory=`` and drops a ``coverage-final.json`` there,
    emulating jest's ``json`` coverage reporter.
    """

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if raise_file_not_found:
            raise FileNotFoundError(2, "No such file or directory: 'npx'")
        if write_report:
            output_arg = next(
                (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
                None,
            )
            assert output_arg is not None, "stub jest invocation missing --outputFile"
            report_path = Path(output_arg.split("=", 1)[1])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report_payload if report_payload is not None else _sample_jest_payload()),
                encoding="utf-8",
            )
        if write_coverage:
            cov_dir_arg = next(
                (a for a in argv if isinstance(a, str) and a.startswith("--coverageDirectory=")),
                None,
            )
            assert cov_dir_arg is not None, "stub jest invocation missing --coverageDirectory"
            cov_dir = Path(cov_dir_arg.split("=", 1)[1])
            cov_dir.mkdir(parents=True, exist_ok=True)
            (cov_dir / "coverage-final.json").write_text(
                json.dumps(_sample_istanbul_payload()), encoding="utf-8"
            )
        return SubprocessResult(
            returncode=returncode,
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            timed_out=timed_out,
        )

    return stub


async def test_happy_path_parses_payload_and_returns_native_result(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, write_report=True),
    )

    target = resolve_test_target("__tests__/", jest_basic_workspace)
    result = await run_jest(target, artifact_dir=tmp_path, timeout=60.0)

    assert result.engine_name == "jest"
    assert result.returncode == 0
    assert result.payload["success"] is True
    assert result.payload["numTotalTests"] == 3

    report_path = result.artifact_paths["jest_json_report"]
    assert report_path.name == JEST_REPORT_FILENAME
    assert report_path.is_file()

    stdout_path = result.artifact_paths["stdout"]
    stderr_path = result.artifact_paths["stderr"]
    assert stdout_path.name == STDOUT_LOG_FILENAME
    assert stderr_path.name == STDERR_LOG_FILENAME


async def test_argv_includes_target_expression(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-empty ``target_expression`` is appended as a positional after ``--``.

    The ``--`` separator (RUN-22, W1/S1) pins the target as a test path
    pattern: yargs places everything after ``--`` into the positionals, so
    a dash-leading value can never be consumed as a jest flag. Empirically
    verified on jest 29.7.0 / Node 22 (2026-07-07): ``jest -- <pattern>``
    selects the same tests as the bare positional did.
    """

    import novetest.run.adapters.jest_adapter as adapter

    captured_argv: list[str] = []

    async def capturing_stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        captured_argv.extend(argv)
        # Still write the report so the rest of the adapter completes.
        output_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
            None,
        )
        assert output_arg is not None
        report_path = Path(output_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(_sample_jest_payload()), encoding="utf-8")
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", capturing_stub)

    target = resolve_test_target("__tests__/math.test.js", jest_basic_workspace)
    await run_jest(target, artifact_dir=tmp_path, timeout=60.0)

    # The launcher prefix is OS-specific (POSIX: resolved `npx` path;
    # Windows: `cmd /c npx`) and is covered separately by the
    # `_npx_launcher` tests. This test asserts only the OS-invariant
    # concern it exists for: jest is invoked with the canonical flags and
    # the target expression is appended as the final positional.
    assert "jest" in captured_argv
    assert "--ci" in captured_argv
    assert "--json" in captured_argv
    assert "--testLocationInResults" in captured_argv
    assert "--watchman=false" in captured_argv
    # RUN-22: the target stays the final positional, pinned by a `--`
    # separator immediately before it.
    assert captured_argv[-2:] == ["--", "__tests__/math.test.js"]


async def test_empty_target_expression_runs_full_suite(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty target should produce argv without a positional target."""

    import novetest.run.adapters.jest_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        captured_argv.extend(argv)
        output_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
            None,
        )
        assert output_arg is not None
        report_path = Path(output_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(_sample_jest_payload()), encoding="utf-8")
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", jest_basic_workspace)
    await run_jest(target, artifact_dir=tmp_path, timeout=60.0)

    # No bare-string positional (anything that does not start with `-`) after
    # the canonical flags. Use the index of `--watchman=false` as the boundary.
    assert captured_argv[-1] == "--watchman=false"


@pytest.mark.parametrize(
    "metachar_target",
    ["foo & calc.exe", "x | whoami", "t > out", "a < b", "p ^ q", "50%x", 'q "r"'],
)
async def test_shell_metachar_target_rejected_before_spawn(
    metachar_target: str,
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RUN-09 (RCE·Windows): a cmd.exe metacharacter in the target would be
    interpreted by the command interpreter on the ``cmd /c npx`` launcher
    path. The adapter rejects it as ``invalid-target`` before any spawn —
    platform-independent input validation, so this is green on Linux."""

    import novetest.run.adapters.jest_adapter as adapter

    async def bomb(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        raise AssertionError(
            f"subprocess must not spawn for a rejected target; argv={argv!r}"
        )

    monkeypatch.setattr(adapter, "run_subprocess", bomb)

    target = resolve_test_target(metachar_target, jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "invalid-target"
    assert "injection" in str(exc_info.value)


async def test_unresolvable_npx_raises_typed_error(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When `shutil.which("npx")` returns None, the adapter raises a typed
    ``missing-binary`` error up front — before any subprocess spawn."""

    monkeypatch.setattr(shutil, "which", lambda name: None)

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"
    assert exc_info.value.install_hint is not None
    assert "Node.js" in exc_info.value.install_hint


async def test_launcher_exec_failure_falls_back_to_missing_binary(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `FileNotFoundError` from the spawn itself (TOCTOU race, or a
    missing `cmd.exe` on Windows) still maps to ``missing-binary``."""

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=0, write_report=False, raise_file_not_found=True
        ),
    )

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-binary"
    assert exc_info.value.install_hint is not None
    assert "Node.js" in exc_info.value.install_hint


def test_npx_launcher_posix_uses_resolved_path() -> None:
    """On POSIX the resolved absolute `npx` path is exec'd directly."""

    assert _npx_launcher("/usr/local/bin/npx", windows=False) == ["/usr/local/bin/npx"]


def test_npx_launcher_windows_wraps_in_cmd() -> None:
    """On Windows `npx` is a `.cmd` batch shim that `CreateProcess` cannot
    run directly, so the launcher routes through `cmd.exe /c`. The bare
    name `npx` (not the resolved `.cmd` path) is handed to `cmd` so its
    `PATHEXT` resolution applies and `cmd /c`'s leading-quote-stripping
    rule is sidestepped.
    """

    launcher = _npx_launcher(
        r"C:\Program Files\nodejs\npx.cmd", windows=True
    )
    assert launcher == ["cmd", "/c", "npx"]


async def test_jest_not_installed_in_workspace_maps_to_missing_plugin(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When npx prints "could not determine executable", we report missing-plugin."""

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=1,
            write_report=False,
            stderr_bytes=b"npm ERR! could not determine executable to run\n",
        ),
    )

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "missing-plugin"
    assert exc_info.value.install_hint == "npm install --save-dev jest"


async def test_missing_report_with_unrelated_stderr_maps_to_unparseable(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If jest aborts without writing the report and stderr is unrecognized,
    we surface ``unparseable-output`` so the caller still gets a typed error.
    """

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=2,
            write_report=False,
            stderr_bytes=b"some unrelated jest error message\n",
        ),
    )

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "unparseable-output"


async def test_timeout_maps_to_typed_error(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(
            returncode=-9,
            write_report=False,
            timed_out=True,
        ),
    )

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=0.1)
    assert exc_info.value.kind == "timed-out"


async def test_report_with_invalid_json_maps_to_unparseable(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncated / corrupted report file must not raise a parse exception
    out of the adapter — it must surface as a typed error so the CLI can
    map to exit-code 4 cleanly.
    """

    import novetest.run.adapters.jest_adapter as adapter

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        output_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
            None,
        )
        assert output_arg is not None
        report_path = Path(output_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("{not json", encoding="utf-8")
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", jest_basic_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(target, artifact_dir=tmp_path, timeout=10.0)
    assert exc_info.value.kind == "unparseable-output"


async def test_collect_coverage_false_adds_no_coverage_flags(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default (coverage off) path stays byte-identical: no jest
    ``--coverage`` flags in argv, no ``coverage_json`` artifact key."""

    import novetest.run.adapters.jest_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        captured_argv.extend(argv)
        output_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
            None,
        )
        assert output_arg is not None
        report_path = Path(output_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(_sample_jest_payload()), encoding="utf-8")
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("", jest_basic_workspace)
    result = await run_jest(target, artifact_dir=tmp_path, timeout=60.0)

    assert not any(arg.startswith("--coverage") for arg in captured_argv)
    assert "coverage_json" not in result.artifact_paths


async def test_collect_coverage_adds_flags_and_registers_artifact(
    jest_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``collect_coverage=True`` adds the jest coverage flags and registers
    the Istanbul ``coverage-final.json`` under the ``coverage_json`` key.

    ``coverage_json`` is the SAME key the pytest adapter uses — pinned
    cross-team contract so the Coverage engine looks it up uniformly and
    dispatches format-handling on ``engine_name``.
    """

    import novetest.run.adapters.jest_adapter as adapter

    captured_argv: list[str] = []

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        captured_argv.extend(argv)
        output_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--outputFile=")),
            None,
        )
        assert output_arg is not None
        report_path = Path(output_arg.split("=", 1)[1])
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(_sample_jest_payload()), encoding="utf-8")
        cov_dir_arg = next(
            (a for a in argv if isinstance(a, str) and a.startswith("--coverageDirectory=")),
            None,
        )
        assert cov_dir_arg is not None
        cov_dir = Path(cov_dir_arg.split("=", 1)[1])
        cov_dir.mkdir(parents=True, exist_ok=True)
        (cov_dir / "coverage-final.json").write_text(
            json.dumps(_sample_istanbul_payload()), encoding="utf-8"
        )
        return SubprocessResult(returncode=0, stdout=b"", stderr=b"", timed_out=False)

    monkeypatch.setattr(adapter, "run_subprocess", stub)

    target = resolve_test_target("__tests__/", jest_basic_coverage_workspace)
    result = await run_jest(
        target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
    )

    assert "--coverage" in captured_argv
    assert "--coverageReporters=json" in captured_argv
    # Only the `json` reporter — never lcov / cobertura (pinned contract).
    assert not any(
        a.startswith("--coverageReporters=") and a != "--coverageReporters=json"
        for a in captured_argv
    )
    cov_dir_arg = next(a for a in captured_argv if a.startswith("--coverageDirectory="))
    cov_dir = Path(cov_dir_arg.split("=", 1)[1])
    assert cov_dir.name == "coverage"
    assert cov_dir.parent.name == "native"

    coverage_path = result.artifact_paths["coverage_json"]
    assert coverage_path.name == "coverage-final.json"
    assert coverage_path.parent.name == "coverage"
    assert coverage_path.is_file()


async def test_collect_coverage_missing_report_maps_to_unparseable(
    jest_basic_coverage_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If jest runs but Istanbul produces no ``coverage-final.json`` (e.g.
    a misconfigured ``coverageReporters``), the adapter surfaces a typed
    ``unparseable-output`` error rather than registering a missing file.
    """

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, write_report=True, write_coverage=False),
    )

    target = resolve_test_target("__tests__/", jest_basic_coverage_workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_jest(
            target, artifact_dir=tmp_path, timeout=60.0, collect_coverage=True
        )
    assert exc_info.value.kind == "unparseable-output"


async def test_engine_version_read_from_local_node_modules(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``node_modules/jest/package.json`` exists, version is captured."""

    import novetest.run.adapters.jest_adapter as adapter

    # Build a fake workspace with node_modules so the version probe succeeds.
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "package.json").write_text(
        json.dumps({"name": "x", "devDependencies": {"jest": "^29.7.0"}}),
        encoding="utf-8",
    )
    jest_pkg_dir = workspace / "node_modules" / "jest"
    jest_pkg_dir.mkdir(parents=True)
    (jest_pkg_dir / "package.json").write_text(
        json.dumps({"name": "jest", "version": "29.7.0"}),
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifacts"

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, write_report=True),
    )

    target = resolve_test_target("", workspace)
    result = await run_jest(target, artifact_dir=artifact_dir, timeout=60.0)
    assert result.engine_version == "29.7.0"


# ---------------------------------------------------------------------------
# artifact_dir.resolve() hardening (2026-06-08, B2-4 cycle)
# ---------------------------------------------------------------------------
#
# `run_jest` calls ``artifact_dir = artifact_dir.resolve()`` as the first
# line of the function body. See ``test_pytest_adapter.py``'s parallel
# block for the long-form rationale (originates from the 2026-05-16
# pytest-only TODO; this cycle generalizes to all six adapters).


async def test_relative_artifact_dir_resolves_against_cwd(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative ``artifact_dir`` should resolve against the test's cwd."""

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, write_report=True),
    )
    monkeypatch.chdir(tmp_path)
    rel_artifact_dir = Path("rel-art")
    expected_root = (tmp_path / "rel-art").resolve()

    target = resolve_test_target("", jest_basic_workspace)
    result = await run_jest(target, artifact_dir=rel_artifact_dir, timeout=60.0)

    assert (expected_root / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert expected_root in path.parents, (
            f"{key} → {path} is not under {expected_root}"
        )


async def test_absolute_artifact_dir_unchanged_after_resolve(
    jest_basic_workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute ``artifact_dir`` should round-trip through resolve."""

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(
        adapter,
        "run_subprocess",
        _make_stub_subprocess(returncode=0, write_report=True),
    )
    abs_artifact_dir = (tmp_path / "abs-art").resolve()
    target = resolve_test_target("", jest_basic_workspace)
    result = await run_jest(target, artifact_dir=abs_artifact_dir, timeout=60.0)

    assert (abs_artifact_dir / "native").is_dir()
    for key, path in result.artifact_paths.items():
        assert path.is_absolute(), f"{key} → {path} is not absolute"
        assert abs_artifact_dir in path.parents, (
            f"{key} → {path} is not under {abs_artifact_dir}"
        )
