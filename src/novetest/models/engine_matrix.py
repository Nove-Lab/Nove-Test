"""Supported (ecosystem, engine) pair matrix — shared domain constant.

``SUPPORTED_ENGINE_PAIRS`` is the supported ``(ecosystem, engine_name)``
matrix per decision ``agent-comms/decisions/2026-05-25-supported-engine-matrix.md``
("native engines stay user-owned; drift is mitigated by a supported matrix").
Row order is meaningful: it mirrors the canonical detection-priority order of
REQ-RUN-006 (earlier row wins on a polyglot workspace).

Promoted here from ``run/engine_selector.py`` (XCT-13 / S43) so peer layers —
Memory's pin validation today, potentially the CLI tomorrow — reference the
domain constant without importing upward into ``run``. ``run/engine_selector.py``
still derives its own equal copy from ``_ENGINE_MARKER_TABLE`` (the ordered
marker/priority table, which carries workspace-marker globs this constant does
not need); collapsing that duplication onto this module is routed to the next
run-team slice. Until then the divergence guard in
``tests/unit/models/test_engine_matrix.py`` pins the two tuples exactly equal
— a new ecosystem must land in BOTH places (plus the marker table) in one
change, or the guard fails loudly.
"""

from __future__ import annotations


SUPPORTED_ENGINE_PAIRS: tuple[tuple[str, str], ...] = (
    ("python", "pytest"),
    ("javascript-typescript", "jest"),
    ("java", "junit"),
    ("go", "go-test"),
    ("rust", "cargo-test"),
    ("dotnet", "xunit"),
)
