"""Unit tests for the JUnit 5 (Jupiter) Native Engine adapter.

Mirrors `test_gotest_adapter.py` / `test_cargo_adapter.py` in shape:
covers build-tool detection, manifest-based dependency parsing
(Jupiter / JUnit 4 / TestNG / JaCoCo), Surefire-XML normalization
across the four outcome categories, and the failure-log per-test-write
side effect. The end-to-end adapter invocation is exercised by the
integration tests under `tests/integration/run/test_junit_*.py` — this
file isolates the pure helpers from the subprocess seam.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from novetest.run.adapters import junit_adapter
from novetest.run.adapters.junit_adapter import (
    _detect_build_tool,
    _detects_junit4_in_manifest,
    _detects_jupiter_in_manifest,
    _detects_testng_in_manifest,
    _gradle_declares_jacoco,
    _maven_module_paths,
    _maven_pom_declares_jacoco,
    _normalize_test_case,
    _parse_surefire_reports_dir,
    _safe_failure_log_name,
    _stage_coverage_xml,
    _stage_reports_dir,
    _strip_trailing_parens,
    _summarize_tests,
)
from novetest.run.types import TestTarget
from novetest.utils.asyncio_subprocess import SubprocessResult


# ---------------------------------------------------------------------------
# _detect_build_tool: all four manifest combinations
# ---------------------------------------------------------------------------


class TestDetectBuildTool:
    def test_maven_only(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        assert _detect_build_tool(tmp_path) == "maven"

    def test_gradle_groovy_only(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle").write_text("// gradle groovy", encoding="utf-8")
        assert _detect_build_tool(tmp_path) == "gradle"

    def test_gradle_kotlin_only(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle.kts").write_text("// gradle kts", encoding="utf-8")
        assert _detect_build_tool(tmp_path) == "gradle"

    def test_neither(self, tmp_path: Path) -> None:
        assert _detect_build_tool(tmp_path) is None

    def test_both_maven_wins(self, tmp_path: Path) -> None:
        # D3 tiebreaker — Maven wins when both manifests present. The
        # warning is surfaced on the run's payload by `run_junit`; the
        # pure detect helper just returns the winner.
        (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
        (tmp_path / "build.gradle.kts").write_text("plugins { }", encoding="utf-8")
        assert _detect_build_tool(tmp_path) == "maven"


# ---------------------------------------------------------------------------
# _detects_jupiter_in_manifest: Maven + Gradle DSLs, positive + negative
# ---------------------------------------------------------------------------


class TestDetectsJupiterInManifest:
    def test_maven_with_jupiter(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies>
                <dependency>
                    <groupId>org.junit.jupiter</groupId>
                    <artifactId>junit-jupiter</artifactId>
                    <version>5.10.2</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "maven") is True

    def test_maven_with_jupiter_api_artifact_id(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies>
                <dependency>
                    <groupId>org.junit.jupiter</groupId>
                    <artifactId>junit-jupiter-api</artifactId>
                    <version>5.11.0</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "maven") is True

    def test_maven_without_test_framework(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies></dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "maven") is False

    def test_maven_with_junit4_only(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies>
                <dependency>
                    <artifactId>junit</artifactId>
                    <version>4.13.2</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "maven") is False
        assert _detects_junit4_in_manifest(tmp_path, "maven") is True

    def test_gradle_groovy_with_jupiter(self, tmp_path: Path) -> None:
        content = """
        dependencies {
            testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
        }
        """
        (tmp_path / "build.gradle").write_text(content, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "gradle") is True

    def test_gradle_kotlin_with_jupiter(self, tmp_path: Path) -> None:
        content = """
        dependencies {
            testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
        }
        """
        (tmp_path / "build.gradle.kts").write_text(content, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "gradle") is True

    def test_gradle_kotlin_with_bom_pattern(self, tmp_path: Path) -> None:
        """The fixture pattern: `platform("org.junit:junit-bom:X") +
        testImplementation("org.junit.jupiter:junit-jupiter")`."""

        content = """
        dependencies {
            testImplementation(platform("org.junit:junit-bom:5.10.2"))
            testImplementation("org.junit.jupiter:junit-jupiter")
        }
        """
        (tmp_path / "build.gradle.kts").write_text(content, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "gradle") is True

    def test_gradle_without_jupiter(self, tmp_path: Path) -> None:
        content = "dependencies {}"
        (tmp_path / "build.gradle").write_text(content, encoding="utf-8")
        assert _detects_jupiter_in_manifest(tmp_path, "gradle") is False


# ---------------------------------------------------------------------------
# _detects_junit4_in_manifest + _detects_testng_in_manifest (D5)
# ---------------------------------------------------------------------------


class TestDetectsJunit4AndTestng:
    def test_junit4_maven_4_13(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies>
                <dependency>
                    <artifactId>junit</artifactId>
                    <version>4.13.2</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_junit4_in_manifest(tmp_path, "maven") is True

    def test_junit4_maven_5_is_not_junit4(self, tmp_path: Path) -> None:
        """`junit-jupiter` 5.x must NOT match the JUnit-4 regex —
        the artifactId is the discriminant."""

        pom = """<project>
            <dependencies>
                <dependency>
                    <artifactId>junit-jupiter</artifactId>
                    <version>5.10.2</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_junit4_in_manifest(tmp_path, "maven") is False

    def test_junit4_gradle(self, tmp_path: Path) -> None:
        content = """
        dependencies {
            testImplementation 'junit:junit:4.13.2'
        }
        """
        (tmp_path / "build.gradle").write_text(content, encoding="utf-8")
        assert _detects_junit4_in_manifest(tmp_path, "gradle") is True

    def test_testng_maven(self, tmp_path: Path) -> None:
        pom = """<project>
            <dependencies>
                <dependency>
                    <groupId>org.testng</groupId>
                    <artifactId>testng</artifactId>
                    <version>7.10.2</version>
                </dependency>
            </dependencies>
        </project>"""
        (tmp_path / "pom.xml").write_text(pom, encoding="utf-8")
        assert _detects_testng_in_manifest(tmp_path, "maven") is True

    def test_testng_gradle(self, tmp_path: Path) -> None:
        content = """
        dependencies {
            testImplementation 'org.testng:testng:7.10.2'
        }
        """
        (tmp_path / "build.gradle").write_text(content, encoding="utf-8")
        assert _detects_testng_in_manifest(tmp_path, "gradle") is True


