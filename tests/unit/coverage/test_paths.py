"""Unit tests for `novetest.coverage._paths`.

Exercises the shared workspace-relativization helper used by the
istanbul / lcov / cobertura parsers. The Windows cross-drive
``ValueError`` path is simulated on every platform via monkeypatching
``os.path.relpath`` so the third (drive-stripped POSIX) step is
guaranteed to be exercised on the Linux CI host.

Why this matters: the 2026-06-09 Windows-parser-fix slice was triggered
by 4 RED tests on the ci.yml Windows × Python 3.11/3.12/3.13 matrix.
Adding Linux-side coverage for the simulated cross-drive case ensures a
future regression that re-breaks this fallback is caught BEFORE it
escapes to Windows-only CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from novetest.coverage._paths import (
    relpath_or_drive_stripped,
    to_workspace_relative_posix,
)


# --- step 1: subpath (clean POSIX, no ``..``) --------------------------------


def test_subpath_returns_clean_posix(tmp_path: Path) -> None:
    inside = tmp_path / "src" / "lib.rs"
    assert to_workspace_relative_posix(inside, tmp_path) == "src/lib.rs"


def test_subpath_top_level_file(tmp_path: Path) -> None:
    inside = tmp_path / "README.md"
    assert to_workspace_relative_posix(inside, tmp_path) == "README.md"


# --- step 2: ``os.path.relpath`` fallback (``..``-prefixed) ------------------


def test_sibling_path_yields_dotdot_relpath(tmp_path: Path) -> None:
    """A path adjacent to workspace_root resolves via os.path.relpath
    and starts with ``..`` segments."""
    sibling = tmp_path.parent / "neighbor" / "src" / "lib.rs"
    out = to_workspace_relative_posix(sibling, tmp_path)
    assert out.startswith("../"), f"expected ../-prefix, got {out!r}"
    assert out.endswith("neighbor/src/lib.rs"), f"got {out!r}"
    # Never absolute (the universal contract).
    assert not Path(out).is_absolute()


# --- step 3: cross-drive ValueError fallback (drive-stripped) ---------------


def test_cross_drive_value_error_falls_back_to_drive_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When `os.path.relpath` raises ValueError (Windows cross-drive),
    the helper falls back to a POSIX form of the input path with the
    leading drive prefix and slash stripped."""

    def _raising_relpath(path: object, start: object = os.curdir) -> str:  # noqa: ARG001
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", _raising_relpath)

    outside = Path("/abs/path/to/workspace/MathLib/MathOps.cs")
    out = to_workspace_relative_posix(outside, tmp_path)
    # Step 3 strips the leading "/" — result is syntactically relative.
    assert out == "abs/path/to/workspace/MathLib/MathOps.cs"
    assert not Path(out).is_absolute()


def test_cross_drive_value_error_returned_via_relpath_or_drive_stripped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The step-2/step-3 half of the helper (used by cobertura's loop
    fallback and lcov's outside-workspace branch) also catches the
    cross-drive ValueError and emits the drive-stripped POSIX form."""

    def _raising_relpath(path: object, start: object = os.curdir) -> str:  # noqa: ARG001
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", _raising_relpath)

    outside = Path("/elsewhere/cargo-build-script/generated.rs")
    out = relpath_or_drive_stripped(outside, tmp_path)
    assert out == "elsewhere/cargo-build-script/generated.rs"
    assert not Path(out).is_absolute()


def test_drive_stripped_handles_windows_style_drive_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regex tolerates a literal ``C:``-style prefix that
    ``PurePath.as_posix()`` would emit on Windows for an explicit drive
    (``WindowsPath("C:/foo").as_posix() == "C:/foo"``).
    """

    def _raising_relpath(path: object, start: object = os.curdir) -> str:  # noqa: ARG001
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", _raising_relpath)

    # Simulate a path whose POSIX representation has a drive prefix.
    # We can't construct an actual WindowsPath on a POSIX host, so we
    # exercise the regex by passing a Path whose string starts with
    # ``C:`` — Path treats ``C:foo`` as POSIX-relative on Linux, but the
    # regex on the as_posix() string still strips the ``C:`` literal.
    out = relpath_or_drive_stripped(Path("C:/projects/repo/src/lib.rs"), tmp_path)
    assert out == "projects/repo/src/lib.rs"
    assert not Path(out).is_absolute()


# --- universal contract: result never absolute ------------------------------


@pytest.mark.parametrize(
    "input_path",
    [
        "/abs/path/to/lib.rs",
        "/abs/path/to/workspace/sub/lib.rs",
        "lib.rs",  # already-relative
    ],
)
def test_result_never_absolute(input_path: str, tmp_path: Path) -> None:
    """Universal contract from decision 2026-05-15 amend 2026-06-08:
    ``not Path(file_path).is_absolute()`` MUST hold for every input."""
    out = to_workspace_relative_posix(Path(input_path), tmp_path)
    assert not Path(out).is_absolute(), (
        f"absolute path leaked through: input={input_path!r}, out={out!r}"
    )
