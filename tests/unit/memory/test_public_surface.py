"""Architecture guards for the Memory package boundary (XCT-12 / XCT-13, S43).

Two ratchets over the production source tree (AST-based, so docstrings and
comments mentioning module paths cannot false-positive):

1. **Public-surface ratchet (XCT-12).** Consumers outside ``memory/`` must
   import from ``novetest.memory`` only; the submodule paths
   (``novetest.memory.store`` / ``novetest.memory.project_store``) are
   private. The pre-existing deep imports in the four derived engines are
   pinned in ``_DEEP_IMPORT_ALLOWLIST`` below; the assertion is
   **offenders ⊆ allowlist** — deliberately SUBSET, not equality, because
   the flips land in parallel worktrees and merge in any order (an equality
   pin would fail merge-order-dependently). The allowlist may only SHRINK.

2. **Layering pin (XCT-13).** No module under ``src/novetest/memory/``
   imports ``novetest.run`` (the former ``set_pinned_engine`` deferred
   import was the single inversion; this keeps it from creeping back).
   Memory validates engine pins against
   ``novetest.models.engine_matrix.SUPPORTED_ENGINE_PAIRS`` instead —
   models sits BELOW memory, so the reference is downward.

Tests are exempt from both policies (this file itself imports whatever it
needs; unit tests for the submodules import them directly by design).
"""

from __future__ import annotations

import ast
from pathlib import Path

import novetest.memory as memory_public


_SRC_NOVETEST = Path(__file__).resolve().parents[3] / "src" / "novetest"

# The Memory submodules that are PRIVATE to the package. Peer engines import
# their symbols from `novetest.memory` (all legitimately consumed symbols are
# re-exported there — additions are additive, never a reason to deep-import).
_PRIVATE_MEMORY_MODULES = ("novetest.memory.store", "novetest.memory.project_store")

# The four derived engines XCT-12 inventoried (run/orchestration/cli already
# consume the public surface or none at all).
_DERIVED_ENGINE_DIRS = ("coverage", "localization", "regression", "replay")

# FULL offender set at this slice's base (`993ff59`) — 16 files, 27 import
# statements. Routing of the flips (do NOT grow this list; only shrink it):
#   - localization/*, regression/*  → flipped THIS cycle as S31/S37 riders
#     (parallel worktrees; subset semantics absorb any merge order);
#   - coverage/*                    → routed to S34;
#   - replay/*                      → routed to S39/S40.
# When every entry is gone, drop the allowlist and tighten the assertion to
# equality with the empty set.
_DEEP_IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "coverage/availability.py",
        "coverage/compare.py",
        "coverage/derive.py",
        "coverage/persistence.py",
        "coverage/retrieval.py",
        "localization/derive.py",
        "localization/failure_proximity.py",
        "localization/persistence.py",
        "localization/retrieval.py",
        "regression/compare.py",
        "regression/persistence.py",
        "regression/retrieval.py",
        "replay/context.py",
        "replay/engine.py",
        "replay/persistence.py",
        "replay/retrieval.py",
    }
)


def _imported_modules(path: Path) -> list[ast.stmt]:
    """Every Import/ImportFrom node in ``path`` (module- and function-local)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def _module_paths_of(node: ast.stmt) -> list[str]:
    """The dotted module path(s) an import statement binds against."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        # Relative imports (level > 0) never name `novetest.*`; absolute
        # imports always carry a module string in this codebase.
        return [node.module] if node.module else []
    return []


def _is_under(module_path: str, package: str) -> bool:
    return module_path == package or module_path.startswith(package + ".")


def test_derived_engine_deep_imports_are_a_subset_of_the_allowlist() -> None:
    offenders: set[str] = set()
    for engine_dir in _DERIVED_ENGINE_DIRS:
        for py_file in sorted((_SRC_NOVETEST / engine_dir).rglob("*.py")):
            for node in _imported_modules(py_file):
                if any(
                    _is_under(mod, private)
                    for mod in _module_paths_of(node)
                    for private in _PRIVATE_MEMORY_MODULES
                ):
                    offenders.add(py_file.relative_to(_SRC_NOVETEST).as_posix())
                    break
    new_offenders = offenders - _DEEP_IMPORT_ALLOWLIST
    assert not new_offenders, (
        "New deep imports of private Memory submodules (import from "
        f"`novetest.memory` instead): {sorted(new_offenders)}. The allowlist "
        "in this test only ever shrinks."
    )


def test_no_memory_module_imports_novetest_run() -> None:
    # XCT-13 layering pin: memory sits BELOW run; the supported-pair matrix
    # memory validates against lives in models (below memory). A/B: restore
    # the old `from novetest.run.engine_selector import ...` inside
    # `project_store.set_pinned_engine` and this fails naming the file.
    offenders: set[str] = set()
    for py_file in sorted((_SRC_NOVETEST / "memory").rglob("*.py")):
        for node in _imported_modules(py_file):
            if any(_is_under(mod, "novetest.run") for mod in _module_paths_of(node)):
                offenders.add(py_file.relative_to(_SRC_NOVETEST).as_posix())
    assert not offenders, (
        f"memory/ modules import novetest.run (layer inversion): {sorted(offenders)}"
    )


def test_every_deep_imported_symbol_is_exported_at_the_public_surface() -> None:
    # The XCT-12 flip precondition, kept live: whatever symbols the
    # allowlisted offenders still pull from the private submodules must
    # already be importable from `novetest.memory`, so each flip (S31/S37
    # now, S34/S39/S40 later) is a pure import-line rewrite.
    missing: set[str] = set()
    for engine_dir in _DERIVED_ENGINE_DIRS:
        for py_file in sorted((_SRC_NOVETEST / engine_dir).rglob("*.py")):
            for node in _imported_modules(py_file):
                if not isinstance(node, ast.ImportFrom) or node.module is None:
                    continue
                if node.module not in _PRIVATE_MEMORY_MODULES:
                    continue
                for alias in node.names:
                    if alias.name not in memory_public.__all__:
                        missing.add(f"{node.module}.{alias.name}")
    assert not missing, (
        f"Symbols deep-imported by derived engines but absent from "
        f"novetest.memory.__all__ (export them additively): {sorted(missing)}"
    )
