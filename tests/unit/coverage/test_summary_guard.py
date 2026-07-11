"""Divergence guard for the shared summary seam (W2/S33, ANA-06).

Fails LOUDLY if any native parser re-grows a local percent / per-file /
aggregate summary implementation instead of delegating to
``novetest.coverage._summary``. Mechanism: behavioral sentinel probes —
each ``_summary`` seam is monkeypatched to emit an unmistakable sentinel,
every parser is run on a minimal payload, and the sentinel MUST surface in
the parser's output. A parser with a re-forked local implementation would
emit real numbers instead and fail here.

A source-level scan supplements the probes: the pre-S33 local helper
definitions and the inline ``else 100.0`` empty-convention form must not
reappear in the parser modules (or ``derive``, which delegates its
post-filter summary rebuild to the same seam).

The probes rely on the parsers binding the MODULE (``from
novetest.coverage import _summary``) and resolving attributes at call
time — do not "optimize" them into ``from ... import name`` imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.coverage import (
    _summary,
    cobertura_parser,
    derive,
    istanbul_parser,
    jacoco_parser,
    lcov_parser,
)
from novetest.models.coverage_fact_set import CoverageFactSet, CoverageSummary
from novetest.models.run_reference import RunReference


_REF = RunReference(run_id="01GUARD00000000000000000FACT", created_at=1)

_PERCENT_SENTINEL = 12345.0

_SUMMARY_SENTINEL = CoverageSummary(
    num_statements=424242,
    covered_statements=424241,
    missing_statements=1,
    excluded_statements=0,
    num_branches=0,
    covered_branches=0,
    missing_branches=0,
    percent_covered=99.99,
)


# --- minimal payload runners (one per parser) ---------------------------------


def _run_lcov(tmp_path: Path) -> CoverageFactSet:
    lcov_path = tmp_path / "guard.lcov"
    lcov_path.write_text(
        "TN:\nSF:/ws/g/src/lib.rs\nDA:1,1\nDA:2,0\nend_of_record\n",
        encoding="utf-8",
    )
    return lcov_parser.parse_lcov(
        lcov_path,
        run_reference=_REF,
        engine_name="cargo-test",
        ecosystem="rust",
        workspace_root=Path("/ws/g"),
        derived_at=1,
    )


def _run_jacoco(tmp_path: Path) -> CoverageFactSet:
    xml_path = tmp_path / "guard-jacoco.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<report name="guard">
    <package name="com/g">
        <sourcefile name="G.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
            <line nr="2" mi="1" ci="0" mb="0" cb="0"/>
        </sourcefile>
    </package>
</report>
""",
        encoding="utf-8",
    )
    return jacoco_parser.parse_jacoco_xml(
        [xml_path],
        run_reference=_REF,
        engine_name="junit",
        ecosystem="java",
        workspace_root=Path("/ws/g"),
        derived_at=1,
    )


def _run_cobertura(tmp_path: Path) -> CoverageFactSet:
    xml_path = tmp_path / "guard-cobertura.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.5" branch-rate="0" lines-covered="1" lines-valid="2"
          timestamp="0" version="6.0.2" complexity="0">
  <sources><source>/ws/g</source></sources>
  <packages>
    <package name="G" line-rate="0.5" branch-rate="0" complexity="0">
      <classes>
        <class name="G.Ops" filename="G/Ops.cs"
               line-rate="0.5" branch-rate="0" complexity="0">
          <lines>
            <line number="1" hits="1" branch="false"/>
            <line number="2" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        encoding="utf-8",
    )
    return cobertura_parser.parse_cobertura_xml(
        [xml_path],
        run_reference=_REF,
        engine_name="xunit",
        ecosystem="dotnet",
        workspace_root=Path("/ws/g"),
        derived_at=1,
    )


def _run_istanbul(tmp_path: Path) -> CoverageFactSet:
    del tmp_path
    payload: dict[str, Any] = {
        "/ws/g/src/g.js": {
            "path": "/ws/g/src/g.js",
            "statementMap": {
                "0": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 5}},
                "1": {"start": {"line": 2, "column": 0}, "end": {"line": 2, "column": 5}},
            },
            "fnMap": {},
            "branchMap": {},
            "s": {"0": 1, "1": 0},
            "f": {},
            "b": {},
        }
    }
    return istanbul_parser.parse_istanbul_json(
        payload,
        run_reference=_REF,
        engine_name="jest",
        ecosystem="javascript-typescript",
        workspace_root=Path("/ws/g"),
        derived_at=1,
    )


_RUNNERS = {
    "lcov": _run_lcov,
    "jacoco": _run_jacoco,
    "cobertura": _run_cobertura,
    "istanbul": _run_istanbul,
}


# --- probe A: the percent convention has exactly ONE home ---------------------


@pytest.mark.parametrize("parser_name", sorted(_RUNNERS))
def test_every_percent_routes_through_shared_percent_covered(
    parser_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _summary, "percent_covered", lambda num, covered: _PERCENT_SENTINEL
    )
    fact_set = _RUNNERS[parser_name](tmp_path)
    assert fact_set.summary.percent_covered == _PERCENT_SENTINEL, (
        f"{parser_name}: top-level percent bypassed _summary.percent_covered"
    )
    for file_coverage in fact_set.files:
        assert file_coverage.summary.percent_covered == _PERCENT_SENTINEL, (
            f"{parser_name}: per-file percent for {file_coverage.file_path} "
            "bypassed _summary.percent_covered"
        )


# --- probe B: top-level aggregation has exactly ONE home ----------------------


@pytest.mark.parametrize("parser_name", sorted(_RUNNERS))
def test_top_level_summary_routes_through_shared_aggregate(
    parser_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _summary, "aggregate_summary", lambda files: _SUMMARY_SENTINEL
    )
    fact_set = _RUNNERS[parser_name](tmp_path)
    assert fact_set.summary == _SUMMARY_SENTINEL, (
        f"{parser_name}: top-level summary bypassed _summary.aggregate_summary"
    )


# --- probe C: the per-file builder has exactly ONE home -----------------------


@pytest.mark.parametrize("parser_name", sorted(_RUNNERS))
def test_per_file_summaries_route_through_shared_builder(
    parser_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _summary,
        "summary_from_counts",
        lambda **kwargs: _SUMMARY_SENTINEL,
    )
    fact_set = _RUNNERS[parser_name](tmp_path)
    assert fact_set.files, f"{parser_name}: guard payload produced no files"
    for file_coverage in fact_set.files:
        assert file_coverage.summary == _SUMMARY_SENTINEL, (
            f"{parser_name}: per-file summary for {file_coverage.file_path} "
            "bypassed _summary.summary_from_counts"
        )


# --- source-level supplement ---------------------------------------------------


_FORBIDDEN_FRAGMENTS = (
    "def _percent_covered",
    "def _aggregate_summary",
    "def _build_file_summary",
    "def _statement_summary",
    "def _aggregate_file_summary",
    "else 100.0",
)


@pytest.mark.parametrize(
    "module",
    [lcov_parser, jacoco_parser, cobertura_parser, istanbul_parser, derive],
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_no_local_summary_implementations_in_source(module: Any) -> None:
    assert module.__file__ is not None
    source = Path(module.__file__).read_text(encoding="utf-8")
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in source, (
            f"{module.__name__} re-grew a local summary implementation "
            f"({fragment!r}) — delegate to novetest.coverage._summary instead"
        )
