"""Cross-engine dash-leading Test Target guard (RUN-22, W1/S1).

Pins the six-engine end-state in ONE place: a dash-leading
``target_expression`` (e.g. ``--pdb``, ``-p no:cacheprovider``) reaching
an adapter through workflow-API callers can NEVER be consumed as an
engine flag. Mechanism per engine, each chosen empirically (2026-07-07,
recorded in the W1/S1 handoff):

========  =======================================================
engine    mechanism
========  =======================================================
pytest    boundary rejection — pytest 9.0.3's ``--`` does not
          terminate option parsing (``pytest -- --collect-only``
          still runs collect-only mode)
jest      ``--`` separator — yargs pins post-``--`` tokens as
          positionals (verified on jest 29.7.0)
go test   boundary rejection — the go command has no ``--``
          terminator (``-args`` forwards to the test binary)
cargo     boundary rejection — nextest's post-``--`` position is
          TEST-BINARY args; the libtest emulation set is still
          consumed as flags (``-- --ignored`` flips selection,
          nextest 0.9.137)
junit     immune by embedding: ``-Dtest=<expr>``
dotnet    immune by embedding: ``FullyQualifiedName~<expr>``
========  =======================================================

The rejection engines raise ``AdapterInvocationError`` BEFORE any
subprocess spawn (kind ``unparseable-output`` — the kind set is pinned
unchanged by the W1/S1 data contract; see ``_target_guard``).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from novetest.run.adapters.dotnet_adapter import _build_argv as build_dotnet_argv
from novetest.run.adapters.gotest_adapter import run_gotest
from novetest.run.adapters.jest_adapter import run_jest
from novetest.run.adapters.junit_adapter import run_junit
from novetest.run.adapters.cargo_adapter import run_cargo
from novetest.run.adapters.pytest_adapter import run_pytest
from novetest.run.errors import AdapterInvocationError
from novetest.run.target_resolver import resolve_test_target


DASH_TARGETS = ["--pdb", "-p no:cacheprovider", "-run TestX", "--ignored"]


class _ArgvCaptured(Exception):
    """Sentinel raised by capture stubs to short-circuit after argv build."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__("argv captured")
        self.argv = argv


def _bomb_subprocess() -> Any:
    """A ``run_subprocess`` stand-in that must never be reached."""

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> Any:
        raise AssertionError(
            f"subprocess must not spawn for a rejected target; argv={argv!r}"
        )

    return stub


def _capturing_subprocess() -> Any:
    """A ``run_subprocess`` stand-in that records argv and short-circuits."""

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> Any:
        raise _ArgvCaptured(list(argv))

    return stub


# ---------------------------------------------------------------------------
# Rejection engines: pytest / go test / cargo-nextest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dash_target", DASH_TARGETS)
async def test_pytest_rejects_dash_leading_target_before_spawn(
    dash_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter, "run_subprocess", _bomb_subprocess())
    workspace = tmp_path / "ws"
    workspace.mkdir()

    target = resolve_test_target(dash_target, workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_pytest(target, artifact_dir=tmp_path / "art", timeout=10.0)
    assert exc_info.value.kind == "unparseable-output"
    assert "flag" in str(exc_info.value)


@pytest.mark.parametrize("dash_target", DASH_TARGETS)
async def test_gotest_rejects_dash_leading_target_before_spawn(
    dash_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.gotest_adapter as adapter

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/go")
    monkeypatch.setattr(adapter, "run_subprocess", _bomb_subprocess())
    workspace = tmp_path / "ws"
    workspace.mkdir()

    target = resolve_test_target(dash_target, workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_gotest(target, artifact_dir=tmp_path / "art", timeout=10.0)
    assert exc_info.value.kind == "unparseable-output"
    assert "flag" in str(exc_info.value)


@pytest.mark.parametrize("dash_target", DASH_TARGETS)
async def test_cargo_rejects_dash_leading_target_before_spawn(
    dash_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import novetest.run.adapters.cargo_adapter as adapter

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/cargo")
    monkeypatch.setattr(adapter, "run_subprocess", _bomb_subprocess())
    workspace = tmp_path / "ws"
    workspace.mkdir()

    target = resolve_test_target(dash_target, workspace)
    with pytest.raises(AdapterInvocationError) as exc_info:
        await run_cargo(target, artifact_dir=tmp_path / "art", timeout=10.0)
    assert exc_info.value.kind == "unparseable-output"
    assert "flag" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Separator engine: jest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dash_target", DASH_TARGETS)
async def test_jest_pins_dash_leading_target_after_separator(
    dash_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """jest keeps dash-leading patterns expressible: the value lands as the
    final positional, immediately after ``--``, never in flag position."""

    import novetest.run.adapters.jest_adapter as adapter

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/npx")
    monkeypatch.setattr(adapter, "run_subprocess", _capturing_subprocess())
    workspace = tmp_path / "ws"
    workspace.mkdir()

    target = resolve_test_target(dash_target, workspace)
    with pytest.raises(_ArgvCaptured) as exc_info:
        await run_jest(target, artifact_dir=tmp_path / "art", timeout=10.0)

    argv = exc_info.value.argv
    assert argv[-2:] == ["--", dash_target]
    # The raw value must not appear anywhere BEFORE the separator, where
    # yargs would parse it as an option.
    assert dash_target not in argv[: argv.index("--")]


# ---------------------------------------------------------------------------
# Immune-by-embedding engines: junit (-Dtest=) / dotnet (FullyQualifiedName~)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dash_target", DASH_TARGETS)
async def test_junit_embeds_dash_leading_target_in_dtest_property(
    dash_target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/mvn")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion>"
        "<groupId>x</groupId><artifactId>y</artifactId>"
        "<version>0.0.0</version></project>",
        encoding="utf-8",
    )

    import novetest.run.adapters.junit_adapter as adapter

    monkeypatch.setattr(adapter, "run_subprocess", _capturing_subprocess())

    target = resolve_test_target(dash_target, workspace)
    with pytest.raises(_ArgvCaptured) as exc_info:
        await run_junit(target, artifact_dir=tmp_path / "art", timeout=10.0)

    argv = exc_info.value.argv
    assert f"-Dtest={dash_target}" in argv
    # Never a bare argv element that Maven could parse as its own flag.
    assert dash_target not in argv


def test_dotnet_embeds_dash_leading_target_in_filter_value(
    tmp_path: Path,
) -> None:
    for dash_target in DASH_TARGETS:
        argv = build_dotnet_argv(
            dotnet_path="/usr/bin/dotnet",
            csproj_path=tmp_path / "X.Tests.csproj",
            results_dir=tmp_path / "results",
            collect_coverage=False,
            runsettings_path=None,
            target_expression=dash_target,
            target_type="file",
        )
        assert f"FullyQualifiedName~{dash_target}" in argv
        assert dash_target not in argv
        # The embedded value rides behind `--filter` as its argument.
        assert argv[argv.index(f"FullyQualifiedName~{dash_target}") - 1] == "--filter"
