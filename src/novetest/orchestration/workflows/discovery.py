"""Bounded downward discovery of candidate sub-projects for ``novetest init``.

Implements D4 of
`agent-comms/decisions/2026-07-03-engine-selection-policy.md`: when
``init`` finds no engine marker at the target directory it creates
nothing and instead reports candidate sub-projects found by a *bounded*
downward scan, so an agent can ``cd`` into a candidate and ``init`` it
itself. This module is that scan, and per D4 it is the ONLY downward
filesystem traversal anywhere in the product — every verb (D2) resolves
its workspace by walking *upward* to the nearest ``.novetest/``.

Bounds enforced here:

- Depth ``<= DISCOVERY_MAX_DEPTH`` below the scan root (direct children
  are depth 1, grandchildren depth 2).
- ``DISCOVERY_SKIP_DIRS`` are never entered.
- Symlinked directories are never followed. This is also how D4's "never
  leave the enclosing git repo" bound is satisfied without an explicit
  repo-boundary check: a purely downward walk that never follows a
  symlink can only ever reach descendants of the scan root on the real
  filesystem, so it cannot escape whatever repo (if any) encloses that
  root.
- Descent stops as soon as a directory yields at least one engine
  candidate ("stop descending once a project root is found"), so nested
  workspace members are not double-reported.
- Scanning is refused outright (no traversal at all) when the resolved
  root is a filesystem root or the user's home directory — those are
  the two directories an agent is most likely to invoke ``init`` in by
  accident, and a full scan there would be both slow and unhelpful.

The report is a courtesy, not a gate: unreadable directories are skipped
silently and projects deeper than the bound are simply not listed (they
remain fully initializable by running ``init`` there directly).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from novetest.run import detect_engine_candidates


DISCOVERY_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "target",
        ".venv",
        "venv",
        ".git",
        "dist",
        "build",
        ".novetest",
    }
)
DISCOVERY_MAX_DEPTH: int = 2


@dataclass(slots=True, frozen=True)
class DiscoveredCandidate:
    """One sub-project found below the scan root.

    ``path`` is always POSIX-form and relative to the scan root (e.g.
    ``"backend"`` or ``"services/api"``), never the root itself — callers
    only invoke `discover_candidates_below` after confirming the root has
    no marker of its own. POSIX separators are load-bearing: these
    strings flow into JSON envelopes consumed by AI agents and must
    serialize identically on Windows and POSIX hosts.
    """

    path: str
    ecosystem: str
    engine_name: str

    def to_dict(self) -> dict[str, str]:
        """Render as the plain-string mapping the CLI envelope expects."""

        return {"path": self.path, "ecosystem": self.ecosystem, "engine_name": self.engine_name}


def discover_candidates_below(root: Path) -> tuple[DiscoveredCandidate, ...] | None:
    """Scan below ``root`` for candidate sub-projects, bounded per D4.

    Returns ``None`` when the scan is refused outright (``root`` resolves
    to a filesystem root or the user's home directory) — no traversal
    happens in that case. Returns a (possibly empty) tuple otherwise:
    empty means "scanned, found nothing", which is a distinct outcome
    from a refused scan.
    """

    resolved_root = root.resolve()
    if resolved_root == Path(resolved_root.anchor) or resolved_root == Path.home().resolve():
        return None

    candidates: list[DiscoveredCandidate] = []
    _scan(resolved_root, resolved_root, depth=0, candidates=candidates)
    return tuple(candidates)


def _scan(root: Path, directory: Path, depth: int, candidates: list[DiscoveredCandidate]) -> None:
    """Depth-first, sorted-by-name walk of ``directory``, appending hits to ``candidates``."""

    try:
        children = sorted(directory.iterdir(), key=lambda entry: entry.name)
    except OSError:
        # Unreadable directory: the report is a courtesy, not a gate.
        return

    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        if child.name in DISCOVERY_SKIP_DIRS:
            continue

        engine_candidates = detect_engine_candidates(child)
        if engine_candidates:
            child_path = child.relative_to(root).as_posix()
            candidates.extend(
                DiscoveredCandidate(
                    path=child_path,
                    ecosystem=candidate.ecosystem,
                    engine_name=candidate.engine_name,
                )
                for candidate in engine_candidates
            )
            continue

        if depth + 1 < DISCOVERY_MAX_DEPTH:
            _scan(root, child, depth + 1, candidates)