# ---------------------------------------------------------------------------
# JaCoCo detection
# ---------------------------------------------------------------------------


class TestJacocoDetection:
    def test_maven_pom_declares_jacoco(self) -> None:
        pom = """<project>
            <build>
                <plugins>
                    <plugin>
                        <artifactId>jacoco-maven-plugin</artifactId>
                        <version>0.8.11</version>
                    </plugin>
                </plugins>
            </build>
        </project>"""
        assert _maven_pom_declares_jacoco(pom) is True

    def test_maven_pom_without_jacoco(self) -> None:
        pom = "<project></project>"
        assert _maven_pom_declares_jacoco(pom) is False

    def test_gradle_groovy_apply_plugin(self) -> None:
        content = "apply plugin: 'jacoco'"
        assert _gradle_declares_jacoco(content) is True

    def test_gradle_kotlin_id_block(self) -> None:
        content = """plugins {
    `java-library`
    jacoco
}"""
        assert _gradle_declares_jacoco(content) is True

    def test_gradle_jacoco_block(self) -> None:
        content = "jacoco { toolVersion = '0.8.11' }"
        assert _gradle_declares_jacoco(content) is True

    def test_gradle_without_jacoco(self) -> None:
        content = "plugins { `java-library` }"
        assert _gradle_declares_jacoco(content) is False


# ---------------------------------------------------------------------------
# _maven_module_paths (multi-module detection)
# ---------------------------------------------------------------------------


class TestMavenModulePaths:
    def test_single_module_returns_empty(self, tmp_path: Path) -> None:
        pom = "<project><dependencies></dependencies></project>"
        assert _maven_module_paths(tmp_path, pom) == []

    def test_multi_module(self, tmp_path: Path) -> None:
        # Create child module dirs so `_maven_module_paths` accepts them.
        (tmp_path / "module-a").mkdir()
        (tmp_path / "module-b").mkdir()
        pom = """<project>
            <modules>
                <module>module-a</module>
                <module>module-b</module>
            </modules>
        </project>"""
        result = _maven_module_paths(tmp_path, pom)
        names = sorted(p.name for p in result)
        assert names == ["module-a", "module-b"]

    def test_missing_module_dir_is_skipped(self, tmp_path: Path) -> None:
        # Only module-a exists; module-b is declared but the directory
        # is absent — it should be filtered out silently.
        (tmp_path / "module-a").mkdir()
        pom = """<project>
            <modules>
                <module>module-a</module>
                <module>module-b</module>
            </modules>
        </project>"""
        result = _maven_module_paths(tmp_path, pom)
        names = [p.name for p in result]
        assert names == ["module-a"]


# ---------------------------------------------------------------------------
# Surefire XML parsing (`_parse_surefire_reports_dir`)
# ---------------------------------------------------------------------------


_SUREFIRE_XML_HAPPY_PATH = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.CalculatorTest" tests="4" failures="1" errors="0" skipped="1" time="0.5">
    <testcase classname="com.example.CalculatorTest" name="testAdd" time="0.001"/>
    <testcase classname="com.example.CalculatorTest" name="testSubtract" time="0.002">
        <failure message="expected: &lt;1&gt; but was: &lt;0&gt;" type="org.opentest4j.AssertionFailedError">
