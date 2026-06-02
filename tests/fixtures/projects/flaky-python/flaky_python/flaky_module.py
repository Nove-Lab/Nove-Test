"""Deliberately non-deterministic behaviour for Replay flakiness fixtures.

The flakiness source is an **on-disk invocation counter** (the brief §4
"counter file on disk" option). This gives the precise property Replay needs:

- **Deterministic within a single subprocess invocation** — the counter is
  read exactly once per process, so the original `novetest run` produces a
  fixed, byte-identically-storable outcome.
- **Non-deterministic across subprocess invocations** — each subsequent
  `novetest replay` rerun is a fresh subprocess that reads the *incremented*
  counter, so successive runs of the SAME test flip outcome by parity.

Invocation 0 (the original run) → even → pass. Replay reruns then alternate
fail / pass / fail / pass / ... so a 5-rerun replay yields a divergent mix
that the classifier labels ``inconsistent``.
"""

from __future__ import annotations

from pathlib import Path


COUNTER_FILENAME = ".flaky_invocations"


def counter_path() -> Path:
    """Return the on-disk counter path at the project root.

    ``flaky_module.py`` lives at ``<root>/flaky_python/flaky_module.py``, so
    ``parents[1]`` is the project root regardless of the process cwd.
    """
    return Path(__file__).resolve().parents[1] / COUNTER_FILENAME


def next_invocation_index(path: Path | None = None) -> int:
    """Return the current invocation index and increment the on-disk counter.

    Reads the counter exactly once (deterministic within the process), then
    persists ``index + 1`` so the next subprocess sees a higher value.
    """
    target = path if path is not None else counter_path()
    try:
        current = int(target.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        current = 0
    target.write_text(str(current + 1), encoding="utf-8")
    return current


def flaky_outcome(path: Path | None = None) -> bool:
    """Return ``True`` on even invocations, ``False`` on odd ones."""
    return next_invocation_index(path) % 2 == 0
