"""``LocalizationFinding`` and friends — model round-trip + validators."""

from __future__ import annotations

import pytest

from novetest.models.localization_finding import (
    CODE_LOCATION_KINDS,
    EVIDENCE_KINDS,
    FORMULAS,
    LOCALIZATION_CONFIDENCES,
    LOCALIZATION_MODES,
    SCHEMA_VERSION,
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.run_reference import RunReference


_REF = RunReference(run_id="01HMODEL0000000000000000XX", created_at=1_700_000_000_000)


def _location() -> CodeLocation:
    return CodeLocation(
        kind="symbol",
        file="src/foo.py",
        symbol="Foo.bar",
        line_range=(10, 20),
        primary_line=15,
        evidence_lines=(15, 12, 18),
    )


def _entry(rank: int = 1) -> LocalizationEntry:
    return LocalizationEntry(
        rank=rank,
        tied_with=(),
        code_location=_location(),
        score_raw=0.71,
        score_normalized=0.92,
        formula="ochiai",
        alternate_scores={"op2": 4.3, "dstar2": 12.5, "tarantula": 0.61},
        related_failed_tests=("tests/test_bar.py::test_compute",),
        evidence_citations=(
            EvidenceCitation(
                kind="test_result",
                run_reference=_REF,
                selector={"test_id": "tests/test_bar.py::test_compute", "outcome": "failed"},
            ),
            EvidenceCitation(
                kind="coverage_fact",
                run_reference=_REF,
                selector={"file": "src/foo.py", "lines": [15, 12, 18]},
            ),
        ),
    )


def _finding() -> LocalizationFinding:
    return LocalizationFinding(
        run_reference=_REF,
        engine_name="pytest",
        ecosystem="python",
        mode="sbfl_per_test",
        confidence="high",
        formula="ochiai",
        alternate_scores_available=("dstar2", "op2", "tarantula"),
        top_n=10,
        entries=(_entry(),),
        derived_at=_REF.created_at + 500,
    )


def test_round_trip_finding() -> None:
    finding = _finding()
    payload = finding.to_dict()
    restored = LocalizationFinding.from_dict(payload)
    assert restored == finding


def test_round_trip_entry() -> None:
    entry = _entry()
    payload = entry.to_dict()
    restored = LocalizationEntry.from_dict(payload)
    assert restored == entry


def test_round_trip_code_location() -> None:
    loc = _location()
    payload = loc.to_dict()
    restored = CodeLocation.from_dict(payload)
    assert restored == loc


def test_code_location_file_kind_with_none_symbol() -> None:
    loc = CodeLocation(
        kind="file",
        file="src/foo.py",
        symbol=None,
        line_range=None,
        primary_line=1,
        evidence_lines=(1, 5, 9),
    )
    restored = CodeLocation.from_dict(loc.to_dict())
    assert restored == loc


def test_evidence_citation_round_trip() -> None:
    citation = EvidenceCitation(
        kind="coverage_fact",
        run_reference=_REF,
        selector={"file": "src/foo.py", "lines": [10, 20]},
    )
    restored = EvidenceCitation.from_dict(citation.to_dict())
    assert restored == citation


def test_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="mode"):
        LocalizationFinding(
            run_reference=_REF,
            engine_name="pytest",
            ecosystem="python",
            mode="not_a_mode",
            confidence="high",
            formula="ochiai",
            alternate_scores_available=(),
            top_n=10,
            entries=(),
            derived_at=0,
        )


def test_invalid_confidence_raises() -> None:
    with pytest.raises(ValueError, match="confidence"):
        LocalizationFinding(
            run_reference=_REF,
            engine_name="pytest",
            ecosystem="python",
            mode="sbfl_per_test",
            confidence="excellent",
            formula="ochiai",
            alternate_scores_available=(),
            top_n=10,
            entries=(),
            derived_at=0,
        )


def test_invalid_formula_raises() -> None:
    with pytest.raises(ValueError, match="formula"):
        LocalizationFinding(
            run_reference=_REF,
            engine_name="pytest",
            ecosystem="python",
            mode="sbfl_per_test",
            confidence="high",
            formula="not_a_formula",
            alternate_scores_available=(),
            top_n=10,
            entries=(),
            derived_at=0,
        )


def test_invalid_alternate_formula_in_finding_raises() -> None:
    with pytest.raises(ValueError, match="alternate_scores_available"):
        LocalizationFinding(
            run_reference=_REF,
            engine_name="pytest",
            ecosystem="python",
            mode="sbfl_per_test",
            confidence="high",
            formula="ochiai",
            alternate_scores_available=("bogus",),
            top_n=10,
            entries=(),
            derived_at=0,
        )


def test_invalid_alternate_formula_in_entry_raises() -> None:
    with pytest.raises(ValueError, match="alternate_scores"):
        LocalizationEntry(
            rank=1,
            tied_with=(),
            code_location=_location(),
            score_raw=0.0,
            score_normalized=0.0,
            formula="ochiai",
            alternate_scores={"made_up": 1.0},
            related_failed_tests=(),
            evidence_citations=(),
        )


def test_invalid_code_location_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        CodeLocation(
            kind="not_a_kind",
            file="src/x.py",
            symbol=None,
            line_range=None,
            primary_line=1,
            evidence_lines=(),
        )


def test_invalid_evidence_kind_raises() -> None:
    with pytest.raises(ValueError, match="kind"):
        EvidenceCitation(
            kind="regression_fact",  # reserved but not in v1 EVIDENCE_KINDS
            run_reference=_REF,
            selector={},
        )


def test_invalid_line_range_raises() -> None:
    with pytest.raises(ValueError, match="line_range"):
        CodeLocation(
            kind="symbol",
            file="src/x.py",
            symbol="f",
            line_range=(10, 5),
            primary_line=8,
            evidence_lines=(),
        )


def test_rank_must_be_positive() -> None:
    with pytest.raises(ValueError, match="rank"):
        LocalizationEntry(
            rank=0,
            tied_with=(),
            code_location=_location(),
            score_raw=0.0,
            score_normalized=0.0,
            formula="ochiai",
            alternate_scores={},
            related_failed_tests=(),
            evidence_citations=(),
        )


def test_schema_version_mismatch_raises() -> None:
    payload = _finding().to_dict()
    payload["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="schema_version"):
        LocalizationFinding.from_dict(payload)


def test_closed_enum_membership() -> None:
    """Sanity checks the closed enums match the documented contract."""
    assert FORMULAS == frozenset({"ochiai", "op2", "dstar2", "tarantula"})
    assert LOCALIZATION_MODES == frozenset(
        {"sbfl_per_test", "sbfl_aggregate", "failure_proximity"}
    )
    assert LOCALIZATION_CONFIDENCES == frozenset({"high", "medium", "low"})
    assert CODE_LOCATION_KINDS == frozenset({"symbol", "line", "branch", "file"})
    assert EVIDENCE_KINDS == frozenset({"test_result", "coverage_fact"})
