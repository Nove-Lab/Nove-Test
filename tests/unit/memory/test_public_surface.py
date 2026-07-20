"""Architecture guards for the Memory package boundary (XCT-12 / XCT-13, S43).

Two ratchets over the production source tree (AST-based, so docstrings and
comments mentioning module paths cannot false-positive):

1. **Public-surface ratchet (XCT-12).** Consumers outside ``memory/`` must
   import from ``novetest.memory`` only; the submodule paths
   (``novetest.memory.store`` / ``novetest.memory.project_store``) are
   private. The four derived engines (coverage/localization/regression/
   replay) once carried an allowlisted set of deep imports; every flip has
   shipped (S31/S37/S34/S40), so the guard is now **equality** — the
   offender set MUST be empty. Note this ratchet scopes only the four
   derived engines; the deliberate ``orchestration``/``cli`` deep imports of
   ``memory.project_store`` are a separate surface out of scope here (they
   pull symbols the audit below proves are re-exported).

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
# consume the public surface or deep-import a separate, out-of-scope surface).
_DERIVED_ENGINE_DIRS = ("coverage", "localization", "regression", "replay")


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


def test_derived_engines_have_no_deep_memory_imports() -> None:
    # Guard is now EQUALITY (S45): every allowlisted flip has shipped, so the
    # offender set must be EMPTY — a derived engine must import Memory symbols
    # from `novetest.memory`, never from its private submodules.
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
    assert not offenders, (
        "Deep imports of private Memory submodules in derived engines "
        f"(import from `novetest.memory` instead): {sorted(offenders)}."
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


def test_s18_run_id_lookup_symbols_are_on_the_public_surface() -> None:
    # S18: `find_entry_by_run_id` + `RUN_ID_NOT_FOUND_MESSAGE` are the run_id
    # lookup contract the orchestration lane consumes from `novetest.memory`
    # (it deletes four duplicated linear scans in favor of them). This guard
    # keeps that contract load-bearing — the exports cannot silently vanish
    # from the package surface, and the not-found template stays `{run_id}`-
    # formattable so the wire wording is stable.
    for symbol in ("find_entry_by_run_id", "RUN_ID_NOT_FOUND_MESSAGE"):
        assert symbol in memory_public.__all__, symbol
        assert hasattr(memory_public, symbol), symbol
    rendered = memory_public.RUN_ID_NOT_FOUND_MESSAGE.format(run_id="01ABC")
    assert rendered == "No Memory Entry for run_id='01ABC'"


def test_every_deep_imported_symbol_is_exported_at_the_public_surface() -> None:
    # Standing re-export guard (belt-and-suspenders beside the equality pin):
    # should a derived engine ever deep-import a symbol from a private Memory
    # submodule, that symbol must already be re-exported from `novetest.memory`
    # so the fix is a pure import-line rewrite, never an `__all__` addition.
    # Vacuously green while the equality guard above holds (zero offenders).
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
