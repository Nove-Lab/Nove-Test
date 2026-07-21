"""Unit tests for `novetest.coverage.jacoco_parser`.

The parser converts JaCoCo's XML report (``jacoco.xml`` /
``jacocoTestReport.xml``) into a structured ``CoverageFactSet``.
Aggregate-mode only; per-test-class is out-of-scope for v1 per brief
§6 D1. Multi-module Maven aggregation is exercised separately via the
``module_prefix_for`` parameter.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.jacoco_parser import parse_jacoco_xml
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.run_reference import RunReference


_RUN_REF = RunReference(run_id="r1", created_at=1)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


_BASIC_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<report name="basic">
    <package name="com/example">
        <class name="com/example/Calculator" sourcefilename="Calculator.java">
            <counter type="LINE" missed="0" covered="4"/>
        </class>
        <sourcefile name="Calculator.java">
            <line nr="3" mi="0" ci="3" mb="0" cb="0"/>
            <line nr="7" mi="0" ci="2" mb="0" cb="0"/>
            <line nr="10" mi="3" ci="0" mb="0" cb="0"/>
            <line nr="13" mi="0" ci="2" mb="1" cb="1"/>
            <counter type="LINE" missed="1" covered="3"/>
        </sourcefile>
    </package>
    <counter type="LINE" missed="1" covered="3"/>
</report>
"""


_MULTI_PACKAGE_JACOCO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<report name="multi-pkg">
    <package name="com/example/a">
        <sourcefile name="ClassA.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
        </sourcefile>
    </package>
    <package name="com/example/b">
        <sourcefile name="ClassB.java">
            <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
            <line nr="2" mi="1" ci="0" mb="0" cb="0"/>
        </sourcefile>
    </package>