org.opentest4j.AssertionFailedError: expected: &lt;1&gt; but was: &lt;0&gt;
    at app//com.example.CalculatorTest.testSubtract(CalculatorTest.java:23)
        </failure>
        <system-out>captured stdout for failing test</system-out>
    </testcase>
    <testcase classname="com.example.CalculatorTest" name="testMultiply" time="0.001"/>
    <testcase classname="com.example.CalculatorTest" name="testIgnored" time="0">
        <skipped/>
    </testcase>
    <testcase classname="com.example.CalculatorTest" name="testCrash" time="0.0">
        <error message="kaboom" type="java.lang.RuntimeException">
java.lang.RuntimeException: kaboom
    at app//com.example.CalculatorTest.testCrash(CalculatorTest.java:42)
        </error>
    </testcase>
</testsuite>
"""


class TestParseSurefireReportsDir:
    def test_happy_path_all_four_outcomes(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "surefire-reports"
        reports_dir.mkdir()
        (reports_dir / "TEST-com.example.CalculatorTest.xml").write_text(
            _SUREFIRE_XML_HAPPY_PATH, encoding="utf-8"
        )
        failures_dir = tmp_path / "failures"
        artifact_dir = tmp_path  # any parent dir works for the rel-path call

        parsed_tests: list[dict[str, object]] = []
        reports_seen: list[dict[str, object]] = []
        failure_logs: dict[str, str] = {}

        _parse_surefire_reports_dir(
            reports_dir,
            module_name=None,
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
        )

        # 5 tests parsed.
        assert len(parsed_tests) == 5
        identities = [t["identity"] for t in parsed_tests]
        assert "com.example.CalculatorTest#testAdd" in identities
        assert "com.example.CalculatorTest#testSubtract" in identities
        assert "com.example.CalculatorTest#testIgnored" in identities
        assert "com.example.CalculatorTest#testCrash" in identities

        # Outcomes: 2 passed, 1 failed, 1 skipped, 1 errored.
        outcomes = [t["status"] for t in parsed_tests]
        assert outcomes.count("passed") == 2
        assert outcomes.count("failed") == 1
        assert outcomes.count("skipped") == 1
        assert outcomes.count("errored") == 1

        # Reports captured with format=junit-xml.
        assert len(reports_seen) == 1
        assert reports_seen[0]["format"] == "junit-xml"

        # Failed test got a per-test failure log written.
        assert "com.example.CalculatorTest#testSubtract" in failure_logs
        log_path = artifact_dir / failure_logs[
            "com.example.CalculatorTest#testSubtract"
        ]
        log_text = log_path.read_text(encoding="utf-8")
        assert "[message]" in log_text
        assert "expected:" in log_text
        assert "[stack]" in log_text
        assert "captured stdout for failing test" in log_text

        # Errored test ALSO gets a failure log (unified failure log path).
        assert "com.example.CalculatorTest#testCrash" in failure_logs

    def test_invalid_xml_recorded_as_invalid_format(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "surefire-reports"
        reports_dir.mkdir()
        (reports_dir / "TEST-bad.xml").write_text(
            "<not closed", encoding="utf-8"
        )
        parsed_tests: list[dict[str, object]] = []
        reports_seen: list[dict[str, object]] = []
        failure_logs: dict[str, str] = {}

        _parse_surefire_reports_dir(
            reports_dir,
            module_name=None,
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
        )

        # Malformed XML should be reported as invalid, not abort.
        assert len(parsed_tests) == 0
        assert len(reports_seen) == 1
        assert reports_seen[0]["format"] == "invalid"

    def test_module_name_propagates(self, tmp_path: Path) -> None:
        reports_dir = tmp_path / "surefire-reports"
        reports_dir.mkdir()
        (reports_dir / "TEST-com.example.CalculatorTest.xml").write_text(
            _SUREFIRE_XML_HAPPY_PATH, encoding="utf-8"
        )

        parsed_tests: list[dict[str, object]] = []
        reports_seen: list[dict[str, object]] = []
        failure_logs: dict[str, str] = {}

        _parse_surefire_reports_dir(
            reports_dir,
            module_name="module-a",
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
        )

        assert all(t.get("module") == "module-a" for t in parsed_tests)
        assert reports_seen[0]["module"] == "module-a"

    def test_testsuites_wrapper_is_handled(self, tmp_path: Path) -> None:
        """Surefire 3+ sometimes wraps multiple suites in a <testsuites>
        root; the parser must descend into the children."""

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <testsuites>
            <testsuite name="A">
                <testcase classname="A" name="passes"/>
            </testsuite>
            <testsuite name="B">
                <testcase classname="B" name="also_passes"/>
            </testsuite>
        </testsuites>
        """
        reports_dir = tmp_path / "surefire-reports"
        reports_dir.mkdir()
        (reports_dir / "TEST-multi.xml").write_text(xml, encoding="utf-8")

        parsed_tests: list[dict[str, object]] = []
        reports_seen: list[dict[str, object]] = []
        failure_logs: dict[str, str] = {}
        _parse_surefire_reports_dir(
            reports_dir,
            module_name=None,
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
        )
        identities = [t["identity"] for t in parsed_tests]
        assert identities == ["A#passes", "B#also_passes"]


