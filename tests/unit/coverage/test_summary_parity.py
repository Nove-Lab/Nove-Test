"""Byte-parity pins for the four native-coverage parsers (W2/S33, ANA-06).

Each test parses a deterministic native payload and compares the
persisted-form serialization — ``json.dumps(fact_set.to_dict(), indent=2)
+ "\\n"``, exactly what ``persistence.write_coverage_facts`` writes — against
an expected file captured at the pre-refactor base (``e32b3ec``), BEFORE the
summary arithmetic moved into ``coverage/_summary.py``. Any byte drift the
dedup introduces fails loudly here.

Expected files live at ``fixtures/summary_parity/<slug>.json``. Regenerate
them ONLY for a deliberate, PM-approved wire change.

ONE normalization is applied before comparing (in both the capture and the
tests): the volatile temp directory inside ``metadata.jacoco_xml_paths`` /
``metadata.cobertura_xml_paths`` is replaced by ``<TMP>`` (with POSIX
separators) — those entries echo the parse-time input location and are the
only machine-dependent bytes in the payload. Everything else is compared in
the exact persisted byte form.

The Istanbul payload deliberately puts TWO statements on one line so the
jest-only ``num_statements > len(executed_lines) + len(missing_lines)``
basis (ANA-04, contract-documented in ``models/coverage_fact_set.py``) is
pinned in bytes too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novetest.coverage.cobertura_parser import parse_cobertura_xml
from novetest.coverage.istanbul_parser import parse_istanbul_json
from novetest.coverage.jacoco_parser import parse_jacoco_xml
from novetest.coverage.lcov_parser import parse_lcov
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_reference import RunReference


_EXPECTED_DIR = Path(__file__).parent / "fixtures" / "summary_parity"

_DERIVED_AT = 1_700_000_002_000


def _ref(run_id: str) -> RunReference:
    return RunReference(run_id=run_id, created_at=1_700_000_000_000)


# --- deterministic payloads ---------------------------------------------------
#
# Percent ratios are chosen so the two historical rounding orderings
# (`round(c / n * 100.0, 2)` vs `round(100.0 * c / n, 2)`) agree for every
# summary in these fixtures — the captures stay valid across the dedup.

_LCOV_BODY = """\
TN:
SF:/ws/cargo-project/src/lib.rs
DA:1,5
DA:2,5
DA:3,0
LF:3
LH:2
end_of_record
SF:/ws/cargo-project/src/branchy.rs
DA:4,1
DA:5,0
BRDA:4,0,0,1
BRDA:4,0,1,0
LF:2
LH:1
BRF:2
BRH:1
end_of_record
"""


_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<report name="parity">
    <package name="com/example">
        <sourcefile name="Calculator.java">
            <line nr="3" mi="0" ci="3" mb="0" cb="0"/>
            <line nr="7" mi="0" ci="2" mb="0" cb="0"/>
            <line nr="10" mi="3" ci="0" mb="0" cb="0"/>
            <line nr="13" mi="0" ci="2" mb="1" cb="1"/>
        </sourcefile>
    </package>
    <package name="com/example/util">
        <sourcefile name="Helper.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
            <line nr="2" mi="1" ci="0" mb="0" cb="0"/>
        </sourcefile>
    </package>
</report>
"""


