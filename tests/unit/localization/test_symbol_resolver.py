"""Symbol resolver unit tests — Python ``ast``-based mapping."""

from __future__ import annotations

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