# ---------------------------------------------------------------------------
# _normalize_test_case (single <testcase> mapping)
# ---------------------------------------------------------------------------


class TestNormalizeTestCase:
    def test_passed_no_failure_payload(self, tmp_path: Path) -> None:
        import xml.etree.ElementTree as ET

        case = ET.fromstring(
            '<testcase classname="X" name="t" time="0.123"/>'
        )
        failure_logs: dict[str, str] = {}
        entry = _normalize_test_case(
            case,
            module_name=None,
            report_path=tmp_path / "TEST-X.xml",
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
            failure_logs=failure_logs,
        )
        assert entry["status"] == "passed"
        assert entry["duration_ms"] == 123
        assert entry["failure"] is None

    def test_parametrized_display_name_preserved(self, tmp_path: Path) -> None:
        import xml.etree.ElementTree as ET

        # JUnit 5 ParameterizedTest display name shape:
        # `testFoo(int)[1] => 1`
        case = ET.fromstring(
            '<testcase classname="X" name="testFoo(int)[1] =&gt; 1" time="0.001"/>'
        )
        entry = _normalize_test_case(
            case,
            module_name=None,
            report_path=tmp_path / "TEST-X.xml",
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
            failure_logs={},
        )
        # Identity preserves the full display name verbatim (only a
        # *literal trailing* `()` is stripped — see TestStripTrailingParens).
        assert entry["identity"] == "X#testFoo(int)[1] => 1"

    def test_gradle_trailing_parens_stripped(self, tmp_path: Path) -> None:
        """Defect 3 hotfix (2026-06-04). Gradle 8+ JUnit XML emits
        ``<testcase name="testFoo()">`` (parens preserved for
        parameterless methods); Maven Surefire emits the same case as
        ``name="testFoo"``. ``_normalize_test_case`` must strip the
        literal trailing `()` so the resulting `identity` is byte-
        stable across build tools."""

        import xml.etree.ElementTree as ET

        gradle_case = ET.fromstring(
            '<testcase classname="com.example.CalculatorTest"'
            ' name="testSubtract()" time="0.002"/>'
        )
        entry_gradle = _normalize_test_case(
            gradle_case,
            module_name=None,
            report_path=tmp_path / "TEST-G.xml",
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
            failure_logs={},
        )
        maven_case = ET.fromstring(
            '<testcase classname="com.example.CalculatorTest"'
            ' name="testSubtract" time="0.002"/>'
        )
        entry_maven = _normalize_test_case(
            maven_case,
            module_name=None,
            report_path=tmp_path / "TEST-M.xml",
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
            failure_logs={},
        )
        assert entry_gradle["identity"] == "com.example.CalculatorTest#testSubtract"
        assert entry_maven["identity"] == "com.example.CalculatorTest#testSubtract"
        assert entry_gradle["identity"] == entry_maven["identity"]

    def test_gradle_failure_log_key_uses_stripped_identity(
        self, tmp_path: Path
    ) -> None:
        """The ``failure_logs`` dict keys MUST also use the stripped
        identity — otherwise downstream consumers (normalizer's
        per-test ``failure_reference`` lookup) miss the log."""

        import xml.etree.ElementTree as ET

        case_xml = (
            '<testcase classname="com.example.CalculatorTest"'
            ' name="testSubtract()" time="0.002">'
            '<failure message="boom" type="AssertionError">stack here</failure>'
            "</testcase>"
        )
        case = ET.fromstring(case_xml)
        failure_logs: dict[str, str] = {}
        _normalize_test_case(
            case,
            module_name=None,
            report_path=tmp_path / "TEST.xml",
            failures_dir=tmp_path / "failures",
            artifact_dir=tmp_path,
            failure_logs=failure_logs,
        )
        # The key uses the stripped form, NOT the original with parens.
        assert "com.example.CalculatorTest#testSubtract" in failure_logs
        assert "com.example.CalculatorTest#testSubtract()" not in failure_logs


# ---------------------------------------------------------------------------
# _strip_trailing_parens (Defect 3 — cross-build-tool identity stability)
# ---------------------------------------------------------------------------


