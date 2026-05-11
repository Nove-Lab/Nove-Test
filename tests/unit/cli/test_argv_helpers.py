from __future__ import annotations

import pytest

from novetest.cli.app import _extract_output_flag, _scan_top_level_intent


@pytest.mark.parametrize(
    "argv,expected_value,expected_cleaned",
    [
        ([], None, []),
        (["--version"], None, ["--version"]),
        (["--output", "json", "--version"], "json", ["--version"]),
        (["--version", "--output", "ndjson"], "ndjson", ["--version"]),
        (["--output=ndjson", "memory", "list"], "ndjson", ["memory", "list"]),
        (["memory", "list", "--output", "json"], "json", ["memory", "list"]),
        (["--output"], None, []),
    ],
)
def test_extract_output_flag(
    argv: list[str], expected_value: str | None, expected_cleaned: list[str]
) -> None:
    value, cleaned = _extract_output_flag(argv)
    assert value == expected_value
    assert cleaned == expected_cleaned


@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], None),
        (["--version"], "version"),
        (["-v"], "version"),
        (["--help"], "help"),
        (["-h"], "help"),
        (["memory", "list", "--help"], None),
        (["test"], None),
        (["--output", "json", "--version"], "version"),
        (["--output=ndjson", "-h"], "help"),
    ],
)
def test_scan_top_level_intent(argv: list[str], expected: str | None) -> None:
    assert _scan_top_level_intent(argv) == expected
