"""JUnit 5 (Jupiter) Native Engine adapter — Maven Surefire / Gradle paths.

Phase 2.5 fifth-ecosystem slice. Brings ``novetest run`` from
four ecosystems (pytest / jest / gotest / cargo) to five (+ Java). Per
``decisions/2026-06-03-junit-console-launcher-vendor.md`` (Open Q #5
closure) the JUnit Platform Console Launcher is vendored under
``src/novetest/run/adapters/_vendor/`` — the first vendored binary
asset in the project. The adapter itself defers TEST EXECUTION to the
user's existing Maven Surefire / Gradle build (we never modify the
user's manifest); the Console Launcher is reserved for a future
``--list`` discovery path and exercised by the R4 mitigation test
``tests/integration/run/test_junit_vendored_launcher.py``.

Foundations parity with the four prior adapters:

- ``cwd`` is required and MUST be the workspace root containing either
  ``pom.xml`` (Maven) or ``build.gradle{,.kts}`` (Gradle).
- All native artifacts (``stdout.log``, ``stderr.log``, the test-report
  directory snapshot, optional JaCoCo XML) land under
  ``<artifact_dir>/native/``. The orchestration layer rewrites those
  absolute paths to Project-Store-relative strings before persisting the
  Run Record.
- ``collect_coverage=True`` flips the argv: Maven gets an extra goal
  (``org.jacoco:jacoco-maven-plugin:report``); Gradle gets the
  ``jacocoTestReport`` task tacked on. The resulting JaCoCo XML
  registers under the artifact key ``coverage_xml`` — distinct from
  pytest/jest's ``coverage_json``, go-test's ``coverage_profile``, and
  cargo's ``coverage_lcov`` so ``coverage/derive.py`` can dispatch on
  ``engine_name == "junit"`` to a JaCoCo-specific parser.

Build tool selection (per task brief §6 D3):

- Both ``pom.xml`` AND ``build.gradle{,.kts}`` present? Maven wins; a
  ``ambiguous-build-tool`` note lands on ``payload["warnings"]``. The
  user can override the silent default via ``--build-tool=gradle`` in
  a future CLI surface (not in this slice).

Per-test failure logs are written **here**, not in the normalizer —
mirroring the gotest/cargo split. The adapter is the only layer that
holds ``artifact_dir``; the normalizer just consumes the payload's
``failure_logs`` map keyed by ``<classname>#<name>``.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

from novetest.run.errors import AdapterInvocationError
from novetest.run.types import NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess

from ._vendor import LAUNCHER_JAR_SHA256, LAUNCHER_VERSION


STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
FAILURES_DIR_NAME = "failures"

# Per-engine name string. Pinned because the engine_selector,
# normalizer, coverage derive dispatch, and CLI envelope all match on
# the literal. Changing this string would break every downstream
# dispatch table.
ENGINE_NAME: Final[str] = "junit"

# Default timeout — mirrors the prior four adapters' 600 s ceiling.
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 600.0


async def run_junit(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = _DEFAULT_TIMEOUT_SECONDS,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run JUnit 5 tests via the user's Maven or Gradle build.

    Sequence:
    1. Detect build tool (``pom.xml`` → maven; ``build.gradle{,.kts}`` →
       gradle; both → maven with ambiguous-build-tool warning;
       neither → raise ``AdapterInvocationError``).
    2. Dispatch to ``_run_maven`` or ``_run_gradle``. Both branches
       compose argv, ``await asyncio.create_subprocess_exec`` via
       ``run_subprocess``, parse the resulting JUnit XML directory, and
       return a ``NativeResult`` per ``task brief §1.4``.

    The readiness gate (`assess_engine_readiness`) is expected to have
    ALREADY classified the workspace as ``ready`` before this function is
    called. The adapter itself only re-detects the build tool because
    that detail is needed for the argv composition.
    """

    native_dir = artifact_dir / "native"
    native_dir.mkdir(parents=True, exist_ok=True)
    failures_dir = native_dir / FAILURES_DIR_NAME

    workspace = test_target.workspace_path
    has_maven = (workspace / "pom.xml").is_file()
    has_gradle = (
        (workspace / "build.gradle").is_file()
        or (workspace / "build.gradle.kts").is_file()
    )
    if not (has_maven or has_gradle):
        raise AdapterInvocationError(
            "neither `pom.xml` nor `build.gradle{,.kts}` found at "
            f"{workspace}; cannot identify the build tool",
            kind="build-tool-undetermined",
        )

    ambiguous = has_maven and has_gradle
    build_tool: str = "maven" if has_maven else "gradle"

    if build_tool == "maven":
        return await _run_maven(
            test_target,
            artifact_dir=artifact_dir,
            native_dir=native_dir,
            failures_dir=failures_dir,
            timeout=timeout,
            collect_coverage=collect_coverage,
            ambiguous=ambiguous,
        )
    return await _run_gradle(
        test_target,
        artifact_dir=artifact_dir,
        native_dir=native_dir,
        failures_dir=failures_dir,
        timeout=timeout,
        collect_coverage=collect_coverage,
        ambiguous=ambiguous,
    )


# ---------------------------------------------------------------------------
# Build tool detection
# ---------------------------------------------------------------------------


def _detect_build_tool(workspace_path: Path) -> str | None:
    """Return ``"maven"`` / ``"gradle"`` / ``None`` for ``workspace_path``.

    The D3 tiebreaker (both manifest files present → Maven wins) lives
    in ``run_junit`` itself so the warning is surfaced on the payload.
    This helper is pure (and reused by ``readiness._assess_junit_readiness``).
    """

    has_maven = (workspace_path / "pom.xml").is_file()
    if has_maven:
        return "maven"
    has_gradle = (
        (workspace_path / "build.gradle").is_file()
        or (workspace_path / "build.gradle.kts").is_file()
    )
    if has_gradle:
        return "gradle"
    return None