</report>
"""


class TestParseJacocoXmlSingleModule:
    def test_basic_parse(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(_BASIC_JACOCO_XML, encoding="utf-8")

        fact_set = parse_jacoco_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="junit",
            ecosystem="java",
            workspace_root=tmp_path,
        )

        assert fact_set.engine_name == "junit"
        assert fact_set.ecosystem == "java"
        assert fact_set.mapping_granularity == "aggregate"
        assert len(fact_set.files) == 1

        fc = fact_set.files[0]
        assert fc.file_path == "src/main/java/com/example/Calculator.java"
        assert fc.executed_lines == (3, 7, 13)
        assert fc.missing_lines == (10,)
        # Branches: 1 covered (line 13, index 0) + 1 missed (line 13, index 1).
        assert fc.executed_branches == ((13, 0),)
        assert fc.missing_branches == ((13, 1),)
        assert fc.summary.num_statements == 4
        assert fc.summary.covered_statements == 3
        assert fc.summary.missing_statements == 1
        assert fc.summary.num_branches == 2
        assert fc.summary.covered_branches == 1
        assert fc.summary.missing_branches == 1

    def test_multi_package(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(_MULTI_PACKAGE_JACOCO_XML, encoding="utf-8")

        fact_set = parse_jacoco_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="junit",
            ecosystem="java",
            workspace_root=tmp_path,
        )
        # Sorted by file_path deterministically.
        paths = [f.file_path for f in fact_set.files]
        assert paths == [
            "src/main/java/com/example/a/ClassA.java",
            "src/main/java/com/example/b/ClassB.java",
        ]

        # Aggregate summary: 3 statements total, 2 covered.
        assert fact_set.summary.num_statements == 3
        assert fact_set.summary.covered_statements == 2
        assert fact_set.summary.missing_statements == 1
        # percent_covered = round(100 * 2 / 3, 2) = 66.67
        assert fact_set.summary.percent_covered == pytest.approx(66.67, abs=0.01)

    def test_metadata_is_pinned(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(_BASIC_JACOCO_XML, encoding="utf-8")

        fact_set = parse_jacoco_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="junit",
            ecosystem="java",
            workspace_root=tmp_path,
        )
        assert fact_set.metadata["coverage_format"] == "jacoco-xml"
        assert (
            fact_set.metadata["branch_arc_semantics"]
            == "jacoco-line-counter-index"
        )
        assert fact_set.metadata["jacoco_xml_paths"] == [str(xml_path)]


class TestParseJacocoXmlMultiModule:
    def test_module_prefix_for(self, tmp_path: Path) -> None:
        """Multi-module Maven D2: each per-module XML's FileCoverage
        entries are prefixed with the module dir name so paths stay
        workspace-relative + unambiguous."""

        # Two module XMLs with overlapping source paths but different
        # packages — verify each gets the correct prefix.
        module_a_xml = tmp_path / "module-a" / "target" / "site" / "jacoco" / "jacoco.xml"
        module_b_xml = tmp_path / "module-b" / "target" / "site" / "jacoco" / "jacoco.xml"
        module_a_xml.parent.mkdir(parents=True)
        module_b_xml.parent.mkdir(parents=True)

        module_a_xml.write_text(
            """<?xml version="1.0"?>
            <report name="a">
                <package name="com/example/a">
                    <sourcefile name="A.java">
                        <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
                    </sourcefile>
                </package>
            </report>""",
            encoding="utf-8",
        )
        module_b_xml.write_text(
            """<?xml version="1.0"?>
            <report name="b">
                <package name="com/example/b">
                    <sourcefile name="B.java">
                        <line nr="1" mi="0" ci="1" mb="0" cb="0"/>
                    </sourcefile>
                </package>
            </report>""",
            encoding="utf-8",
        )

        prefix_map = {
            str(module_a_xml): "module-a",
            str(module_b_xml): "module-b",
        }

        fact_set = parse_jacoco_xml(
            [module_a_xml, module_b_xml],
            run_reference=_RUN_REF,
            engine_name="junit",
            ecosystem="java",
            workspace_root=tmp_path,
            module_prefix_for=prefix_map,
        )

        paths = [f.file_path for f in fact_set.files]
        assert paths == [
            "module-a/src/main/java/com/example/a/A.java",
            "module-b/src/main/java/com/example/b/B.java",
        ]


class TestParseJacocoXmlErrors:
    def test_no_paths_raises(self) -> None:
        with pytest.raises(CoverageJsonParseError):
            parse_jacoco_xml(
                [],
                run_reference=_RUN_REF,
                engine_name="junit",
                ecosystem="java",
                workspace_root=Path("/tmp"),
            )

    def test_empty_xml_raises(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text("", encoding="utf-8")

        with pytest.raises(CoverageJsonParseError, match="empty"):
            parse_jacoco_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="junit",
                ecosystem="java",
                workspace_root=tmp_path,
            )

    def test_malformed_xml_raises(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text("<not closed", encoding="utf-8")
        with pytest.raises(CoverageJsonParseError, match="Malformed"):
            parse_jacoco_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="junit",
                ecosystem="java",
                workspace_root=tmp_path,
            )

    def test_wrong_root_tag_raises(self, tmp_path: Path) -> None:
        xml_path = tmp_path / "jacoco.xml"
        xml_path.write_text(
            "<?xml version='1.0'?><not_a_report/>",
            encoding="utf-8",
        )
        with pytest.raises(CoverageJsonParseError, match="root tag"):
            parse_jacoco_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="junit",
                ecosystem="java",
                workspace_root=tmp_path,
            )


class TestParseJacocoRealGolden:
    """Real-artifact golden (ANA-15): parse a byte-verbatim ``jacoco.xml``
    captured from an actual Maven + JaCoCo run so the real report shape is
    exercised on hosts WITHOUT a JVM (CI cells lacking Java skip the
    ``test_junit_jacoco_derive.py`` integration sibling; this golden keeps
    the real-shape signal alive there).

    The inline XML samples elsewhere in this module omit the pieces a real
    JaCoCo report carries: the ``<!DOCTYPE report PUBLIC "-//JACOCO//DTD
    Report 1.1//EN" ...>`` declaration, ``<sessioninfo>``, and the full
    ``<class>/<method>/<counter>`` nesting the parser must skip past to
    reach ``<sourcefile>``. A JaCoCo version bump that reorders/renests any
    of that would slip past the inline tests but is caught here.

    Provenance — ``tests/fixtures/projects/junit-maven-basic`` run with
    ``mvn -B test`` under: JDK 17.0.19, Apache Maven 3.9.16,
    jacoco-maven-plugin 0.8.11, maven-surefire-plugin 3.2.5,
    JUnit Jupiter 5.10.2 (JaCoCo DTD Report 1.1). Committed byte-verbatim
    (nothing stripped — the machine-local ``<sessioninfo>`` id/timestamps
    are inert to the parser, which reads only ``<sourcefile>`` lines).
    """

    def test_real_golden_parses_to_expected_fact_set(self) -> None:
        golden = _FIXTURES_DIR / "jacoco_junit_maven_basic.xml"

        fact_set = parse_jacoco_xml(
            [golden],
            run_reference=_RUN_REF,
            engine_name="junit",
            ecosystem="java",
            workspace_root=_FIXTURES_DIR,
        )

        assert fact_set.engine_name == "junit"
        assert fact_set.ecosystem == "java"
        assert fact_set.mapping_granularity == "aggregate"

        # Single sourcefile in the fixture: Calculator.java, composed under
        # the standard Maven ``src/main/java`` layout.
        assert len(fact_set.files) == 1
        fc = fact_set.files[0]
        assert fc.file_path == "src/main/java/com/example/Calculator.java"

        # Every Calculator method is exercised by the companion test class
        # (add/subtract/multiply/divide + the ctor line), so the fixture is
        # fully covered — no missing lines.
        assert fc.executed_lines == (15, 18, 23, 27, 31, 32, 34)
        assert fc.missing_lines == ()

        # divide()'s ``if (b == 0)`` is the only branch point; both arms are
        # covered (testDivide passes b!=0, testDivideByZero passes b==0), so
        # the parser synthesizes two covered branch indices on line 31 and
        # no missing branch. This is the real-artifact branch-extraction
        # signal ANA-15 asked for.
        assert fc.executed_branches == ((31, 0), (31, 1))
        assert fc.missing_branches == ()

        assert fc.summary.num_statements == 7
        assert fc.summary.covered_statements == 7
        assert fc.summary.missing_statements == 0
        assert fc.summary.num_branches == 2
        assert fc.summary.covered_branches == 2
        assert fc.summary.missing_branches == 0

        # Aggregate roll-up mirrors the single file.
        assert fact_set.summary.num_statements == 7
        assert fact_set.summary.covered_statements == 7
        assert fact_set.summary.num_branches == 2
        assert fact_set.summary.percent_covered == pytest.approx(100.0)

        assert fact_set.metadata["coverage_format"] == "jacoco-xml"
        assert (
            fact_set.metadata["branch_arc_semantics"]
            == "jacoco-line-counter-index"
        )
