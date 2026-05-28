"""Localization Finding domain model.

Persisted ranked Code Locations derived from a single Run's Coverage Facts
plus failed Test Results — the SBFL output the Localization engine writes
under ``<store>/localization/findings/run_<id>/localization_findings.json``.

Source of truth for the wire format:
- ``design/implementation-plan/localization-strategy.md`` §1–§6
- ``design/interace-contract/localization.md``
- ``.claude/agents/novetest-localization-team.md``

This file owns four frozen dataclasses that together form the on-disk
``localization_findings.json`` payload:

- ``CodeLocation``        — what was implicated (symbol or file-level).
- ``EvidenceCitation``    — the per-entry pointers back to the run evidence.
- ``LocalizationEntry``   — one ranked finding (score + rank + tie info).
- ``LocalizationFinding`` — the top-level entity.

The wire schema is a Phase-4-entry **working draft** — PM freezes the shape
in a follow-up ``decisions/`` entry after Manual Test fields it (same
ship → field-test → freeze cadence the Coverage and Regression engines
followed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Self

from novetest.models.run_reference import RunReference


SCHEMA_VERSION: int = 1


# ---------------------------------------------------------------------------
# Closed enums — validated in ``__post_init__``. Adding a value is a breaking
# change (consumers pattern-match on the closed set); requires a follow-up
# decision update + ``schema_version`` bump.
# ---------------------------------------------------------------------------

# Mode enum — design-of-record §2 ("Three explicit modes"). Only
# ``sbfl_per_test`` is produced by the Phase-4-entry slice; the other two are
# reserved enum values so the wire schema does not need to change when the
# follow-up degradation slices land.
LOCALIZATION_MODES: frozenset[str] = frozenset(
    {
        "sbfl_per_test",
        "sbfl_aggregate",
        "failure_proximity",
    }
)


# Confidence enum — design-of-record §2 ("a ``confidence`` field
# (``high`` / ``medium`` / ``low``)").
LOCALIZATION_CONFIDENCES: frozenset[str] = frozenset({"high", "medium", "low"})


# Formula enum — design-of-record §1.
FORMULAS: frozenset[str] = frozenset({"ochiai", "op2", "dstar2", "tarantula"})


# CodeLocation kind — design-of-record §3 ("Output shape"). ``branch`` is
# reserved but not produced today.
CODE_LOCATION_KINDS: frozenset[str] = frozenset({"symbol", "line", "branch", "file"})


# EvidenceCitation kind — task brief §1. ``regression_fact`` is reserved for
# the aggregate-mode follow-up slice.
EVIDENCE_KINDS: frozenset[str] = frozenset({"test_result", "coverage_fact"})


@dataclass(slots=True, frozen=True)
class CodeLocation:
    """The implicated location for one ranked finding.

    ``kind`` discriminates symbol-level vs file-level (or future
    line/branch) entries. For symbol-level entries the resolver yielded a
    qualified symbol name and a ``(start_line, end_line)`` inclusive range;
    file-level entries (e.g. module-level code, file-level fallback for
    ecosystems without a symbol resolver) carry ``symbol=None`` and
    ``line_range=None``.

    ``primary_line`` is always populated and points at the single most
    suspicious line inside the entry; ``evidence_lines`` carries the other
    suspicious lines (top-K within the symbol or file) for AI-consumer
    transparency.
    """

    kind: str
    file: str
    symbol: str | None
    line_range: tuple[int, int] | None
    primary_line: int
    evidence_lines: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.kind not in CODE_LOCATION_KINDS:
            raise ValueError(
                f"Invalid CodeLocation.kind={self.kind!r}; "
                f"expected one of {sorted(CODE_LOCATION_KINDS)!r}"
            )
        if self.line_range is not None:
            start, end = self.line_range
            if start > end:
                raise ValueError(
                    f"CodeLocation.line_range start>end: {self.line_range!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.file,
            "symbol": self.symbol,
            "line_range": (
                None
                if self.line_range is None
                else [self.line_range[0], self.line_range[1]]
            ),
            "primary_line": self.primary_line,
            "evidence_lines": list(self.evidence_lines),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        _require_keys(d, ("kind", "file", "primary_line"), cls.__name__)
        line_range_raw = d.get("line_range")
        return cls(
            kind=str(d["kind"]),
            file=str(d["file"]),
            symbol=_opt_str(d.get("symbol")),
            line_range=(
                None
                if line_range_raw is None
                else (int(line_range_raw[0]), int(line_range_raw[1]))
            ),
            primary_line=int(d["primary_line"]),
            evidence_lines=tuple(int(x) for x in (d.get("evidence_lines") or ())),
        )


@dataclass(slots=True, frozen=True)
class EvidenceCitation:
    """Per-entry traceability back to the run evidence (NFR-LOC-001).

    ``selector`` is a discriminated payload whose shape depends on
    ``kind`` — the closed shapes for this slice are pinned by the task
    brief §1:

    - ``kind == "test_result"`` →
      ``selector = {"test_id": <nodeid>, "outcome": "failed"}``
    - ``kind == "coverage_fact"`` →
      ``selector = {"file": <path>, "lines": [<int>, ...]}``

    The ``regression_fact`` kind is reserved for the aggregate-mode slice
    (where the FLUCCS-style regression-aware reweighting fires).
    """

    kind: str
    run_reference: RunReference
    selector: dict[str, Any]

    def __post_init__(self) -> None:
        if self.kind not in EVIDENCE_KINDS:
            raise ValueError(
                f"Invalid EvidenceCitation.kind={self.kind!r}; "
                f"expected one of {sorted(EVIDENCE_KINDS)!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "run_reference": self.run_reference.to_dict(),
            "selector": dict(self.selector),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        _require_keys(d, ("kind", "run_reference", "selector"), cls.__name__)
        return cls(
            kind=str(d["kind"]),
            run_reference=RunReference.from_dict(dict(d["run_reference"])),
            selector=dict(d["selector"]),
        )


@dataclass(slots=True, frozen=True)
class LocalizationEntry:
    """One ranked Localization Finding entry.

    ``rank`` is 1-based dense (ties share a rank, next rank skips); a tied
    entry's ``tied_with`` carries OTHER entries' handles sharing the same
    rank. The handle format pinned for this slice is the literal string
    ``"entry_index_<i>"`` where ``<i>`` is the 0-based index of the other
    entry within the truncated ``entries`` tuple (so ``entry_index_0`` is
    the top-ranked entry, etc.). This convention is a working draft —
    Manual Test fields it; PM freezes the shape in a follow-up decision.

    ``score_raw`` is the formula's native value for the ``formula`` field
    (NOT a fixed Ochiai-only pick — when a non-default formula is selected
    via the future CLI flag, this carries that formula's score).
    ``score_normalized`` is min-max within the ENTIRE finding set, applied
    before top_n truncation (design-of-record §4).

    ``alternate_scores`` carries the other three formulas' scores for the
    SAME location so AI consumers can compare without re-deriving.
    """

    rank: int
    tied_with: tuple[str, ...]
    code_location: CodeLocation
    score_raw: float
    score_normalized: float
    formula: str
    alternate_scores: dict[str, float]
    related_failed_tests: tuple[str, ...]
    evidence_citations: tuple[EvidenceCitation, ...]

    def __post_init__(self) -> None:
        if self.formula not in FORMULAS:
            raise ValueError(
                f"Invalid LocalizationEntry.formula={self.formula!r}; "
                f"expected one of {sorted(FORMULAS)!r}"
            )
        if self.rank < 1:
            raise ValueError(
                f"LocalizationEntry.rank must be 1-based positive, got {self.rank!r}"
            )
        for alt_formula in self.alternate_scores:
            if alt_formula not in FORMULAS:
                raise ValueError(
                    f"Invalid LocalizationEntry.alternate_scores key="
                    f"{alt_formula!r}; expected one of {sorted(FORMULAS)!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "tied_with": list(self.tied_with),
            "code_location": self.code_location.to_dict(),
            "score_raw": self.score_raw,
            "score_normalized": self.score_normalized,
            "formula": self.formula,
            "alternate_scores": dict(self.alternate_scores),
            "related_failed_tests": list(self.related_failed_tests),
            "evidence_citations": [c.to_dict() for c in self.evidence_citations],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "rank",
            "code_location",
            "score_raw",
            "score_normalized",
            "formula",
        )
        _require_keys(d, required, cls.__name__)
        return cls(
            rank=int(d["rank"]),
            tied_with=tuple(str(x) for x in (d.get("tied_with") or ())),
            code_location=CodeLocation.from_dict(dict(d["code_location"])),
            score_raw=float(d["score_raw"]),
            score_normalized=float(d["score_normalized"]),
            formula=str(d["formula"]),
            alternate_scores={
                str(k): float(v)
                for k, v in (d.get("alternate_scores") or {}).items()
            },
            related_failed_tests=tuple(
                str(x) for x in (d.get("related_failed_tests") or ())
            ),
            evidence_citations=tuple(
                EvidenceCitation.from_dict(dict(c))
                for c in (d.get("evidence_citations") or ())
            ),
        )


@dataclass(slots=True, frozen=True)
class LocalizationFinding:
    """Top-level persisted Localization payload for one run.

    Persisted at
    ``<store>/localization/findings/run_<run_id>/localization_findings.json``
    — this filename and directory layout is **load-bearing**: Memory's
    ``_availability_flags`` probe (``src/novetest/memory/store.py:_availability_flags``)
    auto-flips ``MemoryEntry.has_localization_findings`` based on the
    existence of this exact path. Do NOT rename.

    ``mode`` is one of ``LOCALIZATION_MODES``; ``confidence`` is one of
    ``LOCALIZATION_CONFIDENCES``; ``formula`` is the default presentation
    formula whose score drives ``rank`` (``"ochiai"`` today).
    ``alternate_scores_available`` enumerates the other formulas computed
    in parallel — design-of-record §1 mandates all four are computed and
    persisted so callers can switch presentation without re-derivation.
    """

    CURRENT_SCHEMA_VERSION: ClassVar[int] = SCHEMA_VERSION

    run_reference: RunReference
    engine_name: str
    ecosystem: str
    mode: str
    confidence: str
    formula: str
    alternate_scores_available: tuple[str, ...]
    top_n: int
    entries: tuple[LocalizationEntry, ...]
    derived_at: int
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.mode not in LOCALIZATION_MODES:
            raise ValueError(
                f"Invalid LocalizationFinding.mode={self.mode!r}; "
                f"expected one of {sorted(LOCALIZATION_MODES)!r}"
            )
        if self.confidence not in LOCALIZATION_CONFIDENCES:
            raise ValueError(
                f"Invalid LocalizationFinding.confidence={self.confidence!r}; "
                f"expected one of {sorted(LOCALIZATION_CONFIDENCES)!r}"
            )
        if self.formula not in FORMULAS:
            raise ValueError(
                f"Invalid LocalizationFinding.formula={self.formula!r}; "
                f"expected one of {sorted(FORMULAS)!r}"
            )
        for alt in self.alternate_scores_available:
            if alt not in FORMULAS:
                raise ValueError(
                    f"Invalid LocalizationFinding.alternate_scores_available "
                    f"entry={alt!r}; expected one of {sorted(FORMULAS)!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_reference": self.run_reference.to_dict(),
            "engine_name": self.engine_name,
            "ecosystem": self.ecosystem,
            "mode": self.mode,
            "confidence": self.confidence,
            "formula": self.formula,
            "alternate_scores_available": list(self.alternate_scores_available),
            "top_n": self.top_n,
            "entries": [e.to_dict() for e in self.entries],
            "derived_at": self.derived_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        required = (
            "schema_version",
            "run_reference",
            "engine_name",
            "ecosystem",
            "mode",
            "confidence",
            "formula",
            "top_n",
            "entries",
            "derived_at",
        )
        _require_keys(d, required, cls.__name__)
        schema_version = d["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported {cls.__name__} schema_version={schema_version!r}; "
                f"supported={SCHEMA_VERSION}"
            )
        return cls(
            run_reference=RunReference.from_dict(dict(d["run_reference"])),
            engine_name=str(d["engine_name"]),
            ecosystem=str(d["ecosystem"]),
            mode=str(d["mode"]),
            confidence=str(d["confidence"]),
            formula=str(d["formula"]),
            alternate_scores_available=tuple(
                str(x) for x in (d.get("alternate_scores_available") or ())
            ),
            top_n=int(d["top_n"]),
            entries=tuple(
                LocalizationEntry.from_dict(dict(e)) for e in d["entries"]
            ),
            derived_at=int(d["derived_at"]),
            metadata=dict(d.get("metadata") or {}),
            schema_version=int(schema_version),
        )


# --- internals ---------------------------------------------------------------


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], owner: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise ValueError(f"{owner}.from_dict missing required keys: {missing!r}")