class TestStripTrailingParens:
    def test_maven_style_passthrough(self) -> None:
        assert _strip_trailing_parens("testFoo") == "testFoo"

    def test_gradle_style_stripped(self) -> None:
        assert _strip_trailing_parens("testFoo()") == "testFoo"

    def test_parametrized_signature_preserved(self) -> None:
        """JUnit 5 parametrized tests carry the parameter type list
        inside the display name's parens — that text is NOT a literal
        trailing `()`, so it must be preserved verbatim."""

        assert (
            _strip_trailing_parens("testFoo(int)[1] arg=5")
            == "testFoo(int)[1] arg=5"
        )

    def test_signature_form_preserved(self) -> None:
        """Some Surefire / Gradle plugins emit Java signature in the
        name (`name="testBar(java.lang.String)"`). The signature ends
        with `)` but the name does NOT end with the empty `()` pair,
        so it stays intact."""

        assert (
            _strip_trailing_parens("testBar(java.lang.String)")
            == "testBar(java.lang.String)"
        )

    def test_empty_string_passthrough(self) -> None:
        assert _strip_trailing_parens("") == ""

    def test_bare_double_parens_collapse(self) -> None:
        """Edge: a `name="()"` would strip to empty. Acceptable; an
        empty `name` is already pathological for JUnit XML."""

        assert _strip_trailing_parens("()") == ""


# ---------------------------------------------------------------------------
# _stage_reports_dir + _stage_coverage_xml (Defects 1 + 2 closure)
# ---------------------------------------------------------------------------


class TestStageReportsDir:
    def test_stages_under_artifact_dir(self, tmp_path: Path) -> None:
        """Defect 1 fix: the staged path MUST be a subpath of
        ``artifact_dir`` so the orchestration layer's
        ``.relative_to(store.path)`` rewrite holds. Otherwise the CLI
        envelope hard-fails with `cli-error` on every JUnit run."""

        src = tmp_path / "target" / "surefire-reports"
        src.mkdir(parents=True)
        (src / "TEST-Foo.xml").write_text("<testsuite/>", encoding="utf-8")

        artifact_dir = tmp_path / ".novetest" / "run" / "artifacts" / "run_X"
        staged = _stage_reports_dir(src, artifact_dir=artifact_dir)

        assert staged == artifact_dir / "native" / "reports"
        assert staged.is_relative_to(artifact_dir)
        assert (staged / "TEST-Foo.xml").is_file()
        # Source is untouched (we copy, never move).
        assert (src / "TEST-Foo.xml").is_file()

    def test_multi_module_preserves_module_subpath(self, tmp_path: Path) -> None:
        """Maven multi-module: each module stages under
        ``reports/<module_name>/`` so per-module attribution survives
        on disk."""

        src_a = tmp_path / "module-a" / "target" / "surefire-reports"
        src_a.mkdir(parents=True)
        (src_a / "TEST-A.xml").write_text("<testsuite/>", encoding="utf-8")
        src_b = tmp_path / "module-b" / "target" / "surefire-reports"
        src_b.mkdir(parents=True)
        (src_b / "TEST-B.xml").write_text("<testsuite/>", encoding="utf-8")

        artifact_dir = tmp_path / "art"
        _stage_reports_dir(src_a, artifact_dir=artifact_dir, sub_path="module-a")
        _stage_reports_dir(src_b, artifact_dir=artifact_dir, sub_path="module-b")

        reports_root = artifact_dir / "native" / "reports"
        assert (reports_root / "module-a" / "TEST-A.xml").is_file()
        assert (reports_root / "module-b" / "TEST-B.xml").is_file()

    def test_idempotent_on_retry(self, tmp_path: Path) -> None:
        """Staging twice within the same run (a retry / re-run within
        the same artifact_dir) does not raise — ``dirs_exist_ok=True``
        keeps the helper safe."""

        src = tmp_path / "target" / "surefire-reports"
        src.mkdir(parents=True)
        (src / "TEST-X.xml").write_text("<testsuite/>", encoding="utf-8")

        artifact_dir = tmp_path / "art"
        _stage_reports_dir(src, artifact_dir=artifact_dir)
        # Should not raise.
        staged = _stage_reports_dir(src, artifact_dir=artifact_dir)
        assert (staged / "TEST-X.xml").is_file()


