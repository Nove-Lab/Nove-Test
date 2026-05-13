"""ULID helpers (Crockford-base32, 48-bit ms timestamp + 80-bit randomness).

Why this lives here: the foundations doc (§4) pins the on-disk Run Record
path to ``runs/YYYY/MM/DD/run_<ulid>/``, with the first 10 characters of the
ULID encoding ``created_at`` so the date path is computable from the run id
alone. This module is the canonical encoder/decoder.

Implementation is stdlib only — pulling in the ``python-ulid`` package would
add a dependency for ~40 lines of base32 arithmetic that we control entirely.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone


_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}

_TIMESTAMP_CHARS = 10
_RANDOM_CHARS = 16
ULID_LENGTH = _TIMESTAMP_CHARS + _RANDOM_CHARS


def _encode(value: int, length: int) -> str:
    if value < 0:
        raise ValueError(f"ulid: cannot encode negative value {value}")
    chars: list[str] = []
    for _ in range(length):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    if value != 0:
        raise ValueError(f"ulid: value too large to fit in {length} base32 chars")
    return "".join(reversed(chars))


def _decode(text: str) -> int:
    value = 0
    for ch in text.upper():
        slot = _DECODE.get(ch)
        if slot is None:
            raise ValueError(f"ulid: invalid Crockford base32 char {ch!r} in {text!r}")
        value = (value << 5) | slot
    return value


def generate_ulid(timestamp_ms: int | None = None) -> str:
    """Return a fresh 26-char ULID. ``timestamp_ms`` overrides the clock (tests)."""
    ts_ms = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    rnd = int.from_bytes(secrets.token_bytes(10), "big")
    return _encode(ts_ms, _TIMESTAMP_CHARS) + _encode(rnd, _RANDOM_CHARS)


def extract_timestamp_ms(ulid: str) -> int:
    """Decode the 48-bit timestamp prefix of a ULID."""
    if len(ulid) != ULID_LENGTH:
        raise ValueError(
            f"ulid: expected length {ULID_LENGTH}, got {len(ulid)} for {ulid!r}"
        )
    return _decode(ulid[:_TIMESTAMP_CHARS])


def date_path_for_timestamp_ms(timestamp_ms: int) -> tuple[str, str, str]:
    """Return ``(YYYY, MM, DD)`` in UTC for the run record directory path."""
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}"
