"""``LocalizationUnavailable`` + REASON_* constants — validation + closed enum.

The 5-element ``KNOWN_REASONS`` set is pinned by
``agent-comms/decisions/2026-05-28-localization-finding-shape.md`` §6 + §X
(the §X split that introduced ``missing-derived-facts``). The values are
kebab-case since W2/S29 (ANA-09): one reason convention across all engines,
with ``missing-derived-facts`` literally identical to the
coverage / regression / replay token.
"""

from __future__ import annotations

import re

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
    assert REASON_NO_FAILED_TESTS == "no-failed-tests"
    assert REASON_NO_COVERAGE == "no-coverage"
    assert REASON_NO_RUN_EVIDENCE == "no-run-evidence"
    assert REASON_MISSING_DERIVED_FACTS == "missing-derived-facts"
    assert REASON_RUN_NOT_ANALYZABLE == "run-not-analyzable"


def test_all_reasons_are_kebab_case() -> None:
    """W2/S29 (ANA-09) guard: every reason is kebab-case — lowercase words
    joined by single hyphens, no underscores. Localization was the last
    engine on snake_case; this pins the converged convention."""
    kebab = re.compile(r"^[a-z]+(-[a-z]+)*$")
    for reason in KNOWN_REASONS:
        assert kebab.fullmatch(reason), f"non-kebab-case reason: {reason!r}"
        assert "_" not in reason


def test_missing_derived_facts_matches_sibling_engines_spelling() -> None:
    """The convergence point of ANA-09: localization's
    ``missing-derived-facts`` is the LITERAL same token coverage,
    regression, and replay emit for the same concept, so a single matcher
    works across every engine's unavailable outcome in one ``inspect``
    payload. Read-only imports — this test must never mutate those
    modules."""
    from novetest.coverage.results import (
        REASON_MISSING_DERIVED_FACTS as COVERAGE_MISSING_DERIVED_FACTS,
    )
    from novetest.regression.results import (
        REASON_MISSING_DERIVED_FACTS as REGRESSION_MISSING_DERIVED_FACTS,
    )
    from novetest.replay.errors import (
        REASON_MISSING_DERIVED_FACTS as REPLAY_MISSING_DERIVED_FACTS,
    )

    assert REASON_MISSING_DERIVED_FACTS == COVERAGE_MISSING_DERIVED_FACTS
    assert REASON_MISSING_DERIVED_FACTS == REGRESSION_MISSING_DERIVED_FACTS
    assert REASON_MISSING_DERIVED_FACTS == REPLAY_MISSING_DERIVED_FACTS


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


def test_unavailable_snake_case_missing_derived_facts_is_rejected() -> None:
    """The pre-S29 underscore spelling ``missing_derived_facts`` is no
    longer a member of the closed enum — a silent revert of the ANA-09
    kebab-case rename (or a stale producer) must fail loudly here."""
    with pytest.raises(ValueError, match="reason"):
        LocalizationUnavailable(
            run_reference=_REF, reason="missing_derived_facts"
        )