class TestStageCoverageXml:
    def test_canonicalizes_basename_to_jacoco_xml(self, tmp_path: Path) -> None:
        """Gradle emits `jacocoTestReport.xml`; Maven emits `jacoco.xml`.
        Staging collapses both onto the canonical destination basename
        `jacoco.xml` so the Coverage engine's dispatch is uniform."""

        gradle_src = tmp_path / "build" / "reports" / "jacoco" / "test"
        gradle_src.mkdir(parents=True)
        gradle_xml = gradle_src / "jacocoTestReport.xml"
        gradle_xml.write_text(
            "<?xml version='1.0'?><report/>", encoding="utf-8"
        )

        artifact_dir = tmp_path / ".novetest" / "art"
        staged = _stage_coverage_xml(gradle_xml, artifact_dir=artifact_dir)

        assert staged == artifact_dir / "native" / "coverage" / "jacoco.xml"
        assert staged.is_relative_to(artifact_dir)
        assert staged.read_text(encoding="utf-8").startswith("<?xml")

    def test_multi_module_sub_path(self, tmp_path: Path) -> None:
        """Maven multi-module stages each module's XML under
        ``coverage/<module>/jacoco.xml``."""

        src = tmp_path / "module-a" / "target" / "site" / "jacoco" / "jacoco.xml"
        src.parent.mkdir(parents=True)
        src.write_text("<report/>", encoding="utf-8")

        artifact_dir = tmp_path / "art"
        staged = _stage_coverage_xml(
            src, artifact_dir=artifact_dir, sub_path="module-a"
        )

        assert (
            staged
            == artifact_dir / "native" / "coverage" / "module-a" / "jacoco.xml"
        )


# ---------------------------------------------------------------------------
# _summarize_tests + _safe_failure_log_name (mechanical)
# ---------------------------------------------------------------------------


class TestSummarizeTests:
    def test_counts_each_outcome(self) -> None:
        tests = [
            {"status": "passed"},
            {"status": "passed"},
            {"status": "failed"},
            {"status": "skipped"},
            {"status": "errored"},
        ]
        summary = _summarize_tests(tests)
        assert summary == {
            "total": 5,
            "passed": 2,
            "failed": 1,
            "skipped": 1,
            "errored": 1,
        }

    def test_unknown_status_counted_in_total_only(self) -> None:
        tests = [{"status": "unknown"}]
        summary = _summarize_tests(tests)
        assert summary["total"] == 1
        assert summary["passed"] == 0
        assert summary["failed"] == 0


class TestSafeFailureLogName:
    def test_replaces_class_method_separator(self) -> None:
        assert (
            _safe_failure_log_name("com.example.Foo#testBar")
            == "com.example.Foo_testBar"
        )

    def test_strips_parametrized_brackets(self) -> None:
        result = _safe_failure_log_name("X#test[1, foo](int)")
        assert "[" not in result
        assert "]" not in result
        assert "(" not in result
        assert "," not in result

    def test_handles_subtest_slash(self) -> None:
        result = _safe_failure_log_name("X#parent/child")
        assert "/" not in result


# ---------------------------------------------------------------------------
# Module-level smoke against the published surface
# ---------------------------------------------------------------------------


def test_engine_name_constant_pinned() -> None:
    """The literal ``"junit"`` is a downstream-dispatch contract:
    engine.py, derive.py, normalizer.py all match on it. Renaming
    requires updating ALL of them in lockstep."""

    assert junit_adapter.ENGINE_NAME == "junit"


def test_run_junit_raises_when_no_manifest(tmp_path: Path) -> None:
    """`run_junit` is a coroutine; the manifest absence is detected
    synchronously inside the coroutine. Drive it through asyncio."""

    import asyncio

    from novetest.run.errors import AdapterInvocationError
    from novetest.run.types import TestTarget

    target = TestTarget(
        target_expression="",
        target_type="workspace",
        workspace_path=tmp_path,
    )
    artifact_dir = tmp_path / "art"
    with pytest.raises(AdapterInvocationError) as excinfo:
        asyncio.run(
            junit_adapter.run_junit(
                target,
                artifact_dir=artifact_dir,
                timeout=10.0,
                collect_coverage=False,
            )
        )
    assert excinfo.value.kind == "build-tool-undetermined"


# ---------------------------------------------------------------------------
# Defect 2 reopen (hotfix #2 2026-06-04) — coverage argv must keep the
# build alive past the failing-test phase so the JaCoCo report goal /
# task actually runs.
# ---------------------------------------------------------------------------


_MAVEN_POM_WITH_JACOCO = """<?xml version="1.0" encoding="UTF-8"?>
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>x</groupId><artifactId>y</artifactId><version>1</version>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.11</version>
            </plugin>
        </plugins>
    </build>
</project>"""


_GRADLE_BUILD_WITH_JACOCO = """
plugins {
    `java-library`
    jacoco
}
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}
"""


_MINIMAL_SUREFIRE_XML = (
    '<?xml version="1.0"?>'
    '<testsuite name="Sentinel" tests="1" failures="0" errors="0" skipped="0">'
    '<testcase classname="Sentinel" name="probe" time="0.001"/>'
    "</testsuite>"
)


def _seed_maven_workspace(workspace: Path) -> None:
    """Materialize a minimal Maven workspace declaring JaCoCo."""

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pom.xml").write_text(_MAVEN_POM_WITH_JACOCO, encoding="utf-8")


