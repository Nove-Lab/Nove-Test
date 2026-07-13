"""Symbol resolver unit tests — Python ``ast``-based mapping."""

from __future__ import annotations

import os
from pathlib import Path

from novetest.localization.symbol_resolver import (
    clear_resolver_cache,
    resolve_python_symbol,
)


def _write(tmp_path: Path, name: str, source: str) -> Path:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    clear_resolver_cache()
    return target


def test_resolves_top_level_function(tmp_path: Path) -> None:
    target = _write(
        tmp_path,
        "m.py",
        "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n",
    )
    name, line_range = resolve_python_symbol(target, 2)
    assert name == "foo"
    assert line_range == (1, 2)


def test_resolves_method_on_class(tmp_path: Path) -> None:
    source = (
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 1\n"
        "\n"
        "    def baz(self):\n"
        "        return 2\n"
    )
    target = _write(tmp_path, "m.py", source)
    name, line_range = resolve_python_symbol(target, 3)
    assert name == "Foo.bar"
    assert line_range == (2, 3)


def test_resolves_nested_function_to_innermost(tmp_path: Path) -> None:
    source = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n"
    )
    target = _write(tmp_path, "m.py", source)
    name, line_range = resolve_python_symbol(target, 3)
    assert name == "outer.inner"
    assert line_range == (2, 3)


def test_resolves_async_function(tmp_path: Path) -> None:
    source = "async def foo():\n    await bar()\n"
    target = _write(tmp_path, "m.py", source)
    name, line_range = resolve_python_symbol(target, 2)
    assert name == "foo"
    assert line_range == (1, 2)


def test_module_level_line_returns_none_none(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "\n"
        "def foo():\n"
        "    return os.name\n"
    )
    target = _write(tmp_path, "m.py", source)
    name, line_range = resolve_python_symbol(target, 1)
    assert name is None
    assert line_range is None


def test_syntax_error_returns_none_none(tmp_path: Path) -> None:
    target = _write(tmp_path, "broken.py", "def foo(:\n    return 1\n")
    name, line_range = resolve_python_symbol(target, 2)
    assert name is None
    assert line_range is None


def test_missing_file_returns_none_none(tmp_path: Path) -> None:
    clear_resolver_cache()
    name, line_range = resolve_python_symbol(tmp_path / "does_not_exist.py", 1)
    assert name is None
    assert line_range is None


def test_outer_function_recognized_when_inside_outer_but_outside_inner(
    tmp_path: Path,
) -> None:
    """A line in outer's body but outside the nested inner picks outer."""
    source = (
        "def outer():\n"
        "    x = 1\n"           # line 2, inside outer but not inner
        "    def inner():\n"    # line 3
        "        return 1\n"    # line 4 — inside inner
        "    return x + inner()\n"  # line 5, outer but not inner
    )
    target = _write(tmp_path, "m.py", source)
    name, line_range = resolve_python_symbol(target, 2)
    assert name == "outer"
    assert line_range is not None and line_range[0] == 1
    # And line 4 picks inner:
    name2, _ = resolve_python_symbol(target, 4)
    assert name2 == "outer.inner"


# ---------------------------------------------------------------------------
# S32 / ANA-21 — parse cache keyed on (path, st_mtime_ns).
# ---------------------------------------------------------------------------


def test_cache_misses_when_file_mtime_changes(tmp_path: Path) -> None:
    """ANA-21 A/B tripwire: modifying a file invalidates the cached
    extents WITHOUT ``clear_resolver_cache()`` — the cache key carries
    ``st_mtime_ns``, so a changed file is a cache miss."""
    target = tmp_path / "m.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")
    # Pin the mtime explicitly — a same-nanosecond rewrite must not be a
    # flake source for this test.
    os.utime(target, ns=(1_000_000_000, 1_000_000_000))
    clear_resolver_cache()
    assert resolve_python_symbol(target, 2) == ("foo", (1, 2))

    # Rewrite: ``foo`` moves down two lines; force a DIFFERENT mtime_ns.
    target.write_text("# moved\n\ndef foo():\n    return 1\n", encoding="utf-8")
    os.utime(target, ns=(2_000_000_000, 2_000_000_000))
    assert resolve_python_symbol(target, 4) == ("foo", (3, 4))


def test_cache_hit_on_same_mtime_reuses_parse(tmp_path: Path) -> None:
    """ANA-21 contract pin: an UNCHANGED ``(path, st_mtime_ns)`` key
    serves the cached parse without re-reading the file — rewriting the
    bytes but restoring the original mtime yields the stale extents.
    That is the documented key contract (mtime, not content hash)."""
    target = tmp_path / "m.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")
    os.utime(target, ns=(1_000_000_000, 1_000_000_000))
    clear_resolver_cache()
    assert resolve_python_symbol(target, 2) == ("foo", (1, 2))

    # New content (``bar``), same mtime → cached ``foo`` extents win.
    target.write_text("def bar():\n    return 1\n", encoding="utf-8")
    os.utime(target, ns=(1_000_000_000, 1_000_000_000))
    assert resolve_python_symbol(target, 2) == ("foo", (1, 2))


# ---------------------------------------------------------------------------
# S32 / ANA-22 — decorator lines belong to the decorated def's extent.
# ---------------------------------------------------------------------------


def test_decorator_line_resolves_to_decorated_function(tmp_path: Path) -> None:
    """ANA-22 A/B tripwire: a line ON the decorator resolves to the
    decorated function instead of degrading to file level."""
    source = (
        "def deco(f):\n"     # line 1
        "    return f\n"     # line 2
        "\n"
        "@deco\n"            # line 4
        "def wrapped():\n"   # line 5
        "    return 1\n"     # line 6
    )
    target = _write(tmp_path, "m.py", source)
    assert resolve_python_symbol(target, 4) == ("wrapped", (4, 6))


def test_stacked_decorators_extent_starts_at_first_decorator(
    tmp_path: Path,
) -> None:
    """The extent starts at ``decorator_list[0]`` — BOTH stacked
    decorator lines fall inside the decorated function's range."""
    source = (
        "def a(f):\n"        # line 1
        "    return f\n"     # line 2
        "\n"
        "def b(f):\n"        # line 4
        "    return f\n"     # line 5
        "\n"
        "@a\n"               # line 7
        "@b\n"               # line 8
        "def double():\n"    # line 9
        "    return 1\n"     # line 10
    )
    target = _write(tmp_path, "m.py", source)
    assert resolve_python_symbol(target, 7) == ("double", (7, 10))
    assert resolve_python_symbol(target, 8) == ("double", (7, 10))


def test_decorated_method_resolves_from_decorator_line(tmp_path: Path) -> None:
    """A decorated METHOD's decorator line maps to the dotted qualname."""
    source = (
        "class Foo:\n"           # line 1
        "    @staticmethod\n"    # line 2
        "    def bar():\n"       # line 3
        "        return 1\n"     # line 4
    )
    target = _write(tmp_path, "m.py", source)
    assert resolve_python_symbol(target, 2) == ("Foo.bar", (2, 4))
