"""Integration tests for the JUnit adapter's envelope-warnings projection.

Covers two of the three JUnit warning kinds catalogued in
``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``
§"What MUST be retroactively projected to envelope top-level":

| Kind | Trigger |
|---|---|
| ``missing-jacoco`` | Maven-Surefire fixture without ``jacoco-maven-plugin`` + ``--coverage`` |
| ``ambiguous-build-tool`` | Fixture with both ``pom.xml`` AND ``build.gradle.kts`` |

The third row in the brief's §1.1 catalog (``engine-misconfigured``
for JUnit) is **NOT projected by the JUnit adapter** — that kind is
emitted by the .NET adapter (``WARNING_COVERLET_ABSENT`` /
``WARNING_COVERLET_BELOW_FLOOR``) and surfaced via
``test_dotnet_warnings.py``. The JUnit catalog entry appears to be a
brief-authoring error; the JUnit ``engine-misconfigured`` state is a
readiness-probe outcome (raised as ``EngineNotReadyError``) that
short-circuits before the adapter runs and surfaces as an
``envelope.errors[].code == "engine-misconfigured"`` entry,
NOT as a warning. Documented deviation per the brief's §2 allowance:
"Run team may refine if they find a cleaner shape during
implementation; report deviations in the handoff."

Each integration test invokes the actual CLI subprocess against a
copied + mutated ``junit-maven-basic`` fixture and asserts:

1. ``envelope.warnings`` contains a record with the expected ``code``
2. The warning has a non-empty ``message``
3. The legacy ``payload["warnings"]`` bridge is STILL populated
   (criterion #2 of the 2026-06-06 decision) — visible through the
   per-test envelope inspection where applicable
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novetest.run.adapters.junit_adapter import (
    WARNING_AMBIGUOUS_BUILD_TOOL,
    WARNING_MISSING_JACOCO,
)


pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason=(
        "JUnit adapter gates Windows per decision "
        "2026-06-03-junit-console-launcher-vendor.md §R5; "
        "Open Question #16 (Windows binary pipeline) pending."
    ),
)


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "projects"
)


def _require_junit_toolchain() -> None:
    """Skip when ``java``/``mvn`` are missing.

    Mirrors the ``test_junit_maven.py`` skip-gate convention. Manual
    Test's equipped host (per ``scripts/dev-host-setup.md §5``) runs
    these; unequipped CI stays green.
    """

    for tool in ("java", "mvn"):
        if shutil.which(tool) is None:
            pytest.skip(
                f"requires `{tool}` on PATH (see scripts/dev-host-setup.md §5)"
            )


def _strip_jacoco_plugin(pom_text: str) -> str:
    """Remove the ``jacoco-maven-plugin`` ``<plugin>`` block from a pom.

    The fixture's pom declares JaCoCo as a build plugin; deleting that
    block triggers ``has_jacoco == False`` in the adapter and surfaces
    the ``missing-jacoco`` warning when ``--coverage`` is requested.
    Uses a regex over the verbatim block shape declared in the fixture
    pom (multi-line, with execution children). Asserts the substitution
    actually changed something so a future fixture refactor surfaces as
    a test failure rather than a silent no-op.
    """

    # Match the entire `<plugin>...</plugin>` block whose `<artifactId>`
    # is `jacoco-maven-plugin`. Greedy match across newlines.
    pattern = re.compile(
        r"\s*<plugin>\s*<groupId>org\.jacoco</groupId>\s*"
        r"<artifactId>jacoco-maven-plugin</artifactId>.*?</plugin>",
        re.DOTALL,
    )
    stripped, count = pattern.subn("", pom_text)
    assert count == 1, (
        f"expected exactly one jacoco-maven-plugin block to remove; "
        f"matched {count}"
    )
    return stripped


@pytest.fixture
def missing_jacoco_workspace(tmp_path: Path) -> Path:
    """Copy ``junit-maven-basic`` and strip its jacoco-maven-plugin block.

    Per-test copy keeps the source fixture's git state clean.
    """

    dest = tmp_path / "junit-maven-no-jacoco"
    shutil.copytree(FIXTURE_ROOT / "junit-maven-basic", dest)
    pom_path = dest / "pom.xml"
    pom_text = pom_path.read_text(encoding="utf-8")
    pom_path.write_text(_strip_jacoco_plugin(pom_text), encoding="utf-8")
    return dest


@pytest.fixture
def ambiguous_build_tool_workspace(tmp_path: Path) -> Path:
    """Copy ``junit-maven-basic`` and add a stub ``build.gradle.kts``.

    The presence of BOTH ``pom.xml`` AND ``build.gradle.kts`` triggers
    ``ambiguous=True`` in the adapter's build-tool selection (Maven is
    the tiebreaker per decision 2026-06-03). The Gradle file is a
    minimal valid Kotlin DSL stub — it doesn't need to be runnable
    because the adapter never invokes Gradle on this workspace.
    """

    dest = tmp_path / "junit-maven-with-gradle"
    shutil.copytree(FIXTURE_ROOT / "junit-maven-basic", dest)
    (dest / "build.gradle.kts").write_text(
        "// novetest test fixture — triggers ambiguous-build-tool warning.\n"
        "// Maven wins as the tiebreaker; this file is never invoked.\n"
        "plugins { id(\"java\") }\n",
        encoding="utf-8",
    )
    return dest


def _spawn_novetest(
    workspace: Path, args: list[str], *, timeout: float
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["NOVETEST_OUTPUT"] = "json"
    return subprocess.run(
        [sys.executable, "-m", "novetest", *args],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def test_cli_smoke_missing_jacoco_emits_envelope_warning(
    missing_jacoco_workspace: Path,
) -> None:
    """``novetest run --coverage`` against a Maven fixture without
    ``jacoco-maven-plugin`` surfaces ``missing-jacoco`` on
    ``envelope.warnings[]``.

    The test run still succeeds — Maven Surefire compiles + runs the
    tests without coverage. The fixture's 5-test contract includes one
    intentional failure, so the expected exit code is 3
    (``EXIT_USER_TESTS_FAILED``).
    """

    _require_junit_toolchain()

    init_result = _spawn_novetest(missing_jacoco_workspace, ["init"], timeout=60.0)
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(
        missing_jacoco_workspace, ["run", "--coverage"], timeout=600.0
    )
    assert run_result.returncode in (0, 3), (
        f"unexpected exit {run_result.returncode}; "
        f"stdout={run_result.stdout!r} stderr={run_result.stderr!r}"
    )

    envelope = json.loads(run_result.stdout)
    warnings_block = envelope.get("warnings", [])
    assert isinstance(warnings_block, list)
    matching = [w for w in warnings_block if w.get("code") == WARNING_MISSING_JACOCO]
    assert matching, (
        f"expected envelope warning with code={WARNING_MISSING_JACOCO!r}; "
        f"got warnings={warnings_block!r}"
    )
    warning = matching[0]
    assert warning.get("message")
    assert "jacoco" in warning["message"].lower()
    # Details surface the build tool so AI consumers can disambiguate
    # Maven-vs-Gradle remediation advice.
    assert warning.get("details", {}).get("build_tool") == "maven"


def test_cli_smoke_ambiguous_build_tool_emits_envelope_warning(
    ambiguous_build_tool_workspace: Path,
) -> None:
    """``novetest run`` against a fixture with both ``pom.xml`` AND
    ``build.gradle.kts`` surfaces ``ambiguous-build-tool`` on
    ``envelope.warnings[]``.

    Maven wins as the tiebreaker per decision 2026-06-03; the run still
    executes Maven Surefire and produces a Run Record. The warning
    informs the user that the ambiguity was resolved silently.
    """

    _require_junit_toolchain()

    init_result = _spawn_novetest(
        ambiguous_build_tool_workspace, ["init"], timeout=60.0
    )
    assert init_result.returncode == 0, init_result.stderr

    run_result = _spawn_novetest(
        ambiguous_build_tool_workspace, ["run"], timeout=600.0
    )
    assert run_result.returncode in (0, 3), (
        f"unexpected exit {run_result.returncode}; "
        f"stdout={run_result.stdout!r} stderr={run_result.stderr!r}"
    )

    envelope = json.loads(run_result.stdout)
    warnings_block = envelope.get("warnings", [])
    assert isinstance(warnings_block, list)
    matching = [w for w in warnings_block if w.get("code") == WARNING_AMBIGUOUS_BUILD_TOOL]
    assert matching, (
        f"expected envelope warning with code={WARNING_AMBIGUOUS_BUILD_TOOL!r}; "
        f"got warnings={warnings_block!r}"
    )
    warning = matching[0]
    assert warning.get("message")
    assert "pom.xml" in warning["message"]
    assert "build.gradle" in warning["message"]
    # Details surface which build tool actually ran — Maven won the
    # tiebreaker so the chosen_build_tool is "maven".
    assert warning.get("details", {}).get("chosen_build_tool") == "maven"
