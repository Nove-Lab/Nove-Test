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
    _summarize_tests,
)


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
        # Identity preserves the full display name verbatim.
        assert entry["identity"] == "X#testFoo(int)[1] => 1"


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
