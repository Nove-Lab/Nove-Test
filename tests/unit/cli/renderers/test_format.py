"""Unit tests for the domain-agnostic formatting primitives (``_format.py``)."""

from __future__ import annotations

from novetest.cli.renderers._format import (
    GLYPH_FAIL,
    GLYPH_OK,
    GLYPH_UNAVAILABLE,
    availability_glyph,
    format_table,
    format_timestamp,
    indent_block,
    percent,
    run_status_glyph,
    target_label,
)


def test_run_status_glyph_is_case_insensitive() -> None:
    assert run_status_glyph("passed") == GLYPH_OK
    assert run_status_glyph("PASSED") == GLYPH_OK
    assert run_status_glyph("failed") == GLYPH_FAIL
    assert run_status_glyph("errored") == GLYPH_FAIL
    assert run_status_glyph("skipped") == GLYPH_UNAVAILABLE


def test_availability_glyph() -> None:
    assert availability_glyph("available") == GLYPH_OK
    assert availability_glyph("unavailable") == GLYPH_UNAVAILABLE


def test_format_timestamp_epoch_ms_to_iso_utc() -> None:
    assert format_timestamp(1700000000000) == "2023-11-14T22:13:20Z"


def test_format_timestamp_non_int_passthrough() -> None:
    assert format_timestamp("n/a") == "n/a"
    assert format_timestamp(None) == "None"


def test_percent_one_decimal() -> None:
    assert percent(86.66666666) == "86.7%"
    assert percent(100) == "100.0%"
    assert percent("?") == "?"


def test_target_label_blank_is_workspace() -> None:
    assert target_label("") == "<workspace>"
    assert target_label("tests/test_x.py") == "tests/test_x.py"


def test_format_table_left_aligned_columns() -> None:
    table = format_table(["a", "bb"], [["1", "2"], ["333", "4"]])
    assert table == "a    bb\n1    2\n333  4"


def test_format_table_header_only() -> None:
    assert format_table(["run_id", "status"], []) == "run_id  status"


def test_indent_block_prefixes_every_line() -> None:
    assert indent_block("x\ny", "  ") == "  x\n  y"