def _seed_gradle_workspace(workspace: Path) -> None:
    """Materialize a minimal Gradle workspace declaring JaCoCo."""

    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "build.gradle.kts").write_text(
        _GRADLE_BUILD_WITH_JACOCO, encoding="utf-8"
    )


def _make_maven_argv_capturing_stub(
    captured_argv: list[list[str]],
    *,
    workspace: Path,
) -> Any:
    """Build an async stub for `run_subprocess` that captures every
    Maven argv invocation and seeds a minimal Surefire XML report so
    the adapter's parser doesn't blow up on the post-run glob.

    Recognizes two version-probe shapes (``mvn -v`` and ``java
    -version``) and returns canonical bytes; the third (main) shape is
    captured and used to seed reports.
    """

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        # `java -version` writes to stderr per Java convention.
        if isinstance(argv, (list, tuple)) and argv[-1] == "-version":
            return SubprocessResult(
                returncode=0,
                stdout=b"",
                stderr=b'openjdk version "17.0.10"\n',
                timed_out=False,
            )
        # `mvn -v` shape: stdout starts with "Apache Maven ...".
        if (
            isinstance(argv, (list, tuple))
            and len(argv) >= 2
            and argv[-1] == "-v"
        ):
            return SubprocessResult(
                returncode=0,
                stdout=b"Apache Maven 3.9.9 (sha) ...\n",
                stderr=b"",
                timed_out=False,
            )
        # Main `mvn -B test ...` invocation. Capture argv and seed a
        # Surefire XML so the post-run parser walks a real directory.
        captured_argv.append(list(argv))
        reports_dir = workspace / "target" / "surefire-reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "TEST-Sentinel.xml").write_text(
            _MINIMAL_SUREFIRE_XML, encoding="utf-8"
        )
        return SubprocessResult(
            returncode=0,
            stdout=b"",
            stderr=b"",
            timed_out=False,
        )

    return stub


def _make_gradle_argv_capturing_stub(
    captured_argv: list[list[str]],
    *,
    workspace: Path,
) -> Any:
    """Same shape as the Maven stub but for the Gradle path."""

    async def stub(
        argv: Any,
        *,
        cwd: Any,
        env: Any | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        if isinstance(argv, (list, tuple)) and argv[-1] == "-version":
            return SubprocessResult(
                returncode=0,
                stdout=b"",
                stderr=b'openjdk version "17.0.10"\n',
                timed_out=False,
            )
        if isinstance(argv, (list, tuple)) and argv[-1] == "--version":
            return SubprocessResult(
                returncode=0,
                stdout=b"Gradle 8.5\n",
                stderr=b"",
                timed_out=False,
            )
        captured_argv.append(list(argv))
        reports_dir = workspace / "build" / "test-results" / "test"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "TEST-Sentinel.xml").write_text(
            _MINIMAL_SUREFIRE_XML, encoding="utf-8"
        )
        return SubprocessResult(
            returncode=0,
            stdout=b"",
            stderr=b"",
            timed_out=False,
        )

    return stub


