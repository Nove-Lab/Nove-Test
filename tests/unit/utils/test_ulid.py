"""Unit tests for `novetest.utils.ulid`."""

from __future__ import annotations

import pytest

from novetest.utils.ulid import (
    ULID_LENGTH,
    date_path_for_timestamp_ms,
    extract_timestamp_ms,
    generate_ulid,
)


def test_generate_has_canonical_length() -> None:
    ulid = generate_ulid()
    assert len(ulid) == ULID_LENGTH == 26


def test_generate_uses_crockford_alphabet() -> None:
    ulid = generate_ulid()
    legal = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert set(ulid) <= legal


def test_timestamp_round_trip() -> None:
    ts = 1_700_000_000_000
    ulid = generate_ulid(timestamp_ms=ts)
    assert extract_timestamp_ms(ulid) == ts


def test_timestamp_zero_round_trip() -> None:
    assert extract_timestamp_ms(generate_ulid(timestamp_ms=0)) == 0


def test_timestamp_at_48bit_max_round_trip() -> None:
    ts = (1 << 48) - 1
    assert extract_timestamp_ms(generate_ulid(timestamp_ms=ts)) == ts


def test_timestamp_is_monotonic_when_clock_is() -> None:
    earlier = generate_ulid(timestamp_ms=1_700_000_000_000)
    later = generate_ulid(timestamp_ms=1_700_000_000_500)
    assert earlier[:10] < later[:10]


def test_generate_rejects_negative_timestamp() -> None:
    with pytest.raises(ValueError, match="negative"):
        generate_ulid(timestamp_ms=-1)


def test_extract_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="expected length"):
        extract_timestamp_ms("01HXYZ")


def test_extract_rejects_unknown_char() -> None:
    bad = "I" + "0" * (ULID_LENGTH - 1)
    with pytest.raises(ValueError, match="invalid Crockford"):
        extract_timestamp_ms(bad)


def test_date_path_is_utc() -> None:
    # 2026-05-13T10:30:00Z (computed via datetime, not hand-rolled)
    ts_ms = 1_778_668_200_000
    year, month, day = date_path_for_timestamp_ms(ts_ms)
    assert (year, month, day) == ("2026", "05", "13")


def test_date_path_zero_pads() -> None:
    # 2024-01-02T00:00:00Z
    ts_ms = 1_704_153_600_000
    assert date_path_for_timestamp_ms(ts_ms) == ("2024", "01", "02")
