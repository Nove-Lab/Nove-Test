"""Unit tests for `novetest.utils.ulid`."""

from __future__ import annotations

import pytest

from novetest.utils.ulid import new_ulid, timestamp_ms_from_ulid


def test_new_ulid_is_26_chars() -> None:
    assert len(new_ulid()) == 26


def test_new_ulid_alphabet_is_crockford() -> None:
    ulid = new_ulid()
    allowed = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    assert set(ulid).issubset(allowed)


def test_timestamp_round_trip() -> None:
    ts = 1_700_000_000_000
    ulid = new_ulid(timestamp_ms=ts)
    assert timestamp_ms_from_ulid(ulid) == ts


def test_lexicographic_order_matches_timestamp_order() -> None:
    a = new_ulid(timestamp_ms=1_700_000_000_000)
    b = new_ulid(timestamp_ms=1_700_000_001_000)
    assert a < b


def test_timestamp_zero_round_trip() -> None:
    assert timestamp_ms_from_ulid(new_ulid(timestamp_ms=0)) == 0


def test_timestamp_at_48bit_max_round_trip() -> None:
    ts = (1 << 48) - 1
    assert timestamp_ms_from_ulid(new_ulid(timestamp_ms=ts)) == ts


def test_timestamp_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        new_ulid(timestamp_ms=1 << 48)
    with pytest.raises(ValueError):
        new_ulid(timestamp_ms=-1)


def test_decode_rejects_wrong_length() -> None:
    with pytest.raises(ValueError):
        timestamp_ms_from_ulid("ABC")


def test_decode_rejects_invalid_character() -> None:
    base = new_ulid(timestamp_ms=0)
    with pytest.raises(ValueError):
        timestamp_ms_from_ulid("I" + base[1:])
