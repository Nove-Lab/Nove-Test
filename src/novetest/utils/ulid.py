"""ULID generation and timestamp extraction.

Used as the Run Reference ``run_id``. The 48-bit timestamp prefix lets us
derive ``created_at`` (and the date-bucketed Project Store path
``memory/runs/YYYY/MM/DD/run_<ulid>/``) without an index database. See
`design/implementation-plan/foundations.md` §4.
"""

from __future__ import annotations

import secrets
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE_MAP = {c: i for i, c in enumerate(_ALPHABET)}


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """Return a Crockford-base32 ULID.

    When ``timestamp_ms`` is omitted the current wall-clock millisecond is
    used. Pass an explicit value in tests to keep generation deterministic.
    """

    ts = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    if ts < 0 or ts >= (1 << 48):
        raise ValueError(f"timestamp_ms out of 48-bit range: {ts}")
    rand_int = int.from_bytes(secrets.token_bytes(10), "big")
    # 128 bits total, padded up to 130 bits so we can encode 26 5-bit chars
    # without leftover bits. The two leading bits are zero by construction.
    full = ((ts << 80) | rand_int) << 2
    chars = [_ALPHABET[(full >> ((25 - i) * 5)) & 0x1F] for i in range(26)]
    return "".join(chars)


def timestamp_ms_from_ulid(ulid: str) -> int:
    """Extract the 48-bit millisecond timestamp from a ULID string."""

    if len(ulid) != 26:
        raise ValueError(f"ULID must be 26 characters, got {len(ulid)}")
    val = 0
    for c in ulid.upper():
        digit = _DECODE_MAP.get(c)
        if digit is None:
            raise ValueError(f"Invalid ULID character: {c!r}")
        val = (val << 5) | digit
    # val is 130 bits: 2 leading zero pad bits, 48 timestamp bits, 80 random bits.
    return (val >> 82) & ((1 << 48) - 1)
