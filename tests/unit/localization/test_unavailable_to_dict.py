"""``LocalizationUnavailable.to_dict()`` — 3-key envelope projection.

Pinned by the brief for item 2: the serializer must emit exactly three
keys (``run_reference``, ``reason``, ``detail``), each always present.
``run_reference`` and ``detail`` are emitted as ``null`` (not omitted)
when their value is ``None`` so consumers can rely on key presence.
"""

from __future__ import annotations

import pytest

from novetest.localization.results import (
    KNOWN_REASONS,
    REASON_MISSING_DERIVED_FACTS,
    REASON_NO_COVERAGE,
    REASON_NO_FAILED_TESTS,
    REASON_NO_RUN_EVIDENCE,
    REASON_RUN_NOT_ANALYZABLE,
    LocalizationUnavailable,
)
from novetest.models.run_reference import RunReference


_REF = RunReference(
    run_id="01HUNAVDICT00000000000000XX", created_at=1_700_000_000_000
)
_EXPECTED_KEYS = frozenset({"run_reference", "reason", "detail"})


def test_to_dict_emits_exactly_three_top_level_keys() -> None:
    payload = LocalizationUnavailable(
        run_reference=_REF, reason=REASON_NO_FAILED_TESTS, detail="d"
    ).to_dict()
    assert set(payload) == _EXPECTED_KEYS


@pytest.mark.parametrize("reason", sorted(KNOWN_REASONS))
def test_to_dict_three_keys_for_every_known_reason(reason: str) -> None:
    """All 5 ``KNOWN_REASONS`` round-trip through ``to_dict()`` with the
    same 3-key shape; each entry of the closed enum must be serializable."""
    payload = LocalizationUnavailable(
        run_reference=_REF, reason=reason, detail="d"
    ).to_dict()
    assert set(payload) == _EXPECTED_KEYS
    assert payload["reason"] == reason


def test_to_dict_run_reference_round_trips_through_to_dict() -> None:
    """The ``run_reference`` key carries the inner shape from
    ``RunReference.to_dict()`` byte-for-byte."""
    payload = LocalizationUnavailable(
        run_reference=_REF,
        reason=REASON_RUN_NOT_ANALYZABLE,
        detail="tombstoned",
    ).to_dict()
    assert payload["run_reference"] == _REF.to_dict()
    assert payload["run_reference"] == {
        "schema_version": 1,
        "run_id": "01HUNAVDICT00000000000000XX",
        "created_at": 1_700_000_000_000,
    }


def test_to_dict_run_reference_none_emits_null_key_not_absent() -> None:
    """``run_reference=None`` is emitted as JSON ``null``, not omitted —
    consumers branch on value, not on key presence."""
    payload = LocalizationUnavailable(
        run_reference=None,
        reason=REASON_NO_RUN_EVIDENCE,
        detail="no runs in store",
    ).to_dict()
    assert "run_reference" in payload
    assert payload["run_reference"] is None


def test_to_dict_detail_none_emits_null_key_not_absent() -> None:
    """``detail=None`` is emitted as JSON ``null``, not omitted."""
    payload = LocalizationUnavailable(
        run_reference=_REF, reason=REASON_NO_COVERAGE
    ).to_dict()
    assert "detail" in payload
    assert payload["detail"] is None


def test_to_dict_detail_populated_passes_through_string() -> None:
    payload = LocalizationUnavailable(
        run_reference=_REF,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    ).to_dict()
    assert payload["detail"] == "findings not yet derived"


def test_to_dict_is_json_serializable() -> None:
    """Sanity guard: the dict must survive ``json.dumps`` — no exotic
    types may sneak into the projection."""
    import json

    payload = LocalizationUnavailable(
        run_reference=None,
        reason=REASON_NO_RUN_EVIDENCE,
        detail=None,
    ).to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded == {
        "run_reference": None,
        "reason": "no_run_evidence",
        "detail": None,
    }
