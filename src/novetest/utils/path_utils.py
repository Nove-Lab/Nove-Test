"""Project-wide cross-platform workspace-relative path utility.

Centralizes the workspace-relative-POSIX relativization logic used
across the Coverage parsers (istanbul / lcov / cobertura) AND the
Localization ``failure_proximity`` mode, with a Windows cross-drive
fallback path that ``os.path.relpath`` does NOT cover on its own.

History
-------

The utility was originally introduced under ``novetest.coverage._paths``
by the 2026-06-09 Windows-CI fix triple (Coverage commit ``4110645``).
Localization independently implemented the same scenario A pattern
inline (``failure_proximity._normalize_to_workspace_relative``). PM
disposition #3 of
``agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md``
named the scenario A pattern as the project-wide canonical idiom; this
module is the centralization step that disposition promised, lifting
the helpers from Coverage's private namespace to a project-wide
utility surface (task 2026-06-19 workspace-relpath-utility-promotion).

Why this module exists
----------------------

The 2026-06-08 amendment to ``decisions/2026-05-15-coverage-facts-json-layout.md``
mandates ``not Path(file_path).is_absolute()`` as a universal contract
for the persisted ``file_path`` field. The three coverage parsers that
handle absolute native paths (istanbul ``coverage-final.json``,
cargo-llvm-cov LCOV, Coverlet Cobertura XML) each implemented a local
``try relative_to → except: os.path.relpath`` fallback. That pattern
broke on the Windows CI runner — ``GITHUB_WORKSPACE`` lives on
``D:\\...`` while ``runner.temp`` lives on ``C:\\...``, so ANY parser
input whose path is on a third drive (or whose lack of a drive lets
``abspath`` inherit the current cwd's drive) made BOTH steps raise
``ValueError: path is on mount 'X:', start on mount 'Y:'``. The
post-2026-06-09 CI matrix had 4 Coverage tests RED solely on this
fault class.

The helper here adds a guaranteed step 3: when both
``Path.relative_to`` and ``os.path.relpath`` raise ``ValueError``, fall
back to a POSIX form of the input path with the drive prefix and
leading slash stripped. The result satisfies the universal
``not is_absolute()`` invariant on every platform, preserves the path's
structural information (so AI agents can still see "this looks like a
build-script generated file"), and never raises.

Public surface
--------------

- ``to_workspace_relative_posix(path, workspace_root) -> str``
  Three-step resolution: subpath ``a/b/c.py`` → ``../-prefixed``
  ``../../a/b/c.py`` → drive-stripped POSIX ``abs/path/c.py``.
  Always returns a POSIX-flavored, never-absolute string.

- ``relpath_or_drive_stripped(path, workspace_root) -> str``
  Just the step-2/step-3 fallback half. Used by callers (cobertura,
  lcov) that already discriminated "is the path a clean subpath?"
  themselves and only want the outside-workspace half of the logic.

- ``workspace_relpath(path, workspace_root) -> Path``
  ``Path``-typed convenience wrapper over ``to_workspace_relative_posix``
  for callers that want a ``Path`` rather than a ``str``. Internally:
  ``Path(to_workspace_relative_posix(path, workspace_root))``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePath

__all__ = [
    "relpath_or_drive_stripped",
    "to_workspace_relative_posix",
    "workspace_relpath",
]


# Matches a leading Windows drive prefix (``C:``, ``D:``, ``z:`` …) at
# the start of a POSIX-flavored string. The match deliberately does
# NOT include the slash so a subsequent ``lstrip("/")`` removes it
# uniformly across both ``"C:/foo"`` (drive-anchored) and ``"/foo"``
# (no-drive POSIX absolute) inputs.
_WINDOWS_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


def to_workspace_relative_posix(path: Path, workspace_root: Path) -> str:
    """Return a POSIX-flavored, never-absolute workspace-relative path.

    Three-step resolution; each step falls through on ``ValueError``:

    1. ``path.relative_to(workspace_root)`` → clean subpath
       (``"a/b/c.py"``).
    2. ``os.path.relpath(path, workspace_root)`` → ``../``-prefixed
       relpath (``"../../a/b/c.py"``).
    3. POSIX form of the input with the drive prefix and leading
       slashes stripped (``"abs/path/c.py"`` from
       ``"D:\\abs\\path\\c.py"`` or ``"/abs/path/c.py"``).

    Step 3 is the cross-drive fallback for Windows. On Linux / macOS
    step 2 never raises so step 3 is unreachable in normal operation —
    it exists so a single helper covers every platform with no
    platform-conditional branches at the call site.
    """
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return relpath_or_drive_stripped(path, workspace_root)


def relpath_or_drive_stripped(path: Path, workspace_root: Path) -> str:
    """Return ``os.path.relpath`` POSIX form, or drive-stripped fallback.

    Step 2/3 half of :func:`to_workspace_relative_posix`. Callers that
    have already verified the input is not a clean workspace subpath
    (e.g. the cobertura per-source-dir loop) skip step 1 and call this
    directly.
    """
    try:
        return Path(os.path.relpath(path, workspace_root)).as_posix()
    except ValueError:
        # Windows cross-drive: ``os.path.relpath`` cannot bridge two
        # paths on different drives (or one drive-less path against a
        # drive-anchored one when the current process cwd is on a
        # third drive). Emit a synthetic POSIX form preserving the
        # path's structural information but stripping the drive
        # prefix and any leading ``/`` so the result is syntactically
        # relative — satisfying ``not Path(p).is_absolute()`` on every
        # platform.
        posix = PurePath(path).as_posix()
        return _WINDOWS_DRIVE_PREFIX_RE.sub("", posix).lstrip("/")


def workspace_relpath(path: Path, workspace_root: Path) -> Path:
    """``Path``-typed convenience wrapper over :func:`to_workspace_relative_posix`.

    Equivalent to ``Path(to_workspace_relative_posix(path, workspace_root))``.
    Callers that want a ``Path`` (e.g. for further path operations like
    ``.parent`` or ``.with_suffix``) should prefer this; callers that
    persist the result as a JSON string should prefer the underlying
    ``to_workspace_relative_posix``.
    """
    return Path(to_workspace_relative_posix(path, workspace_root))
