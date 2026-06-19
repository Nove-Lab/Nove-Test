"""Project-wide utility surface for the novetest package.

Public path-normalization utilities re-exported for convenience; the
implementation lives in :mod:`novetest.utils.path_utils`.
"""

from __future__ import annotations

from novetest.utils.path_utils import (
    relpath_or_drive_stripped,
    to_workspace_relative_posix,
    workspace_relpath,
)

__all__ = [
    "relpath_or_drive_stripped",
    "to_workspace_relative_posix",
    "workspace_relpath",
]
