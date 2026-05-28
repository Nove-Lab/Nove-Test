"""``LocalizationUnavailable`` + REASON_* constants — validation + closed enum.

The 5-element ``KNOWN_REASONS`` set is pinned by
``agent-comms/decisions/2026-05-28-localization-finding-shape.md`` §6 + §X
(the §X split that introduced ``missing_derived_facts`` lands in this
slice).
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


_REF = RunReference(run_id="01HRESULTS00000000000000XX", created_at=1_700_000_000_000)


def test_known_reasons_closed_enum_contents() -> None:
    """The closed enum must match the documented 5-element set exactly."""
    assert KNOWN_REASONS == frozenset(
        {
            REASON_NO_FAILED_TESTS,
            REASON_NO_COVERAGE,
            REASON_NO_RUN_EVIDENCE,
            REASON_MISSING_DERIVED_FACTS,
            REASON_RUN_NOT_ANALYZABLE,
        }
    )


def test_known_reasons_has_exactly_five_elements() -> None:
    """Sanity guard against accidental duplicate constant values."""
    assert len(KNOWN_REASONS) == 5


def test_reason_constants_have_pinned_string_values() -> None:
    """All five constants pin specific string values consumers may match on."""
    assert REASON_NO_FAILED_TESTS == "no_failed_tests"
    assert REASON_NO_COVERAGE == "no_coverage"
    assert REASON_NO_RUN_EVIDENCE == "no_run_evidence"
    assert REASON_MISSING_DERIVED_FACTS == "missing_derived_facts"
    assert REASON_RUN_NOT_ANALYZABLE == "run_not_analyzable"


def test_unavailable_constructable_with_run_reference() -> None:
    unavailable = LocalizationUnavailable(
        run_reference=_REF, reason=REASON_NO_FAILED_TESTS
    )
    assert unavailable.run_reference is _REF
    assert unavailable.reason == REASON_NO_FAILED_TESTS
    assert unavailable.detail is None


def test_unavailable_constructable_with_none_run_reference() -> None:
    """``run_reference`` can be None for the resolve-failure path."""
    unavailable = LocalizationUnavailable(
        run_reference=None, reason=REASON_NO_RUN_EVIDENCE, detail="not in store"
    )
    assert unavailable.run_reference is None
    assert unavailable.detail == "not in store"


def test_unavailable_constructable_with_missing_derived_facts() -> None:
    """``REASON_MISSING_DERIVED_FACTS`` is in the closed set and constructs."""
    unavailable = LocalizationUnavailable(
        run_reference=_REF,
        reason=REASON_MISSING_DERIVED_FACTS,
        detail="findings not yet derived",
    )
    assert unavailable.reason == REASON_MISSING_DERIVED_FACTS


def test_unavailable_invalid_reason_raises() -> None:
    with pytest.raises(ValueError, match="reason"):
        LocalizationUnavailable(run_reference=_REF, reason="bogus")


def test_unavailable_hyphenated_missing_derived_facts_is_rejected() -> None:
    """Regression uses the hyphenated form ``missing-derived-facts``;
    Localization uses underscore form to match its existing convention.
    A hyphenated reason here must be rejected by the closed-enum guard."""
    with pytest.raises(ValueError, match="reason"):
        LocalizationUnavailable(
            run_reference=_REF, reason="missing-derived-facts"
        )