# ---------------------------------------------------------------------------
# Maven path
# ---------------------------------------------------------------------------


async def _run_maven(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    native_dir: Path,
    failures_dir: Path,
    timeout: float | None,
    collect_coverage: bool,
    ambiguous: bool,
) -> NativeResult:
    """Maven Surefire branch.

    ``mvn -B test [-Dtest=<filter>] -Dsurefire.reportFormat=plain
    -Dsurefire.useFile=false [org.jacoco:jacoco-maven-plugin:report]``.

    Reports under ``target/surefire-reports/TEST-*.xml`` (single-module)
    or ``<module>/target/surefire-reports/TEST-*.xml`` (multi-module).
    Coverage XML at ``target/site/jacoco/jacoco.xml`` (single-module) or
    ``<module>/target/site/jacoco/jacoco.xml`` (multi-module).
    """

    mvn_path = shutil.which("mvn")
    if mvn_path is None:
        raise AdapterInvocationError(
            "`mvn` not found on PATH; install Maven 3.9+ "
            "(see scripts/dev-host-setup.md §5)",
            kind="missing-binary",
            install_hint="install Maven 3.9+ per scripts/dev-host-setup.md §5",
        )

    workspace = test_target.workspace_path
    pom_content = _safe_read_text(workspace / "pom.xml")
    has_jacoco = _maven_pom_declares_jacoco(pom_content)
    multi_module_paths = _maven_module_paths(workspace, pom_content)
    multi_module = bool(multi_module_paths)

    argv: list[str] = [
        mvn_path,
        "-B",
        "test",
    ]
    if collect_coverage and has_jacoco:
        # Tell Surefire to REPORT test failures (in the XML and via
        # exit-code-reaching channels) but NOT raise
        # `MojoFailureException`, so Maven continues past the test
        # phase and the `jacoco:report` goal below actually runs.
        # Without this flag, a single failing test aborts the reactor
        # before `target/site/jacoco/jacoco.xml` is ever serialized —
        # the canonical fixture's intentional failure was exactly that
        # case in hotfix #1 (Manual Test 2026-06-04 findings, Defect 2
        # reopen). The user-tests-failed signal is still carried in
        # the Surefire XML the adapter parses for test outcomes and
        # propagates to `EXIT_USER_TESTS_FAILED` correctly. Apply ONLY
        # in coverage runs — non-coverage runs keep their default
        # abort-on-failure semantics.
        argv.append("-Dmaven.test.failure.ignore=true")
        # Append the JaCoCo report goal so the agent dumps XML at
        # `target/site/jacoco/jacoco.xml` after Surefire finishes. The
        # `prepare-agent` goal is wired into the project's `pom.xml` by
        # the user (we never modify it); we only invoke `report` to
        # serialize the in-memory exec data.
        argv.append("org.jacoco:jacoco-maven-plugin:report")
    argv.extend(
        [
            "-Dsurefire.reportFormat=plain",
            "-Dsurefire.useFile=false",
        ]
    )
    if test_target.target_expression:
        argv.append(f"-Dtest={test_target.target_expression}")

    env = _build_child_env()
    started_ms = int(time.time() * 1000)
    try:
        result = await run_subprocess(
            argv,
            cwd=workspace,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        # TOCTOU between `which("mvn")` and the actual exec.
        raise AdapterInvocationError(
            "the `mvn` launcher could not be executed; install Maven 3.9+ "
            "per scripts/dev-host-setup.md §5",
            kind="missing-binary",
            install_hint="install Maven 3.9+ per scripts/dev-host-setup.md §5",
        ) from exc
    completed_ms = int(time.time() * 1000)

    (native_dir / STDOUT_LOG_FILENAME).write_bytes(result.stdout)
    (native_dir / STDERR_LOG_FILENAME).write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"mvn test exceeded {timeout}s timeout",
            kind="timed-out",
        )

    # Glob Surefire report directories. For multi-module projects each
    # module has its own `target/surefire-reports/`; for single-module
    # there's one at the workspace root. Walk both shapes uniformly.
    report_locations: list[tuple[Path, str | None]] = []  # (dir, module_name)
    if multi_module:
        for module_dir in multi_module_paths:
            module_reports = module_dir / "target" / "surefire-reports"
            if module_reports.is_dir():
                report_locations.append((module_reports, module_dir.name))
    else:
        single_reports = workspace / "target" / "surefire-reports"
        if single_reports.is_dir():
            report_locations.append((single_reports, None))

    if not report_locations:
        # No reports produced at all is a hard failure unless mvn itself
        # exited 0 with a "no tests to run" diagnostic — in that case
        # surface as a clean empty run (returncode 0, empty tests list).
        # We tolerate the empty case here; the absence-vs-failure split
        # is decided by the returncode in the normalizer.
        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")
            stdout_text = result.stdout.decode("utf-8", errors="replace")
            detail_source = stderr_text if stderr_text else stdout_text
            raise AdapterInvocationError(
                f"mvn exited {result.returncode} but emitted no Surefire "
                f"reports under target/surefire-reports/; build failure? "
                f"detail tail: {detail_source[-400:]}",
                kind="unparseable-output",
            )

    parsed_tests: list[dict[str, object]] = []
    reports_seen: list[dict[str, object]] = []
    failure_logs: dict[str, str] = {}
    for reports_dir, module_name in report_locations:
        _parse_surefire_reports_dir(
            reports_dir,
            module_name=module_name,
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
        )

    # Coverage glob + per-mode dispatch + stage.
    coverage_xml: Path | None = None
    if collect_coverage:
        if multi_module:
            # Multi-module: stage every per-module XML preserving the
            # module folder. ``coverage_xml`` points at the parent
            # ``coverage/`` directory so D2's per-module glob works at
            # the Coverage engine.
            staged_any = False
            for module_dir in multi_module_paths:
                module_xml = (
                    module_dir / "target" / "site" / "jacoco" / "jacoco.xml"
                )
                if module_xml.is_file():
                    _stage_coverage_xml(
                        module_xml,
                        artifact_dir=artifact_dir,
                        sub_path=module_dir.name,
                    )
                    staged_any = True
            if staged_any:
                coverage_xml = artifact_dir / "native" / "coverage"
        else:
            native_jacoco = workspace / "target" / "site" / "jacoco" / "jacoco.xml"
            if native_jacoco.is_file():
                coverage_xml = _stage_coverage_xml(
                    native_jacoco,
                    artifact_dir=artifact_dir,
                )
        # If `coverage_xml` is still None and the user did NOT declare
        # JaCoCo: degrade gracefully — emit a `missing-jacoco` warning
        # (handled by the warnings block below) and omit
        # `artifact_paths["coverage_xml"]`. The Coverage engine's
        # ``derive_coverage_facts`` then returns a `missing-native-
        # payload` outcome.

    payload_warnings: list[dict[str, str]] = []
    if ambiguous:
        payload_warnings.append(
            {
                "kind": "ambiguous-build-tool",
                "message": (
                    "both pom.xml and build.gradle{,.kts} were detected; "
                    "Maven was chosen as the default tiebreaker per "
                    "decisions/2026-06-03 ratification of brief §6 D3. To "
                    "use Gradle instead, remove the Maven manifest or "
                    "(future) pass --build-tool=gradle."
                ),
            }
        )
    if collect_coverage and not has_jacoco:
        payload_warnings.append(
            {
                "kind": "missing-jacoco",
                "message": (
                    "coverage was requested but the project's pom.xml does "
                    "not declare jacoco-maven-plugin; add the plugin (>= "
                    "0.8.11) under <build><plugins> in pom.xml. Coverage "
                    "data was not collected for this run."
                ),
            }
        )

    payload: dict[str, object] = {
        "build_tool": "maven",
        "build_tool_version": await _read_maven_version(mvn_path, workspace),
        "jupiter_version": _detect_jupiter_version_maven(pom_content),
        "jdk_version": await _read_java_version(workspace),
        "reports": reports_seen,
        "tests": parsed_tests,
        "summary": _summarize_tests(parsed_tests),
        "failure_logs": failure_logs,
        "warnings": payload_warnings,
    }

    artifact_paths: dict[str, Path] = {
        "stdout": native_dir / STDOUT_LOG_FILENAME,
        "stderr": native_dir / STDERR_LOG_FILENAME,
    }
    # Stage the native reports directory under
    # ``artifact_dir/native/reports/`` so ``artifact_paths["reports_dir"]``
    # is a subpath of ``store.path`` — required by the orchestration
    # layer's ``.relative_to(store.path)`` invariant (`workflows/run.py:
    # 85-88`). Sibling adapters (pytest/jest/gotest/cargo) write their
    # native artifacts directly under ``artifact_dir``; Maven writes
    # under ``<workspace>/target/`` so we copy. Multi-module workspaces
    # preserve the per-module folder under ``reports/<module>/`` so
    # downstream attribution survives. The full module-aware list lives
    # on ``payload["reports"]``.
    if report_locations:
        for native_reports, module_name in report_locations:
            _stage_reports_dir(
                native_reports,
                artifact_dir=artifact_dir,
                sub_path=module_name,
            )
        artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"
    if coverage_xml is not None:
        artifact_paths["coverage_xml"] = coverage_xml

    metadata: dict[str, str] = {
        "console_launcher_version": LAUNCHER_VERSION,
        "console_launcher_sha256": LAUNCHER_JAR_SHA256,
        "build_tool": "maven",
        "multi_module": "true" if multi_module else "false",
    }
    if has_jacoco and coverage_xml is not None:
        # Best-effort: surface jacoco-version pin if the user's pom.xml
        # declared an explicit `<version>` for the plugin. Otherwise
        # omit — version detection without a tree-walk over the
        # effective POM is brittle.
        jacoco_version = _detect_jacoco_version_maven(pom_content)
        if jacoco_version is not None:
            metadata["jacoco_version"] = jacoco_version
    surefire_version = _detect_surefire_version_maven(pom_content)
    if surefire_version is not None:
        metadata["surefire_version"] = surefire_version

    return NativeResult(
        engine_name=ENGINE_NAME,
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=_string_or_none(payload.get("jupiter_version")),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Gradle path
# ---------------------------------------------------------------------------


async def _run_gradle(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    native_dir: Path,
    failures_dir: Path,
    timeout: float | None,
    collect_coverage: bool,
    ambiguous: bool,
) -> NativeResult:
    """Gradle branch (wrapper preferred, falls back to ``gradle`` on PATH).

    ``./gradlew test --no-daemon [--tests <filter>] [jacocoTestReport]``.

    Reports at ``build/test-results/test/*.xml``.
    Coverage XML at ``build/reports/jacoco/test/jacocoTestReport.xml``.
    """

    workspace = test_target.workspace_path
    wrapper_path = workspace / "gradlew"
    if wrapper_path.is_file() and os.access(wrapper_path, os.X_OK):
        gradle_invocation: list[str] = [str(wrapper_path)]
    else:
        gradle_bin = shutil.which("gradle")
        if gradle_bin is None:
            raise AdapterInvocationError(
                "no `./gradlew` wrapper in workspace and `gradle` not on "
                "PATH; install Gradle 7.6+ (see scripts/dev-host-setup.md §5) "
                "or commit a Gradle wrapper",
                kind="missing-binary",
                install_hint=(
                    "install Gradle 7.6+ per scripts/dev-host-setup.md §5 or "
                    "commit the Gradle wrapper into the workspace"
                ),
            )
        gradle_invocation = [gradle_bin]

    build_content = _safe_read_text(workspace / "build.gradle")
    if not build_content:
        build_content = _safe_read_text(workspace / "build.gradle.kts")
    has_jacoco = _gradle_declares_jacoco(build_content)

    argv: list[str] = list(gradle_invocation)
    argv.extend(["test", "--no-daemon"])
    if test_target.target_expression:
        argv.extend(["--tests", test_target.target_expression])
    if collect_coverage and has_jacoco:
        # `--continue` tells Gradle to keep running independent tasks
        # even when some fail. `:jacocoTestReport` is independent of
        # `:test`'s pass/fail outcome — it depends on the JaCoCo
        # agent's `jacoco.exec` file, which is produced when `:test`
        # runs the JaCoCo-instrumented JVM regardless of result.
        # Without `--continue`, a single failing test stops the task
        # graph and `:jacocoTestReport` never runs (Manual Test
        # 2026-06-04 findings, Defect 2 reopen). Apply ONLY in
        # coverage runs.
        argv.append("--continue")
        argv.append("jacocoTestReport")

    env = _build_child_env()
    started_ms = int(time.time() * 1000)
    try:
        result = await run_subprocess(
            argv,
            cwd=workspace,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise AdapterInvocationError(
            "the gradle launcher could not be executed; install Gradle 7.6+ "
            "per scripts/dev-host-setup.md §5",
            kind="missing-binary",
            install_hint="install Gradle 7.6+ per scripts/dev-host-setup.md §5",
        ) from exc
    completed_ms = int(time.time() * 1000)

    (native_dir / STDOUT_LOG_FILENAME).write_bytes(result.stdout)
    (native_dir / STDERR_LOG_FILENAME).write_bytes(result.stderr)

    if result.timed_out:
        raise AdapterInvocationError(
            f"gradle test exceeded {timeout}s timeout",
            kind="timed-out",
        )

    reports_dir = workspace / "build" / "test-results" / "test"
    parsed_tests: list[dict[str, object]] = []
    reports_seen: list[dict[str, object]] = []
    failure_logs: dict[str, str] = {}
    if reports_dir.is_dir():
        _parse_surefire_reports_dir(
            reports_dir,
            module_name=None,
            parsed_tests=parsed_tests,
            reports_seen=reports_seen,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
        )
    elif result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        detail_source = stderr_text if stderr_text else stdout_text
        raise AdapterInvocationError(
            f"gradle exited {result.returncode} but emitted no test reports "
            f"under build/test-results/test/; build failure? detail tail: "
            f"{detail_source[-400:]}",
            kind="unparseable-output",
        )

    coverage_xml: Path | None = None
    if collect_coverage:
        candidate = (
            workspace
            / "build"
            / "reports"
            / "jacoco"
            / "test"
            / "jacocoTestReport.xml"
        )
        if candidate.is_file():
            # Gradle's source basename is `jacocoTestReport.xml`; we
            # stage it as the canonical `jacoco.xml` so the Coverage
            # engine has a single dispatch path across build tools.
            coverage_xml = _stage_coverage_xml(
                candidate,
                artifact_dir=artifact_dir,
            )

    payload_warnings: list[dict[str, str]] = []
    if ambiguous:
        payload_warnings.append(
            {
                "kind": "ambiguous-build-tool",
                "message": (
                    "both pom.xml and build.gradle{,.kts} were detected; "
                    "Maven was chosen as the default tiebreaker per brief "
                    "§6 D3 — this Gradle branch should not have been "
                    "reached, but the warning is preserved for audit."
                ),
            }
        )
    if collect_coverage and not has_jacoco:
        payload_warnings.append(
            {
                "kind": "missing-jacoco",
                "message": (
                    "coverage was requested but the project's "
                    "build.gradle{,.kts} does not apply the `jacoco` "
                    "plugin; add `apply plugin: 'jacoco'` (or "
                    "`jacoco {}` in Kotlin DSL). Coverage data was not "
                    "collected for this run."
                ),
            }
        )

    payload: dict[str, object] = {
        "build_tool": "gradle",
        "build_tool_version": await _read_gradle_version(gradle_invocation, workspace),
        "jupiter_version": _detect_jupiter_version_gradle(build_content),
        "jdk_version": await _read_java_version(workspace),
        "reports": reports_seen,
        "tests": parsed_tests,
        "summary": _summarize_tests(parsed_tests),
        "failure_logs": failure_logs,
        "warnings": payload_warnings,
    }

    artifact_paths: dict[str, Path] = {
        "stdout": native_dir / STDOUT_LOG_FILENAME,
        "stderr": native_dir / STDERR_LOG_FILENAME,
    }
    # Stage Gradle's native reports under
    # ``artifact_dir/native/reports/`` so the path satisfies the
    # orchestration layer's ``.relative_to(store.path)`` invariant
    # (`workflows/run.py:85-88`). Gradle writes under
    # ``<workspace>/build/test-results/test/`` which is NOT a subpath
    # of ``store.path`` and would otherwise trigger a `cli-error`.
    if reports_dir.is_dir():
        _stage_reports_dir(reports_dir, artifact_dir=artifact_dir)
        artifact_paths["reports_dir"] = artifact_dir / "native" / "reports"
    if coverage_xml is not None:
        artifact_paths["coverage_xml"] = coverage_xml

    metadata: dict[str, str] = {
        "console_launcher_version": LAUNCHER_VERSION,
        "console_launcher_sha256": LAUNCHER_JAR_SHA256,
        "build_tool": "gradle",
        "multi_module": "false",  # Gradle multi-module support is out-of-scope for v1
    }
    if has_jacoco and coverage_xml is not None:
        jacoco_version = _detect_jacoco_version_gradle(build_content)
        if jacoco_version is not None:
            metadata["jacoco_version"] = jacoco_version

    return NativeResult(
        engine_name=ENGINE_NAME,
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=_string_or_none(payload.get("jupiter_version")),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------


def _parse_surefire_reports_dir(
    reports_dir: Path,
    *,
    module_name: str | None,
    parsed_tests: list[dict[str, object]],
    reports_seen: list[dict[str, object]],
    failure_logs: dict[str, str],
    failures_dir: Path,
    artifact_dir: Path,
) -> None:
    """Append every ``TEST-*.xml`` under ``reports_dir`` into ``parsed_tests``.

    Mutates the caller's lists/dicts in place — matches the gotest/
    cargo adapter pattern of stream-style accumulation. The
    ``module_name`` annotation is preserved on each parsed test so
    multi-module Maven projects retain per-module attribution
    downstream (Localization / Recommendation can cite the module).
    """

    for report_path in sorted(reports_dir.glob("TEST-*.xml")):
        try:
            tree = ET.parse(report_path)
        except ET.ParseError:
            # Defensive: a single malformed report file should not abort
            # the whole adapter. Surface it as a `reports_seen` entry
            # with `format=invalid` so downstream consumers see why a
            # report is missing tests. Matches go-test's resilience
            # posture (per the 2026-05-25 defensive-parsing decision).
            reports_seen.append(
                {
                    "path": str(report_path),
                    "format": "invalid",
                    "module": module_name or "",
                }
            )
            continue
        root = tree.getroot()
        reports_seen.append(
            {
                "path": str(report_path),
                "format": "junit-xml",
                "module": module_name or "",
            }
        )
        # The root is either <testsuite> (Surefire/Gradle classic) or
        # <testsuites> (Surefire 3+ wrapper). Handle both.
        suites = (
            list(root.findall("testsuite")) if root.tag == "testsuites" else [root]
        )
        for suite in suites:
            for case in suite.findall("testcase"):
                test_entry = _normalize_test_case(
                    case,
                    module_name=module_name,
                    report_path=report_path,
                    failures_dir=failures_dir,
                    artifact_dir=artifact_dir,
                    failure_logs=failure_logs,
                )
                parsed_tests.append(test_entry)


def _normalize_test_case(
    case: ET.Element,
    *,
    module_name: str | None,
    report_path: Path,
    failures_dir: Path,
    artifact_dir: Path,
    failure_logs: dict[str, str],
) -> dict[str, object]:
    """Map one ``<testcase>`` element to a payload-shaped dict per brief §1.4.

    Identity is ``<classname>#<name>``. JUnit Platform's ``uniqueId``
    attribute is NOT present in classic Surefire XML; we surface the
    same string under both ``identity`` and ``unique_id`` keys so
    downstream consumers can route on either without branching. If a
    future OTR XML path lands, it will populate ``unique_id`` with the
    richer ``[engine:.../[class:.../[method:...]`` form.
    """

    classname = case.get("classname", "")
    name = _strip_trailing_parens(case.get("name", ""))
    identity = f"{classname}#{name}" if classname else name
    time_attr = case.get("time", "0")
    try:
        duration_ms = int(round(float(time_attr) * 1000))
    except (TypeError, ValueError):
        duration_ms = 0

    failure_el = case.find("failure")
    error_el = case.find("error")
    skipped_el = case.find("skipped")

    status: str
    failure_payload: dict[str, str] | None = None
    if failure_el is not None:
        status = "failed"
        failure_payload = _extract_failure(failure_el)
    elif error_el is not None:
        status = "errored"
        failure_payload = _extract_failure(error_el)
    elif skipped_el is not None:
        status = "skipped"
    else:
        status = "passed"

    stdout_el = case.find("system-out")
    stderr_el = case.find("system-err")
    stdout_text = (stdout_el.text or "") if stdout_el is not None else ""
    stderr_text = (stderr_el.text or "") if stderr_el is not None else ""

    # Per-test failure log file (matches gotest/cargo pattern). Only
    # populated for failed/errored tests; the log captures the
    # failure/error message + stack + system-out + system-err so a
    # consumer (e.g. Localization's failure-proximity mode) can
    # re-read it without the original XML.
    if status in ("failed", "errored") and failure_payload is not None:
        safe_name = _safe_failure_log_name(identity)
        failures_dir.mkdir(parents=True, exist_ok=True)
        failure_path = failures_dir / f"{safe_name}.log"
        log_lines: list[str] = []
        if failure_payload.get("message"):
            log_lines.append(f"[message] {failure_payload['message']}")
        if failure_payload.get("type"):
            log_lines.append(f"[type] {failure_payload['type']}")
        if failure_payload.get("stack"):
            log_lines.append(f"[stack]\n{failure_payload['stack']}")
        if stdout_text:
            log_lines.append(f"[system-out]\n{stdout_text}")
        if stderr_text:
            log_lines.append(f"[system-err]\n{stderr_text}")
        failure_path.write_text("\n".join(log_lines), encoding="utf-8")
        failure_logs[identity] = str(failure_path.relative_to(artifact_dir))

    entry: dict[str, object] = {
        "identity": identity,
        "unique_id": identity,  # OTR upgrade slot — see docstring
        "status": status,
        "duration_ms": duration_ms,
        "failure": failure_payload,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
    if module_name:
        entry["module"] = module_name
    return entry


def _extract_failure(element: ET.Element) -> dict[str, str]:
    """Build the ``{message, type, stack}`` payload from a `<failure>` or
    `<error>` element."""

    return {
        "message": element.get("message", "") or "",
        "type": element.get("type", "") or "",
        "stack": element.text or "",
    }


def _summarize_tests(tests: list[dict[str, object]]) -> dict[str, int]:
    summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errored": 0}
    for entry in tests:
        summary["total"] += 1
        status = entry.get("status")
        if status == "passed":
            summary["passed"] += 1
        elif status == "failed":
            summary["failed"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "errored":
            summary["errored"] += 1
    return summary


def _strip_trailing_parens(name: str) -> str:
    """Normalize a JUnit ``<testcase name>`` attribute across build tools.

    Gradle 8+ (JUnit Platform 1.10+) JUnit XML reports include a literal
    trailing ``()`` for parameterless methods (e.g. ``"testFoo()"``).
    Maven Surefire strips them (emits ``"testFoo"``). We normalize to
    the Maven-canonical no-parens form so ``identity`` is byte-stable
    across build tools — otherwise ``run_record.failed_tests`` diverges
    on the same source between Maven and Gradle, breaking downstream
    Phase 4 (Localization) / Phase 5 (Replay) ``test_id`` lookups.

    ONLY strips a literal trailing ``()`` pair. Parametrized JUnit 5
    display names like ``"testFoo(int)[1] => 1"`` or signature forms
    like ``"testBar(java.lang.String)"`` are preserved verbatim — the
    parens there carry signature information that downstream
    consumers may want to render.
    """

    if name.endswith("()"):
        return name[:-2]
    return name


def _safe_failure_log_name(identity: str) -> str:
    """Map ``<classname>#<name>`` to a filesystem-safe basename.

    Same posture as the gotest adapter: replace path-unfriendly
    characters with ``_`` rather than URL-encode. The substitution set
    covers ``/`` (subtest separators), ``:`` (Windows-illegal),
    ``\\`` (Windows path), ``#`` (the canonical Maven/Gradle separator
    between class and method), ``[`` / ``]`` / ``(`` / ``)`` / ``,``
    (parametrized test display names — JUnit 5's `@ParameterizedTest`
    surfaces these heavily), and whitespace.
    """

    out = identity
    for bad in ("/", ":", "\\", "#", "[", "]", "(", ")", ",", " ", "\t"):
        out = out.replace(bad, "_")
    return out


# ---------------------------------------------------------------------------
# Manifest detection helpers (used by readiness + adapter)
# ---------------------------------------------------------------------------


_JUPITER_MAVEN_RE = re.compile(
    r"<artifactId>\s*junit-jupiter(?:-[a-z]+)?\s*</artifactId>",
    re.IGNORECASE,
)
_JUNIT4_MAVEN_RE = re.compile(
    r"<artifactId>\s*junit\s*</artifactId>\s*"
    r"<version>\s*4\.[\d\.]+",
    re.IGNORECASE | re.DOTALL,
)
_TESTNG_MAVEN_RE = re.compile(
    r"<artifactId>\s*testng\s*</artifactId>",
    re.IGNORECASE,
)
_JACOCO_MAVEN_RE = re.compile(
    r"<artifactId>\s*jacoco-maven-plugin\s*</artifactId>",
    re.IGNORECASE,
)
_SUREFIRE_VERSION_RE = re.compile(
    r"<artifactId>\s*maven-surefire-plugin\s*</artifactId>\s*"
    r"<version>\s*([\d\.]+)\s*</version>",
    re.IGNORECASE | re.DOTALL,
)
_JACOCO_VERSION_MAVEN_RE = re.compile(
    r"<artifactId>\s*jacoco-maven-plugin\s*</artifactId>\s*"
    r"<version>\s*([\d\.]+)\s*</version>",
    re.IGNORECASE | re.DOTALL,
)
_JUPITER_VERSION_MAVEN_RE = re.compile(
    r"<junit\.jupiter\.version>\s*([\d\.]+)\s*</junit\.jupiter\.version>",
    re.IGNORECASE,
)
# Gradle DSL (Groovy + Kotlin both use string literals for coordinates).
_JUPITER_GRADLE_RE = re.compile(
    r"org\.junit\.jupiter[:\s\.]junit-jupiter",
    re.IGNORECASE,
)
_JUNIT4_GRADLE_RE = re.compile(
    r"['\"]junit:junit:4\.",
    re.IGNORECASE,
)
_TESTNG_GRADLE_RE = re.compile(r"['\"]org\.testng:testng", re.IGNORECASE)
_JACOCO_GRADLE_RE = re.compile(
    r"(apply\s+plugin\s*:\s*['\"]jacoco['\"]|"
    r"id\s*\(\s*['\"]jacoco['\"]|"
    r"id\s+['\"]jacoco['\"]|"
    r"jacoco\s*\{|"
    # Bare `jacoco` identifier on its own line — the Kotlin DSL
    # `plugins { java-library; jacoco }` pattern uses this. A line-
    # anchored match (MULTILINE flag) keeps it from over-matching
    # inside string literals or longer identifiers.
    r"^\s*jacoco\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
_JUPITER_VERSION_GRADLE_RE = re.compile(
    r"org\.junit\.jupiter[:.\s]junit-jupiter[^\"']*['\"]\s*[,:]?\s*['\"]?"
    r"([0-9][\d\.]*)",
    re.IGNORECASE,
)


def _safe_read_text(path: Path) -> str:
    """Return ``path``'s text content, or empty string on any error."""

    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _maven_pom_declares_jacoco(pom_content: str) -> bool:
    if not pom_content:
        return False
    return _JACOCO_MAVEN_RE.search(pom_content) is not None


def _maven_module_paths(workspace: Path, pom_content: str) -> list[Path]:
    """Return the directories of `<module>` children declared in ``pom.xml``.

    Empty list for single-module projects. We use a regex rather than
    an XML parse because pom.xml can carry comments / CDATA that
    confuse a naive ``ET.parse`` walk; the regex is targeted and
    cheap, and the brief authorizes manifest-regex for v1 (§5 note).
    """

    if not pom_content:
        return []
    module_re = re.compile(r"<module>\s*([^<\s][^<]*?)\s*</module>", re.IGNORECASE)
    modules: list[Path] = []
    for match in module_re.finditer(pom_content):
        rel = match.group(1).strip()
        if rel:
            candidate = (workspace / rel).resolve()
            if candidate.is_dir():
                modules.append(candidate)
    return modules


def _detects_jupiter_in_manifest(workspace: Path, build_tool: str) -> bool:
    """Return True if the user's manifest declares JUnit Jupiter.

    Used by the readiness probe. Tolerant of both DSLs (Groovy + Kotlin)
    for Gradle; for Maven, accepts any ``junit-jupiter*`` artifactId.
    """

    if build_tool == "maven":
        return _JUPITER_MAVEN_RE.search(_safe_read_text(workspace / "pom.xml")) is not None
    if build_tool == "gradle":
        content = _safe_read_text(workspace / "build.gradle") or _safe_read_text(
            workspace / "build.gradle.kts"
        )
        return _JUPITER_GRADLE_RE.search(content) is not None
    return False


def _detects_junit4_in_manifest(workspace: Path, build_tool: str) -> bool:
    """Return True iff the manifest declares JUnit 4 (artifactId 'junit'
    with version 4.x). Used by readiness to reject JUnit 4 projects with
    a specific message (D5)."""

    if build_tool == "maven":
        return _JUNIT4_MAVEN_RE.search(_safe_read_text(workspace / "pom.xml")) is not None
    if build_tool == "gradle":
        content = _safe_read_text(workspace / "build.gradle") or _safe_read_text(
            workspace / "build.gradle.kts"
        )
        return _JUNIT4_GRADLE_RE.search(content) is not None
    return False


def _detects_testng_in_manifest(workspace: Path, build_tool: str) -> bool:
    """Return True iff the manifest declares TestNG. Readiness uses this
    to surface a `testng-not-supported` warning."""

    if build_tool == "maven":
        return _TESTNG_MAVEN_RE.search(_safe_read_text(workspace / "pom.xml")) is not None
    if build_tool == "gradle":
        content = _safe_read_text(workspace / "build.gradle") or _safe_read_text(
            workspace / "build.gradle.kts"
        )
        return _TESTNG_GRADLE_RE.search(content) is not None
    return False


def _gradle_declares_jacoco(build_content: str) -> bool:
    if not build_content:
        return False
    return _JACOCO_GRADLE_RE.search(build_content) is not None


def _detect_jupiter_version_maven(pom_content: str) -> str | None:
    if not pom_content:
        return None
    match = _JUPITER_VERSION_MAVEN_RE.search(pom_content)
    if match is None:
        # Try inline <version> sibling to junit-jupiter-* artifactId.
        inline = re.search(
            r"<artifactId>\s*junit-jupiter(?:-[a-z]+)?\s*</artifactId>\s*"
            r"<version>\s*([\d\.]+)\s*</version>",
            pom_content,
            re.IGNORECASE | re.DOTALL,
        )
        if inline is None:
            return None
        return inline.group(1)
    return match.group(1)


def _detect_jupiter_version_gradle(build_content: str) -> str | None:
    if not build_content:
        return None
    match = _JUPITER_VERSION_GRADLE_RE.search(build_content)
    return match.group(1) if match else None


def _detect_surefire_version_maven(pom_content: str) -> str | None:
    if not pom_content:
        return None
    match = _SUREFIRE_VERSION_RE.search(pom_content)
    return match.group(1) if match else None


def _detect_jacoco_version_maven(pom_content: str) -> str | None:
    if not pom_content:
        return None
    match = _JACOCO_VERSION_MAVEN_RE.search(pom_content)
    return match.group(1) if match else None


def _detect_jacoco_version_gradle(build_content: str) -> str | None:
    """Gradle does not pin JaCoCo version via the plugin block by default;
    the version comes from the Gradle distribution's bundled tool. We
    return None (informational metadata only)."""

    return None


# ---------------------------------------------------------------------------
# Native-artifact staging (subpath-invariant enforcement)
# ---------------------------------------------------------------------------
#
# Maven Surefire writes JUnit XML under ``<workspace>/target/surefire-
# reports/`` and JaCoCo XML under ``<workspace>/target/site/jacoco/``.
# Gradle writes JUnit XML under ``<workspace>/build/test-results/test/``
# and JaCoCo XML under ``<workspace>/build/reports/jacoco/test/``. None
# of those paths sit under the Project Store (`store.path`), so they
# violate the orchestration layer's ``.relative_to(store.path)``
# invariant (``workflows/run.py:85-88``). We copy the native outputs
# under ``artifact_dir/native/`` so every entry in
# ``NativeResult.artifact_paths`` is a subpath of ``store.path``,
# matching what pytest / jest / gotest / cargo adapters already do.
#
# We copy (`shutil.copytree` / `shutil.copy2`) rather than move so the
# user's source tree is never touched and a retry won't clobber the
# native build dir on the second pass.


def _stage_reports_dir(
    src: Path,
    *,
    artifact_dir: Path,
    sub_path: str | None = None,
) -> Path:
    """Copy ``src`` into ``artifact_dir/native/reports[/<sub_path>]``.

    Returns the staged directory. Existing destination contents are
    removed first so a retry call within the same run produces a clean
    copy (``shutil.copytree`` rejects pre-existing destinations on
    Python < 3.8; ``dirs_exist_ok=True`` is the modern equivalent and
    keeps the helper idempotent within a single run).

    ``sub_path`` is used by Maven multi-module workspaces: every module's
    ``target/surefire-reports/`` lands under
    ``artifact_dir/native/reports/<module>/`` so per-module attribution
    is preserved on disk for downstream readers.
    """

    staged_root = artifact_dir / "native" / "reports"
    dest = staged_root / sub_path if sub_path else staged_root
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return dest


def _stage_coverage_xml(
    src: Path,
    *,
    artifact_dir: Path,
    sub_path: str | None = None,
) -> Path:
    """Copy ``src`` into ``artifact_dir/native/coverage/[<sub_path>/]jacoco.xml``.

    Returns the staged file path. Canonical destination basename is
    ``jacoco.xml`` regardless of the source name — Gradle's source file
    is ``jacocoTestReport.xml`` while Maven's is ``jacoco.xml``; the
    Coverage engine dispatches on the engine name, not the basename, so
    we collapse both onto one canonical name so a future glob over the
    coverage directory has a stable shape.

    ``sub_path`` (e.g. a Maven module name) lands one directory level
    above the file, matching the multi-module D2 contract per
    ``decisions/2026-06-03``.
    """

    staged_dir = artifact_dir / "native" / "coverage"
    if sub_path:
        staged_dir = staged_dir / sub_path
    staged_dir.mkdir(parents=True, exist_ok=True)
    dest = staged_dir / "jacoco.xml"
    shutil.copy2(src, dest)
    return dest


# ---------------------------------------------------------------------------
# Coverage artifact glob (Maven multi-module aware)
# ---------------------------------------------------------------------------


def _glob_jacoco_xml(workspace: Path, multi_module_paths: list[Path]) -> Path | None:
    """Return the JaCoCo XML artifact for the run.

    For a single-module project: ``target/site/jacoco/jacoco.xml``.

    For multi-module: per ``decisions/2026-06-03`` brief §6 D2 we emit
    one CoverageFact PER MODULE downstream — but the ``coverage_xml``
    artifact key on the NativeResult is a single Path. We return the
    FIRST per-module XML found; the Coverage engine's
    `_derive_junit_jacoco` is responsible for re-globbing every module
    XML using the workspace root + `metadata["multi_module"]`.
    """

    if multi_module_paths:
        for module_dir in multi_module_paths:
            candidate = module_dir / "target" / "site" / "jacoco" / "jacoco.xml"
            if candidate.is_file():
                return candidate
        return None
    candidate = workspace / "target" / "site" / "jacoco" / "jacoco.xml"
    return candidate if candidate.is_file() else None


# ---------------------------------------------------------------------------
# Child env + version probes
# ---------------------------------------------------------------------------


def _build_child_env() -> dict[str, str]:
    """Build the subprocess env for ``mvn`` / ``gradle``.

    Mirrors the determinism intent of the prior adapters:
    - ``MAVEN_OPTS=-Dfile.encoding=UTF-8`` keeps Surefire's XML output
      consistent across hosts (Surefire uses the JVM default charset
      for system-out / system-err otherwise — surfaces as garbled
      UTF-8 on platforms where the default is non-UTF-8).
    - ``GRADLE_OPTS=-Dorg.gradle.daemon=false`` is a belt to the
      ``--no-daemon`` suspenders.
    - ``NO_COLOR=1`` strips ANSI escapes from captured logs.
    - JAVA_TOOL_OPTIONS not set; we respect the user's JVM defaults.
    """

    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    # Append rather than overwrite — user may have JVM tuning flags.
    existing_maven = env.get("MAVEN_OPTS", "")
    env["MAVEN_OPTS"] = f"{existing_maven} -Dfile.encoding=UTF-8".strip()
    existing_gradle = env.get("GRADLE_OPTS", "")
    env["GRADLE_OPTS"] = f"{existing_gradle} -Dorg.gradle.daemon=false".strip()
    return env


async def _read_maven_version(mvn_path: str, workspace: Path) -> str | None:
    """Best-effort ``mvn -v`` parse. Returns the bare version
    (e.g. ``"3.9.9"``) or None on any failure."""

    try:
        result = await run_subprocess(
            [mvn_path, "-v"],
            cwd=workspace,
            timeout=15.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace")
    # First line shape: "Apache Maven 3.9.9 (sha) ..."
    match = re.search(r"Apache Maven\s+([\d\.]+)", text)
    return match.group(1) if match else None


async def _read_gradle_version(
    gradle_invocation: list[str], workspace: Path
) -> str | None:
    try:
        result = await run_subprocess(
            [*gradle_invocation, "--version"],
            cwd=workspace,
            timeout=30.0,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"Gradle\s+([\d\.]+)", text)
    return match.group(1) if match else None


async def _read_java_version(workspace: Path) -> str | None:
    """Best-effort ``java -version`` parse. Returns the bare version
    (e.g. ``"17.0.10"``) or None on any failure. ``java -version`` writes
    to stderr (a well-known Java quirk).

    ``workspace`` satisfies `run_subprocess`'s required ``cwd`` — the
    java executable doesn't care about cwd for the version probe, but
    the helper's contract requires one (foundations §3: never inherit
    the CLI's CWD).
    """

    java_path = shutil.which("java")
    if java_path is None:
        return None
    try:
        result = await run_subprocess(
            [java_path, "-version"],
            cwd=workspace,
            timeout=10.0,
        )
    except (OSError, FileNotFoundError):
        return None
    # java -version writes to stderr; some JDK wrappers also dump to
    # stdout. Look at both.
    text = (
        result.stderr.decode("utf-8", errors="replace")
        + "\n"
        + result.stdout.decode("utf-8", errors="replace")
    )
    match = re.search(r'version\s+"([\d\._]+)"', text)
    return match.group(1) if match else None


def _string_or_none(value: object) -> str | None:
    """Type-tightening helper: pass-through if str, else None."""

    return value if isinstance(value, str) else None


__all__ = [
    "ENGINE_NAME",
    "FAILURES_DIR_NAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "_detect_build_tool",
    "_detects_jupiter_in_manifest",
    "_detects_junit4_in_manifest",
    "_detects_testng_in_manifest",
    "run_junit",
]