_COBERTURA_XML = """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.6" branch-rate="0" lines-covered="3" lines-valid="5"
          timestamp="0" version="6.0.2" complexity="0">
  <sources>
    <source>/ws/dotnet-project</source>
  </sources>
  <packages>
    <package name="MathLib" line-rate="0.5" branch-rate="0" complexity="0">
      <classes>
        <class name="MathLib.MathOps" filename="MathLib/MathOps.cs"
               line-rate="0.5" branch-rate="0" complexity="0">
          <lines>
            <line number="14" hits="1" branch="false"/>
            <line number="15" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
    <package name="StringLib" line-rate="0.66" branch-rate="0" complexity="0">
      <classes>
        <class name="StringLib.StringOps" filename="StringLib/StringOps.cs"
               line-rate="0.66" branch-rate="0" complexity="0">
          <lines>
            <line number="4" hits="2" branch="false"/>
            <line number="5" hits="2" branch="false"/>
            <line number="6" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def _istanbul_payload() -> dict[str, Any]:
    """Two-file Istanbul payload; calc.js has 2 statements on line 1."""
    return {
        "/ws/jest-project/src/calc.js": {
            "path": "/ws/jest-project/src/calc.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 10},
                },
                "1": {
                    "start": {"line": 1, "column": 12},
                    "end": {"line": 1, "column": 24},
                },
                "2": {
                    "start": {"line": 5, "column": 2},
                    "end": {"line": 5, "column": 18},
                },
            },
            "fnMap": {},
            "branchMap": {},
            "s": {"0": 3, "1": 3, "2": 0},
            "f": {},
            "b": {},
        },
        "/ws/jest-project/src/util.js": {
            "path": "/ws/jest-project/src/util.js",
            "statementMap": {
                "0": {
                    "start": {"line": 1, "column": 0},
                    "end": {"line": 1, "column": 12},
                },
            },
            "fnMap": {},
            "branchMap": {},
            "s": {"0": 1},
            "f": {},
            "b": {},
        },
    }


# --- fact-set builders (shared with the capture script) -----------------------


def build_lcov_fact_set(tmp_path: Path) -> CoverageFactSet:
    lcov_path = tmp_path / "coverage.lcov"
    lcov_path.write_text(_LCOV_BODY, encoding="utf-8")
    return parse_lcov(
        lcov_path,
        run_reference=_ref("01PARITYLCOV000000000000FACT"),
        engine_name="cargo-test",
        ecosystem="rust",
        workspace_root=Path("/ws/cargo-project"),
        derived_at=_DERIVED_AT,
    )


def build_jacoco_fact_set(tmp_path: Path) -> CoverageFactSet:
    xml_path = tmp_path / "jacoco.xml"
    xml_path.write_text(_JACOCO_XML, encoding="utf-8")
    return parse_jacoco_xml(
        [xml_path],
        run_reference=_ref("01PARITYJACOCO0000000000FACT"),
        engine_name="junit",
        ecosystem="java",
        workspace_root=Path("/ws/java-project"),
        derived_at=_DERIVED_AT,
    )


def build_cobertura_fact_set(tmp_path: Path) -> CoverageFactSet:
    xml_path = tmp_path / "coverage.cobertura.xml"
    xml_path.write_text(_COBERTURA_XML, encoding="utf-8")
    return parse_cobertura_xml(
        [xml_path],
        run_reference=_ref("01PARITYCOBERTURA00000000FACT"),
        engine_name="xunit",
        ecosystem="dotnet",
        workspace_root=Path("/ws/dotnet-project"),
        derived_at=_DERIVED_AT,
    )


def build_istanbul_fact_set(tmp_path: Path) -> CoverageFactSet:
    del tmp_path  # istanbul parses an in-memory payload; kept for symmetry
    return parse_istanbul_json(
        _istanbul_payload(),
        run_reference=_ref("01PARITYISTANBUL00000000FACT"),
        engine_name="jest",
        ecosystem="javascript-typescript",
        workspace_root=Path("/ws/jest-project"),
        derived_at=_DERIVED_AT,
    )


# --- the parity pins ----------------------------------------------------------


def normalized_payload(fact_set: CoverageFactSet, tmp_path: Path) -> dict[str, Any]:
    """``to_dict()`` with the volatile temp dir tokenized (see module docstring)."""
    payload = fact_set.to_dict()
    metadata = payload.get("metadata", {})
    for key in ("jacoco_xml_paths", "cobertura_xml_paths"):
        if key in metadata:
            metadata[key] = [
                str(p).replace(str(tmp_path), "<TMP>").replace("\\", "/")
                for p in metadata[key]
            ]
    return payload


def _assert_persisted_bytes_match(
    fact_set: CoverageFactSet, tmp_path: Path, slug: str
) -> None:
    expected_path = _EXPECTED_DIR / f"{slug}.json"
    expected_text = expected_path.read_text(encoding="utf-8")
    payload = normalized_payload(fact_set, tmp_path)
    # Dict-level equality first: on drift this gives a readable diff.
    assert payload == json.loads(expected_text)
    # Then the exact persisted byte form (write_coverage_facts serialization).
    assert json.dumps(payload, indent=2) + "\n" == expected_text


def test_lcov_fact_set_bytes_match_base_capture(tmp_path: Path) -> None:
    _assert_persisted_bytes_match(
        build_lcov_fact_set(tmp_path), tmp_path, "cargo_lcov"
    )


def test_jacoco_fact_set_bytes_match_base_capture(tmp_path: Path) -> None:
    _assert_persisted_bytes_match(
        build_jacoco_fact_set(tmp_path), tmp_path, "junit_jacoco"
    )


def test_cobertura_fact_set_bytes_match_base_capture(tmp_path: Path) -> None:
    _assert_persisted_bytes_match(
        build_cobertura_fact_set(tmp_path), tmp_path, "xunit_cobertura"
    )


def test_istanbul_fact_set_bytes_match_base_capture(tmp_path: Path) -> None:
    _assert_persisted_bytes_match(
        build_istanbul_fact_set(tmp_path), tmp_path, "jest_istanbul"
    )