class TestMavenCoverageArgv:
    """Maven coverage argv must include ``-Dmaven.test.failure.ignore=true``
    *before* the ``jacoco:report`` goal so the report goal runs even
    when Surefire reports failures. Hotfix #2 closure (Defect 2 reopen)."""

    async def test_failure_ignore_flag_present_with_coverage_and_jacoco(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import shutil as _shutil

        workspace = tmp_path / "ws"
        _seed_maven_workspace(workspace)
        captured: list[list[str]] = []
        monkeypatch.setattr(
            junit_adapter,
            "run_subprocess",
            _make_maven_argv_capturing_stub(captured, workspace=workspace),
        )
        monkeypatch.setattr(
            _shutil,
            "which",
            lambda name: f"/fake/{name}",
        )

        target = TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace,
        )
        await junit_adapter.run_junit(
            target,
            artifact_dir=tmp_path / "art",
            timeout=10.0,
            collect_coverage=True,
        )

        assert len(captured) == 1, "stub should have captured one main invocation"
        argv = captured[0]
        assert "-Dmaven.test.failure.ignore=true" in argv
        assert "org.jacoco:jacoco-maven-plugin:report" in argv
        # Ordering matters: the flag must come BEFORE the report goal so
        # Maven has the directive in scope when surefire decides whether
        # to raise.
        idx_flag = argv.index("-Dmaven.test.failure.ignore=true")
        idx_goal = argv.index("org.jacoco:jacoco-maven-plugin:report")
        assert idx_flag < idx_goal, (
            "`-Dmaven.test.failure.ignore=true` MUST precede the JaCoCo "
            "report goal so Surefire's failure handling honors it."
        )

    async def test_failure_ignore_flag_absent_without_coverage(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Non-coverage runs keep their default abort-on-failure
        semantics — the flag must NOT be injected unless we asked for
        coverage."""

        import shutil as _shutil

        workspace = tmp_path / "ws"
        _seed_maven_workspace(workspace)
        captured: list[list[str]] = []
        monkeypatch.setattr(
            junit_adapter,
            "run_subprocess",
            _make_maven_argv_capturing_stub(captured, workspace=workspace),
        )
        monkeypatch.setattr(_shutil, "which", lambda name: f"/fake/{name}")

        target = TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace,
        )
        await junit_adapter.run_junit(
            target,
            artifact_dir=tmp_path / "art",
            timeout=10.0,
            collect_coverage=False,
        )

        assert len(captured) == 1
        argv = captured[0]
        assert "-Dmaven.test.failure.ignore=true" not in argv
        assert "org.jacoco:jacoco-maven-plugin:report" not in argv

    async def test_failure_ignore_flag_absent_when_jacoco_undeclared(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even with `collect_coverage=True`, if the user's pom.xml
        does NOT declare jacoco-maven-plugin, we must not toggle the
        ignore flag (there's no `jacoco:report` goal to run anyway —
        a `missing-jacoco` warning surfaces instead per hotfix #1)."""

        import shutil as _shutil

        workspace = tmp_path / "ws"
        workspace.mkdir(parents=True)
        # JaCoCo deliberately absent from pom.
        (workspace / "pom.xml").write_text(
            """<?xml version="1.0"?>
            <project>
                <modelVersion>4.0.0</modelVersion>
                <groupId>x</groupId><artifactId>y</artifactId><version>1</version>
                <dependencies>
                    <dependency>
                        <groupId>org.junit.jupiter</groupId>
                        <artifactId>junit-jupiter</artifactId>
                        <version>5.10.2</version>
                    </dependency>
                </dependencies>
            </project>""",
            encoding="utf-8",
        )
        captured: list[list[str]] = []
        monkeypatch.setattr(
            junit_adapter,
            "run_subprocess",
            _make_maven_argv_capturing_stub(captured, workspace=workspace),
        )
        monkeypatch.setattr(_shutil, "which", lambda name: f"/fake/{name}")

        target = TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace,
        )
        await junit_adapter.run_junit(
            target,
            artifact_dir=tmp_path / "art",
            timeout=10.0,
            collect_coverage=True,
        )

        assert len(captured) == 1
        argv = captured[0]
        assert "-Dmaven.test.failure.ignore=true" not in argv


class TestGradleCoverageArgv:
    """Gradle coverage argv must include ``--continue`` *before*
    ``jacocoTestReport`` so the task graph keeps running after a
    failing `:test` task and the report task can still execute.
    Hotfix #2 closure (Defect 2 reopen, Gradle side)."""

    async def test_continue_flag_present_with_coverage_and_jacoco(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import shutil as _shutil

        workspace = tmp_path / "ws"
        _seed_gradle_workspace(workspace)
        captured: list[list[str]] = []
        monkeypatch.setattr(
            junit_adapter,
            "run_subprocess",
            _make_gradle_argv_capturing_stub(captured, workspace=workspace),
        )
        # `gradle` resolved off PATH (no `./gradlew` in workspace).
        monkeypatch.setattr(_shutil, "which", lambda name: f"/fake/{name}")

        target = TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace,
        )
        await junit_adapter.run_junit(
            target,
            artifact_dir=tmp_path / "art",
            timeout=10.0,
            collect_coverage=True,
        )

        assert len(captured) == 1
        argv = captured[0]
        assert "--continue" in argv
        assert "jacocoTestReport" in argv
        idx_flag = argv.index("--continue")
        idx_task = argv.index("jacocoTestReport")
        assert idx_flag < idx_task, (
            "`--continue` MUST precede `jacocoTestReport` so Gradle has "
            "the flag in scope when the `:test` task fails."
        )

    async def test_continue_flag_absent_without_coverage(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import shutil as _shutil

        workspace = tmp_path / "ws"
        _seed_gradle_workspace(workspace)
        captured: list[list[str]] = []
        monkeypatch.setattr(
            junit_adapter,
            "run_subprocess",
            _make_gradle_argv_capturing_stub(captured, workspace=workspace),
        )
        monkeypatch.setattr(_shutil, "which", lambda name: f"/fake/{name}")

        target = TestTarget(
            target_expression="",
            target_type="workspace",
            workspace_path=workspace,
        )
        await junit_adapter.run_junit(
            target,
            artifact_dir=tmp_path / "art",
            timeout=10.0,
            collect_coverage=False,
        )

        assert len(captured) == 1
        argv = captured[0]
        assert "--continue" not in argv
        assert "jacocoTestReport" not in argv
