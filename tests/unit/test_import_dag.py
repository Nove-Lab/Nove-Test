"""Import-DAG structural guard for the derived-engine boundaries (XCT-06 / W3-S48).

AST-walks the production source tree (``src/novetest/**/*.py``) and asserts
that no module OUTSIDE ``novetest.coverage`` imports a
``novetest.coverage.<submodule>`` path, and no module OUTSIDE
``novetest.regression`` imports a ``novetest.regression.<submodule>`` path.
Cross-engine consumers (regression -> coverage, localization ->
coverage+regression, orchestration -> coverage) must bind the package-public
``__init__`` symbol; the submodule layout is private.

Own-package modules (including the package's own ``__init__`` and any nested
subpackage) are exempt — a coverage submodule may import a sibling coverage
submodule. ``tests/`` is not scanned (test modules import submodules directly
by design). Pure ``ast`` + ``pathlib``; no runtime imports; deterministic.

Scope pin (W3-S48): this guards ONLY the two derived-engine boundaries XCT-06
named. ``memory.project_store`` reach-ins from cli/orchestration are governed
by Memory's own public-surface ratchet
(``tests/unit/memory/test_public_surface.py``) and are deliberately OUT of
scope here. A broader every-engine guard is a possible PM follow-up.
"""

from __future__ import annotations

import ast
from pathlib import Path


_SRC_NOVETEST = Path(__file__).resolve().parents[2] / "src" / "novetest"

# The derived-engine package boundaries XCT-06 guards. A consumer outside the
# package must import the public symbol from ``novetest.<engine>``; reaching
# into ``novetest.<engine>.<submodule>`` is the offense.
_GUARDED_ENGINES = ("coverage", "regression")


def _import_module_paths(node: ast.stmt) -> list[str]:
    """The dotted module path(s) an import statement binds against."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        # Relative imports (level > 0) never name `novetest.*`; absolute
        # imports always carry a module string in this codebase.
        return [node.module] if node.module else []
    return []


def _guarded_submodule_engine(module_path: str) -> str | None:
    """The guarded engine whose *submodule* ``module_path`` names, else ``None``.

    The bare package path ``novetest.<engine>`` is the public surface and is
    always allowed, so it returns ``None`` — only ``novetest.<engine>.<x>``
    matches. The trailing dot makes the boundary exact (``novetest.coverage``
    matches, ``novetest.coverage_helpers`` does not).
    """
    for engine in _GUARDED_ENGINES:
        if module_path.startswith(f"novetest.{engine}."):
            return engine
    return None


def _offenses_in_source(rel: str, source: str) -> list[str]:
    """Offending cross-engine submodule imports in one module's ``source``.

    ``rel`` is the module's posix path relative to ``src/novetest``. Pure over
    text so the guard's discrimination is unit-tested against synthetic
    snippets below, not only the live tree.
    """
    offenses: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for module_path in _import_module_paths(node):
            engine = _guarded_submodule_engine(module_path)
            if engine is None:
                continue
            # Own-package modules (the `<engine>/` subtree, incl. its own
            # `__init__` and any nested subpackage) may reach into siblings.
            if rel.startswith(f"{engine}/"):
                continue
            offenses.append(f"{rel}:{node.lineno}: imports {module_path!r}")
    return offenses


def _tree_offenses() -> list[str]:
    offenses: list[str] = []
    for py_file in sorted(_SRC_NOVETEST.rglob("*.py")):
        rel = py_file.relative_to(_SRC_NOVETEST).as_posix()
        offenses.extend(_offenses_in_source(rel, py_file.read_text(encoding="utf-8")))
    return offenses


def test_no_cross_engine_submodule_imports() -> None:
    offenses = _tree_offenses()
    assert not offenses, (
        "Cross-engine internal-submodule imports found (XCT-06 / W3-S48):\n"
        + "\n".join(offenses)
        + "\n\nBind the package-public symbol from `novetest.<engine>`; if a "
        "needed symbol is not public, extend that package's `__all__` "
        "(owning team) rather than reaching into submodules."
    )


def test_scanner_walked_a_nonempty_tree() -> None:
    # Insurance against a path bug turning the ratchet vacuous: the two guarded
    # package `__init__`s must be present in the scan set.
    scanned = {
        p.relative_to(_SRC_NOVETEST).as_posix()
        for p in _SRC_NOVETEST.rglob("*.py")
    }
    assert "coverage/__init__.py" in scanned
    assert "regression/__init__.py" in scanned


def test_guard_flags_a_cross_engine_submodule_import() -> None:
    # A non-engine consumer reaching into a coverage submodule is flagged with
    # its file:line and the offending module path.
    offenses = _offenses_in_source(
        "regression/foo.py",  # regression reaching into a coverage submodule
        "from novetest.coverage.compare import CoverageDelta\n",
    )
    assert offenses == ["regression/foo.py:1: imports 'novetest.coverage.compare'"]

    # `import novetest.regression.results` from orchestration is caught too.
    offenses = _offenses_in_source(
        "orchestration/x.py",
        "import os\nimport novetest.regression.results\n",
    )
    assert offenses == ["orchestration/x.py:2: imports 'novetest.regression.results'"]


def test_guard_allows_public_surface_and_own_package_imports() -> None:
    # Binding the package-public symbol is allowed from anywhere.
    assert _offenses_in_source(
        "regression/compare.py",
        "from novetest.coverage import CoverageDelta, compare_coverage_facts\n",
    ) == []
    # An own-package submodule import (coverage -> coverage) is exempt.
    assert _offenses_in_source(
        "coverage/retrieval.py",
        "from novetest.coverage.compare import SCHEMA_VERSION\n",
    ) == []
    # A look-alike package name is not a false positive.
    assert _offenses_in_source(
        "orchestration/y.py",
        "from novetest.coverage_helpers.x import thing\n",
    ) == []
