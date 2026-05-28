"""Map ``(file, line)`` to ``(qualified_symbol, line_range)`` via Python ``ast``.

Symbol-level aggregation is the design-of-record granularity (§3): a
2000-line file contributes one entry per function, not one entry per
line. The resolver enables this by mapping each suspicious line back to
its enclosing function / method / class definition.

Phase 4 entry ships the Python resolver only. Other ecosystems
(JS/TS, Java/Kotlin, Go, Rust, C#) fall back to file-level
``CodeLocation(kind="file")`` until per-language resolvers land in
follow-up slices (strategy doc §3 + delivery-phasing.md Phase 4).

Failure modes (return ``(None, None)``):

- File does not exist.
- File is not parseable as Python (syntax error).
- Line is outside any function / async function / method definition
  (e.g. module-level top code).

In all ``(None, None)`` cases the caller falls back to
``CodeLocation(kind="file")``. We deliberately do NOT raise on parse
failure — the spectra path is too far downstream for an unparseable
non-Python file to propagate an exception cleanly. Soft-degradation to
file-level is correct behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path


# Resolver cache keyed by absolute path string. A single resolver call
# parses the file once and caches the function/class extents; subsequent
# resolver calls for the same file at different lines reuse the parse.
# Cache is process-local — invalidate by clearing the dict (see
# ``_RESOLVER_CACHE.clear()`` calls in tests).
_RESOLVER_CACHE: dict[str, list[tuple[str, int, int]]] = {}


def resolve_python_symbol(
    file_path: Path, line: int
) -> tuple[str | None, tuple[int, int] | None]:
    """Return the smallest enclosing function/method qualified symbol + line range.

    Examples:
    - Module-level ``def foo(): ...`` at lines 5-7 + ``line=6`` →
      ``("foo", (5, 7))``.
    - Method ``Foo.bar`` at lines 10-15 + ``line=12`` → ``("Foo.bar", (10, 15))``.
    - Nested function ``outer.inner`` at lines 20-25 (nested inside
      ``outer`` lines 18-30) + ``line=22`` → ``("outer.inner", (20, 25))``.
    - ``line=2`` of a module with no enclosing function → ``(None, None)``.
    - File with a ``SyntaxError`` → ``(None, None)``.
    - File that doesn't exist → ``(None, None)``.

    The "smallest enclosing" rule picks the most specific symbol. For
    nested definitions (function-in-function, method-in-class), this is
    the inner one — its ``line_range`` is contained in the outer's, so
    enclosing-by-range with min-extent is the correct selector.
    """
    extents = _extents_for(file_path)
    if extents is None:
        return None, None
    # Pick the smallest-range definition that encloses ``line``.
    enclosing: tuple[str, int, int] | None = None
    for qualname, start, end in extents:
        if start <= line <= end:
            if enclosing is None:
                enclosing = (qualname, start, end)
                continue
            existing_span = enclosing[2] - enclosing[1]
            candidate_span = end - start
            if candidate_span < existing_span:
                enclosing = (qualname, start, end)
    if enclosing is None:
        return None, None
    qualname, start, end = enclosing
    return qualname, (start, end)


def clear_resolver_cache() -> None:
    """Drop the file-level parse cache. Test-only seam."""
    _RESOLVER_CACHE.clear()


def _extents_for(file_path: Path) -> list[tuple[str, int, int]] | None:
    """Return cached ``[(qualname, start_line, end_line), ...]`` for the file.

    Returns ``None`` on parse failure (missing file / syntax error). The
    cache key is the resolved absolute path so two ``Path`` instances
    pointing at the same file share the parse.
    """
    key = str(file_path)
    cached = _RESOLVER_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        source = file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return None
    extents = _collect_extents(tree)
    _RESOLVER_CACHE[key] = extents
    return extents


def _collect_extents(tree: ast.AST) -> list[tuple[str, int, int]]:
    """Walk the AST yielding ``(qualified_name, lineno, end_lineno)`` per def.

    Names are dotted (``"Foo.bar"`` for ``Foo``'s method, ``"outer.inner"``
    for a nested function). ``ClassDef`` adds its name to the namespace
    stack but does NOT itself emit an extent — SBFL aggregates by
    function-level symbols per design-of-record §3 ("Symbol/function-level
    as the default").
    """
    extents: list[tuple[str, int, int]] = []
    _walk_namespace(tree, [], extents)
    return extents


def _walk_namespace(
    node: ast.AST,
    namespace: list[str],
    extents: list[tuple[str, int, int]],
) -> None:
    """Depth-first traversal collecting function/method extents under ``namespace``."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = ".".join(namespace + [child.name])
            end_lineno = child.end_lineno
            if end_lineno is None:
                # ast.parse with a recent Python version always populates
                # end_lineno on FunctionDef; defend against the legacy
                # case by falling back to lineno (single-line range).
                end_lineno = child.lineno
            extents.append((qualname, child.lineno, end_lineno))
            # Recurse INTO the function for nested defs (and classes).
            _walk_namespace(child, namespace + [child.name], extents)
        elif isinstance(child, ast.ClassDef):
            # Classes contribute to the namespace stack but do not emit
            # their own extent — function-level aggregation only.
            _walk_namespace(child, namespace + [child.name], extents)
        else:
            # Other nodes (Assign, If, expression statements, etc.) do
            # not nest functions in their direct children, but their
            # bodies might (e.g. a function defined inside an ``if``
            # branch). Recurse without adding to the namespace.
            _walk_namespace(child, namespace, extents)
