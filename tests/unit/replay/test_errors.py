"""``ReplayUnavailable`` + ``KNOWN_REASONS`` unit tests.

Validates the discriminator type used by all Replay engine boundaries:
correct construction, reason validation, ``to_dict`` shape contract, and the
closed ``KNOWN_REASONS`` vocabulary.
"""

from __future__ import annotations

import pytest

from novetest.models.run_reference import RunReference
from novetest.replay.errors import (
    KNOWN_REASONS,
    REASON_CONTEXT_RECONSTRUCTION_FAILED,
    REASON_ENGINE_NOT_READY,
    REASON_MISSING_DERIVED_FACTS,
    REASON_ORIGINAL_NOT_FOUND,
    REASON_TARGET_MISSING,
    REASON_TOMBSTONED_ORIGINAL,
    ReplayUnavailable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ref(run_id: str = "01HERR0000000000000000AA") -> RunReference:
    return RunReference(run_id=run_id, created_at=1_700_000_000_000)


# ---------------------------------------------------------------------------
# KNOWN_REASONS vocabulary
# ---------------------------------------------------------------------------


def test_known_reasons_contains_exactly_six_strings() -> None:
    """``KNOWN_REASONS`` must contain the six reasons documented in ``errors.py``."""
    expected = {
        "original-not-found",
        "tombstoned-original",
        "context-reconstruction-failed",
        "engine-not-ready",
        "target-missing",
        "missing-derived-facts",
    }
    assert KNOWN_REASONS == expected


def test_reason_constants_match_known_reasons_set() -> None:
    """Each ``REASON_*`` module constant must appear in ``KNOWN_REASONS``."""
    constants = {
        REASON_ORIGINAL_NOT_FOUND,
        REASON_TOMBSTONED_ORIGINAL,
        REASON_CONTEXT_RECONSTRUCTION_FAILED,
        REASON_ENGINE_NOT_READY,
        REASON_TARGET_MISSING,
        REASON_MISSING_DERIVED_FACTS,
    }
    assert constants == KNOWN_REASONS


# ---------------------------------------------------------------------------
# Valid construction — all six reasons
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "original-not-found",
        "tombstoned-original",
        "context-reconstruction-failed",
        "engine-not-ready",
        "target-missing",
        "missing-derived-facts",
    ],
)
def test_valid_reason_accepted(reason: str) -> None:
    """Every string in ``KNOWN_REASONS`` must be accepted without error."""
    unavailable = ReplayUnavailable(run_reference=_ref(), reason=reason)
    assert unavailable.reason == reason


def test_none_run_reference_accepted() -> None:
    """``run_reference`` may be ``None`` when the reference itself cannot be resolved."""
    unavailable = ReplayUnavailable(run_reference=None, reason="original-not-found")
    assert unavailable.run_reference is None


def test_detail_defaults_to_none() -> None:
    """``detail`` defaults to ``None`` when not supplied."""
    unavailable = ReplayUnavailable(run_reference=None, reason="missing-derived-facts")
    assert unavailable.detail is None


def test_detail_accepted_when_supplied() -> None:
    """Non-None ``detail`` is stored verbatim."""
    unavailable = ReplayUnavailable(
        run_reference=_ref(),
        reason="engine-not-ready",
        detail="pytest binary not found",
    )
    assert unavailable.detail == "pytest binary not found"


# ---------------------------------------------------------------------------
# Invalid reason raises ValueError
# ---------------------------------------------------------------------------


def test_invalid_reason_raises_value_error() -> None:
    """An unknown reason string must raise ``ValueError`` from ``__post_init__``."""
    with pytest.raises(ValueError, match="Invalid ReplayUnavailable.reason"):
        ReplayUnavailable(run_reference=None, reason="not-a-real-reason")


def test_empty_string_reason_raises_value_error() -> None:
    """An empty string is not a valid reason."""
    with pytest.raises(ValueError):
        ReplayUnavailable(run_reference=None, reason="")


# ---------------------------------------------------------------------------
# to_dict shape contract: always 3 keys, nulls emitted (not omitted)
# ---------------------------------------------------------------------------


def test_to_dict_always_has_three_keys() -> None:
    """``to_dict()`` must always emit exactly 3 keys regardless of None fields."""
    unavailable = ReplayUnavailable(run_reference=None, reason="missing-derived-facts")
    d = unavailable.to_dict()
    assert set(d.keys()) == {"run_reference", "reason", "detail"}


def test_to_dict_run_reference_null_when_none() -> None:
    """``run_reference`` is emitted as ``None`` (not omitted) when not set."""
    unavailable = ReplayUnavailable(run_reference=None, reason="original-not-found")
    d = unavailable.to_dict()
    assert "run_reference" in d
    assert d["run_reference"] is None


def test_to_dict_detail_null_when_none() -> None:
    """``detail`` is emitted as ``None`` (not omitted) when not set."""
    unavailable = ReplayUnavailable(run_reference=_ref(), reason="target-missing")
    d = unavailable.to_dict()
    assert "detail" in d
    assert d["detail"] is None


def test_to_dict_run_reference_serialized_when_present() -> None:
    """``run_reference`` is serialized via ``RunReference.to_dict()`` when set."""
    ref = _ref("01HERR0000000000000000BB")
    unavailable = ReplayUnavailable(run_reference=ref, reason="tombstoned-original")
    d = unavailable.to_dict()
    run_ref_dict = d["run_reference"]
    assert isinstance(run_ref_dict, dict)
    assert run_ref_dict["run_id"] == "01HERR0000000000000000BB"


def test_to_dict_reason_and_detail_preserved() -> None:
    """``reason`` and ``detail`` round-trip through ``to_dict``."""
    unavailable = ReplayUnavailable(
        run_reference=None,
        reason="context-reconstruction-failed",
        detail="workspace no longer exists",
    )
    d = unavailable.to_dict()
    assert d["reason"] == "context-reconstruction-failed"
    assert d["detail"] == "workspace no longer exists"


# ---------------------------------------------------------------------------
# Frozen dataclass — immutability
# ---------------------------------------------------------------------------


def test_replay_unavailable_is_frozen() -> None:
    """``ReplayUnavailable`` is a frozen dataclass; attribute assignment raises."""
    unavailable = ReplayUnavailable(run_reference=None, reason="missing-derived-facts")
    with pytest.raises((AttributeError, TypeError)):
        unavailable.reason = "engine-not-ready"  # type: ignore[misc]
