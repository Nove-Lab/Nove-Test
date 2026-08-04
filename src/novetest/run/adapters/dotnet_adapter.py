""".NET / xUnit v2 Native Engine adapter — ``dotnet test`` + Coverlet.

Phase 2.5 sixth-and-last-ecosystem slice. Brings ``novetest run`` from
five ecosystems (pytest / jest / gotest / cargo / junit) to six (+ .NET)
and closes the Phase 2.5 native-engine work cleanly: 6/6 native engines
production-ready. Per ``decisions/2026-06-03-coverlet-pertestcoverage-key.md``
this adapter ships:

- xUnit **v2** as the test runner (v3 / Microsoft.Testing.Platform
  detection routes to a ``xunit-v3-coverage-deferred`` warning + a
  no-coverage run; v3 coverage is a separate follow-up slice).
- Coverlet **6.0.2+** as the coverage path via the VSTest XPlat data
  collector (`--collect:"XPlat Code Coverage"`).
- A **per-run hermetic** ``coverlet.runsettings`` at
  ``<artifact_dir>/native/coverlet.runsettings`` (decision §1.1 verbatim
  template) — we never modify the user's ``.csproj`` or ``runsettings``.
- TRX (`results.trx`) as the test-results format (15+ years stable, full
  failure detail + stdout/stderr capture).

Foundations parity with the five prior adapters:

- ``cwd`` is required and MUST be the workspace root of the .NET
  project — the directory holding the ``*.csproj``, or the solution
  root of a ``*.sln`` (multi-csproj + ``*.sln`` workspaces get an
  ``ambiguous-project-layout`` warning + single-test-project
  selection — Maven-style precedent from the JUnit cycle). See
  ``_detect_test_project`` for the discovery and selection rules.
- All native artifacts (``stdout.log``, ``stderr.log``, the TRX file,
  optional Cobertura coverage XML) land under
  ``<artifact_dir>/native/``. The orchestration layer rewrites those
  absolute paths to Project-Store-relative strings before persisting the
  Run Record.
- ``collect_coverage=True`` swaps the argv to add
  ``--collect:"XPlat Code Coverage"`` + ``--settings <runsettings_path>``,
  generates the hermetic runsettings, and registers the Cobertura XML
  under the artifact key ``coverage_xml`` — same key as the JUnit
  adapter (the Coverage engine will dispatch on
  ``engine_name == "xunit"`` to a Cobertura-specific parser; the choice
  to reuse the ``coverage_xml`` key matches the JUnit slice's pattern
  precedent for XML-based coverage formats).

**Empirical finding (2026-06-05)**: ``<PerTestCoverage>true</PerTestCoverage>``
in the XPlat data collector path is **inert in Coverlet 6.0.x** on SDK
8.0 / Linux — only the aggregate ``coverage.cobertura.xml`` is emitted,
never per-test ``coverage.<slug>.cobertura.xml`` files. The runsettings
template still pins ``<PerTestCoverage>true</PerTestCoverage>`` for
forward-compatibility with a future Coverlet release that honors the
gate; the coverage glob prefers per-test first then falls back to
aggregate. ``mapping_granularity`` is derived from the glob's actual
result count, so when (if) per-test starts working downstream, the
adapter automatically promotes the granularity. See
``agent-comms/questions/run-team-2026-06-05-coverlet-pertestcoverage-
empirically-inert.md`` for the diag-log capture.

**Hotfix #1 (2026-06-06)**: Manual Test 2026-06-05 verdict-failed the
initial adapter (commit ``f8f8d93``) because ``_probe_coverlet_version``
ran ``dotnet list <csproj> package --include-transitive --format json``
BEFORE ``dotnet test``. That command requires
``obj/project.assets.json`` (a ``dotnet restore`` artifact), which a
freshly-copied user project does NOT have. The probe returned ``None``,
the adapter treated Coverlet as absent, and ``novetest run --coverage``
silently degraded to a no-coverage run with no envelope-level error.

The fix has three parts:

1. **F1a — pre-restore before probe.** ``_ensure_csproj_restored`` runs
   ``dotnet restore <csproj>`` BEFORE ``_probe_coverlet_version`` on the
   coverage path. ``dotnet restore`` is idempotent (~50-200ms on warm
   cache) and tolerated to non-zero exit (the probe still tries and the
   F1b safety-net fires if it then also fails). Placement is ONLY on
   the coverage path so non-coverage runs pay nothing extra.

2. **F1b — envelope-level visibility via ``NativeResult.warnings``.**
   When ``--coverage`` is requested AND ``_probe_coverlet_version``
   returns ``None`` AFTER restore, the adapter appends a
   ``coverlet-absent`` ``AdapterWarning`` to
   ``NativeResult.warnings``. The orchestration → CLI projection lifts
   it to the envelope's top-level ``warnings`` field at
   ``envelope.warnings[]`` (code + message + structured details). This
   is the canonical post-sunset surface; per the 2026-06-19 amendment
   to ``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``
   the v1 metadata bridge keys have been removed (the one-release-cycle
   backward-compat window closed cleanly with the envelope projection
   already operational). The forensic ``payload["warnings"]`` channel
   is kept for in-process debug; it does NOT propagate to the envelope.

3. **F1c — integration test pins the fresh-fixture reproducer.**
   ``test_coverage_run_on_fresh_fixture_with_no_prior_restore`` in
   ``tests/integration/run/test_dotnet_coverage.py`` explicitly asserts
   the no-``obj/`` precondition and the post-fix
   ``coverlet_version == "6.0.2"`` outcome.

See ``agent-comms/findings/manual-test-team-2026-06-05-phase2.5-dotnet-
adapter.md`` for the D1 reproducer transcript and
``agent-comms/tasks/run-team-2026-06-05-phase2.5-dotnet-adapter-hotfix.md``
for the binding fix shape.

xUnit v3 detection (per decision §6):

- ``<PackageReference Include="xunit" Version="3.*" />`` in the csproj
  → v3 detected → emit ``xunit-v3-coverage-deferred`` warning + run
  tests WITHOUT coverage (omit ``--collect`` and ``--settings`` flags).
  v3 tests still execute + produce TRX so the normal status path holds.

Coverlet floor enforcement (per decision §2 + §5):

- The adapter probes the user's resolved Coverlet version via
  ``dotnet list <csproj> package --include-transitive --format json``
  (preferred path; SDK ≥ 7.0). Fallback to tabular text parsing for
  SDK < 7.0 per decision R3-low (we tolerate line-wrapping).
- Resolved < 6.0.2 → ``coverlet-below-floor`` warning; absent →
  ``coverlet-absent`` warning. Both degrade to the aggregate fallback
  (drops ``<PerTestCoverage>`` element from the runsettings entirely;
  glob is aggregate-only).

The adapter NEVER modifies the user's ``.csproj``, ``runsettings``,
``Directory.Build.props``, or any other build manifest. Hermetic
``runsettings`` go under ``<artifact_dir>/native/`` and are recreated
per run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

from novetest.run.adapters._harness import (
    prepare_artifact_dirs,
    run_and_capture,
    write_failure_log,
)
from novetest.run.errors import AdapterInvocationError
from novetest.run.types import AdapterWarning, NativeResult, TestTarget
from novetest.utils.asyncio_subprocess import run_subprocess


STDOUT_LOG_FILENAME = "stdout.log"
STDERR_LOG_FILENAME = "stderr.log"
FAILURES_DIR_NAME = "failures"
RESULTS_DIR_NAME = "TestResults"
TRX_FILENAME = "results.trx"
RUNSETTINGS_FILENAME = "coverlet.runsettings"

# Failure-log basename extras beyond the shared-harness default
# (Windows-reserved ``<>:"/\|?*`` + whitespace, which already covers
# ``<>:"/\`` and space/tab). xUnit's parametrized display names surface
# ``#`` (defensive, kept symmetric with junit), the ``[](),`` bracket /
# separator set, and ``=`` / ``'`` inside ``TestParametrized(a: 1, b: 2)``
# style names (RUN-06).
_FAILURE_LOG_EXTRA_CHARS: Final[tuple[str, ...]] = (
    "#", "[", "]", "(", ")", ",", "=", "'",
)

# Per-engine name string. Pinned because engine_selector, normalizer,
# coverage derive dispatch, and CLI envelope all match on the literal.
ENGINE_NAME: Final[str] = "xunit"

# Default timeout — mirrors the prior five adapters' 600 s ceiling.
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 600.0

# Coverlet floor — decision §2. Below this we degrade to aggregate mode
# AND emit a ``coverlet-below-floor`` warning so the user can upgrade.
COVERLET_FLOOR_VERSION: Final[tuple[int, int, int]] = (6, 0, 2)

# Warning kinds — surfaced on ``payload["warnings"]``. Treated as binding
# contract by downstream consumers (recommendation synthesis, AI envelopes).
# The two Coverlet kinds carry unique slugs (RUN-07, W2/S15): they used to
# share the literal "engine-misconfigured", colliding with each other AND
# with the readiness-state token of the same name (`run/types.py`
# ``EngineReadinessResult.state``) — a warning taxonomy must never reuse a
# readiness-state string.
WARNING_XUNIT_V3_DEFERRED: Final[str] = "xunit-v3-coverage-deferred"
WARNING_COVERLET_BELOW_FLOOR: Final[str] = "coverlet-below-floor"
WARNING_COVERLET_ABSENT: Final[str] = "coverlet-absent"
WARNING_AMBIGUOUS_PROJECT: Final[str] = "ambiguous-project-layout"

# Coverlet runsettings — decision §1.1 VERBATIM. The
# ``<PerTestCoverage>true</PerTestCoverage>`` element is retained even
# though it is empirically inert in Coverlet 6.0.x via the XPlat data
# collector path (see module docstring) — forward-compat with a future
# Coverlet that honors the gate. ``<SingleHit>false</SingleHit>`` is
# mandatory per decision §"Why <SingleHit>false</SingleHit> is
# mandatory" — without it Coverlet's SingleHit=true default records
# only the first hit per line and produces misleading zero-hit lines.
_COVERLET_RUNSETTINGS_PER_TEST: Final[str] = """\
<?xml version="1.0" encoding="utf-8"?>
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat Code Coverage">
        <Configuration>
          <Format>cobertura,opencover,json,lcov</Format>
          <PerTestCoverage>true</PerTestCoverage>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
"""

# Aggregate variant — drops ``<PerTestCoverage>`` per decision §5. Used
# when Coverlet < 6.0.2 OR absent. ``<SingleHit>false</SingleHit>`` is
# kept because the Localization SBFL formulas want true hit-counts even
# in aggregate mode (the misleading-zero-hits problem the decision
# warns about is per-test-mode-specific BUT keeping the explicit
# ``false`` here costs nothing and keeps the two templates symmetric).
_COVERLET_RUNSETTINGS_AGGREGATE: Final[str] = """\
<?xml version="1.0" encoding="utf-8"?>
<RunSettings>
  <DataCollectionRunSettings>
    <DataCollectors>
      <DataCollector friendlyName="XPlat Code Coverage">
        <Configuration>
          <Format>cobertura,opencover,json,lcov</Format>
          <SingleHit>false</SingleHit>
        </Configuration>
      </DataCollector>
    </DataCollectors>
  </DataCollectionRunSettings>
</RunSettings>
"""


# TRX namespace pinned by Microsoft. ElementTree's `findall(".//ns:tag",
# namespaces={"ns": _TRX_NS})` accepts this mapping; we keep a single
# constant so future TRX schema bumps are a one-line change.
_TRX_NS: Final[str] = "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"

# xUnit v3 detection regex — looks for any ``<PackageReference Include="xunit"
# Version="3.<anything>"`` pattern. Matches Version="3.0.0", "3.*",
# "3.0.0-beta1", "3.0", etc. The trailing partial-match is intentional —
# any 3.x line means v3 regardless of suffix shape.
_XUNIT_V3_PACKAGEREF_RE: Final[re.Pattern[str]] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']xunit[\"'][^>]*"
    r"Version\s*=\s*[\"']3\.",
    re.IGNORECASE,
)

# xUnit v2 detection — any non-3 version line. Used to confirm the
# project IS xunit (vs MSTest/NUnit which we don't support).
_XUNIT_V2_PACKAGEREF_RE: Final[re.Pattern[str]] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']xunit[\"'](?![.])",
    re.IGNORECASE,
)

# Project entry line of the .sln text format (format version 12.00):
#   Project("{<type guid>}") = "<name>", "<relative\path>", "{<guid>}"
# Group 1 is the path slot. Solution folders share this exact shape with
# a label in the path slot, so the caller filters on the ``.csproj``
# suffix + ``is_file()`` instead of on the folder type GUID — see
# ``_csprojs_listed_in_sln``.
_SLN_PROJECT_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^Project\(\"\{[^}]*\}\"\)\s*=\s*\"[^\"]*\"\s*,\s*\"([^\"]+)\"",
    re.MULTILINE,
)

# "This project is a test project" markers. ``Microsoft.NET.Test.Sdk`` is
# the package that makes a project runnable by ``dotnet test`` at all;
# ``<IsTestProject>`` is the property it sets, which templates often
# also spell explicitly. Framework-neutral on purpose — see
# ``_declares_test_project``.
_TEST_PROJECT_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<PackageReference\s+[^>]*Include\s*=\s*[\"']Microsoft\.NET\.Test\.Sdk[\"']"
    r"|<IsTestProject>\s*true\s*</IsTestProject>",
    re.IGNORECASE,
)


async def run_xunit(
    test_target: TestTarget,
    *,
    artifact_dir: Path,
    timeout: float | None = _DEFAULT_TIMEOUT_SECONDS,
    collect_coverage: bool = False,
) -> NativeResult:
    """Run xUnit tests via the user's ``dotnet test`` invocation.

    Sequence:
    1. Detect the test project: ``*.csproj`` at the workspace root, one
       level deep, or listed by a root ``*.sln`` at any depth; when
       several coexist, the self-declared test project wins (see
       ``_detect_test_project``) and an ``ambiguous-project-layout``
       warning is emitted.
    2. Detect xUnit major version from the csproj. v3 → emit
       ``xunit-v3-coverage-deferred`` warning + force coverage off
       (omit ``--collect`` / ``--settings``).
    3. Coverage-mode + xUnit v2: probe the user's resolved Coverlet
       version via ``dotnet list package --include-transitive --format
       json`` (with tabular fallback). Below floor → emit
       ``coverlet-below-floor`` warning; absent → ``coverlet-absent``
       warning. Both degrade to aggregate-mode runsettings.
    4. Generate the hermetic ``coverlet.runsettings`` under
       ``<artifact_dir>/native/`` if coverage requested. Build argv.
    5. Spawn ``dotnet test``. Capture stdout/stderr under
       ``<artifact_dir>/native/``. Parse the TRX results file.
    6. For each failing test extract ``<ErrorInfo><Message/>
       <StackTrace/></ErrorInfo>`` + stdout/stderr capture; write
       failure log under ``<artifact_dir>/native/failures/<slug>.log``.
    7. Glob coverage artifacts: prefer per-test
       (``coverage.*.cobertura.xml``); fall back to aggregate
       (``coverage.cobertura.xml``). Set ``mapping_granularity`` based
       on whether per-test matched.
    8. Assemble ``NativeResult`` with engine_name="xunit",
       engine_version (dotnet --version), summary_counts, status,
       metadata (xunit_version + coverlet_version + native_exit_code
       provenance, etc).

    The readiness gate (``probe_engine`` on the pinned pair) is expected
    to have classified the workspace as ``ready`` BEFORE this function is
    called. The adapter re-detects the project minimally because that
    detail is needed for argv composition.
    """

    # Resolve ``artifact_dir`` + create ``native/`` (shared harness); the
    # resolved runsettings path is later passed as ``--settings`` to
    # ``dotnet test`` so the contract surface stays absolute.
    artifact_dir, native_dir = prepare_artifact_dirs(artifact_dir)

    workspace = test_target.workspace_path
    failures_dir = native_dir / FAILURES_DIR_NAME
    results_dir = native_dir / RESULTS_DIR_NAME

    dotnet_path = shutil.which("dotnet")
    if dotnet_path is None:
        raise AdapterInvocationError(
            "`dotnet` not found on PATH; install .NET SDK 8.0+ "
            "(see scripts/dev-host-setup.md §6)",
            kind="missing-binary",
            install_hint="install .NET SDK 8.0+ per scripts/dev-host-setup.md §6",
        )

    # 1. Project detection.
    chosen_csproj, all_csprojs, all_slns = _detect_test_project(workspace)
    if chosen_csproj is None:
        raise AdapterInvocationError(
            f"no *.csproj found at {workspace}; cannot identify the test project",
            kind="project-not-found",
        )
    csproj_content = _safe_read_text(chosen_csproj)
    is_ambiguous = _is_layout_ambiguous(all_csprojs, all_slns)

    # 2. xUnit version detection.
    xunit_major = _detect_xunit_major_version(csproj_content)
    is_xunit_v3 = xunit_major == 3
    xunit_version = _detect_xunit_resolved_version(csproj_content)

    payload_warnings: list[dict[str, str]] = []
    # Envelope-bound warning surface (2026-06-06 Option C slice). Mirrors
    # every ``payload_warnings`` append below into an ``AdapterWarning``
    # so the orchestration → CLI projection at ``run_cmd`` /
    # ``build_test_envelope`` surfaces each warning on
    # ``envelope.warnings[]``. The two channels are populated in lockstep
    # — backward-compat criterion #2 of the decision file.
    result_warnings: list[AdapterWarning] = []

    if is_ambiguous:
        # Candidates are reported as workspace-relative POSIX paths, not
        # bare filenames: solution walking can surface two projects that
        # share a basename at different depths, and a bare name would
        # make the pair indistinguishable in the envelope.
        candidate_paths = [_workspace_relative(p, workspace) for p in all_csprojs]
        sibling_names = sorted(
            set(candidate_paths) | {_workspace_relative(s, workspace) for s in all_slns}
        )
        ambiguous_msg = (
            f"multiple .csproj / .sln files detected in the "
            f"workspace ({', '.join(sibling_names)}); novetest runs "
            f"one test project per invocation and picked "
            f"'{_workspace_relative(chosen_csproj, workspace)}' "
            f"for v1 — to scope explicitly, pass the project file "
            f"as the run target (e.g. ``novetest run "
            f"MyProject.Tests/MyProject.Tests.csproj``) in a "
            f"future CLI surface"
        )
        payload_warnings.append(
            {"kind": WARNING_AMBIGUOUS_PROJECT, "message": ambiguous_msg}
        )
        result_warnings.append(
            AdapterWarning(
                code=WARNING_AMBIGUOUS_PROJECT,
                message=ambiguous_msg,
                details={
                    "csproj_candidates": candidate_paths,
                    "sln_files": [_workspace_relative(s, workspace) for s in all_slns],
                    "chosen_csproj": _workspace_relative(chosen_csproj, workspace),
                },
            )
        )

    if is_xunit_v3:
        xunit_v3_msg = (
            "xUnit v3 / Microsoft.Testing.Platform coverage is "
            "not yet supported by novetest; falling back to test "
            "execution without coverage"
        )
        payload_warnings.append(
            {"kind": WARNING_XUNIT_V3_DEFERRED, "message": xunit_v3_msg}
        )
        result_warnings.append(
            AdapterWarning(
                code=WARNING_XUNIT_V3_DEFERRED,
                message=xunit_v3_msg,
                details={"xunit_major_version": xunit_major},
            )
        )

    # Deterministic, telemetry-opted-out child env (RUN-18). Built ONCE
    # here so every dotnet subprocess this adapter spawns — the coverage
    # pre-flight (restore / coverlet probe), the main ``dotnet test``, and
    # the SDK-version read — shares the same sanitized env. Passing it to
    # the pre-flight helpers makes the telemetry opt-out / first-run skip /
    # NOLOGO settings apply to the FIRST dotnet call on the coverage path
    # (the restore), not just the main invocation.
    env = _build_child_env()

    # 3. Coverlet version detection (only when coverage requested + xUnit
    # v2). Determines whether to use the per-test template (forward-compat)
    # or the aggregate template (degraded), and surfaces a warning when
    # the user's resolved Coverlet is below floor or absent.
    #
    # Hotfix #1 F1b — envelope-level safety-net for the "probe returned
    # None despite coverage requested" path. The ``AdapterWarning``
    # emitted into ``result_warnings`` below surfaces via the
    # orchestration → CLI projection at ``envelope.warnings[]`` (code +
    # message + structured details). The v1 metadata bridge keys were
    # removed in the 2026-06-19 sunset slice; the envelope warning is
    # now the sole user-visible surface. ``payload["warnings"]`` is
    # kept for forensic continuity but does NOT propagate to the
    # envelope.
    coverlet_version: tuple[int, int, int] | None = None
    coverlet_mode: str = "aggregate"  # "per-test" or "aggregate"; only used when collect_coverage
    if collect_coverage and not is_xunit_v3:
        # Hotfix #1 F1a — Run `dotnet restore <csproj>` BEFORE the
        # Coverlet version probe. The probe uses
        # ``dotnet list package --include-transitive --format json``
        # which requires ``obj/project.assets.json`` (a restore
        # artifact) to enumerate the resolved package graph. On a
        # freshly-copied user project the assets file doesn't exist,
        # the probe returns None, and the adapter falls through to
        # "Coverlet absent" — silently no-op'ing the ``--coverage``
        # flag. This was the verdict-blocking D1 from Manual Test's
        # 2026-06-05 finding.
        #
        # Restore IS idempotent (~50-200ms on warm cache; ~1-3s on cold
        # NuGet cache on first invocation of a fresh fixture). Cost is
        # bounded; always pay it on the coverage path. Non-zero exit is
        # tolerated: if restore fails (e.g. offline + cold cache), the
        # probe still tries (a pre-existing ``obj/`` may carry the
        # assets file from a prior run), and if the probe ALSO fails
        # the F1b safety-net fires so the user sees what went wrong
        # via metadata.
        #
        # Placement: ONLY on the coverage path (guarded by
        # ``collect_coverage and not is_xunit_v3``). Non-coverage runs
        # pay nothing extra. The probe itself shares the same gate, so
        # restore-before-probe is the natural composition.
        await _ensure_csproj_restored(
            dotnet_path, chosen_csproj, workspace, env=env, timeout=timeout
        )
        coverlet_version = await _probe_coverlet_version(
            dotnet_path, chosen_csproj, workspace, env=env, timeout=timeout
        )
        if coverlet_version is None:
            coverlet_absent_msg = (
                "coverage was requested but `coverlet.collector` "
                "is not in the project's package graph; add "
                "<PackageReference Include=\"coverlet.collector\" "
                "Version=\"6.0.2\" /> (or later 6.0.x) to the "
                ".csproj. Coverage data was not collected for "
                "this run."
            )
            payload_warnings.append(
                {"kind": WARNING_COVERLET_ABSENT, "message": coverlet_absent_msg}
            )
            result_warnings.append(
                AdapterWarning(
                    code=WARNING_COVERLET_ABSENT,
                    message=coverlet_absent_msg,
                    details={
                        "csproj": chosen_csproj.name,
                        "coverlet_floor": _format_version(COVERLET_FLOOR_VERSION),
                    },
                )
            )
            # F1b safety-net: the ``AdapterWarning`` appended to
            # ``result_warnings`` above is the sole envelope-bound
            # surface (lifted to ``envelope.warnings[]`` by the
            # orchestration → CLI projection). Triggers ONLY when
            # restore happened (per F1a above) but the probe STILL
            # returned None — i.e. genuine "coverlet.collector not in
            # user's package graph" OR a rarer "restore failed silently
            # AND no prior obj/ existed" case. Both are user-actionable;
            # the warning message names both. The v1 metadata bridge
            # keys were removed by the 2026-06-19 sunset slice — see
            # the 2026-06-19 amendment on
            # ``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``.
        elif coverlet_version < COVERLET_FLOOR_VERSION:
            coverlet_below_msg = (
                f"detected coverlet.collector "
                f"{_format_version(coverlet_version)} is below "
                f"the supported floor "
                f"{_format_version(COVERLET_FLOOR_VERSION)}; "
                f"upgrade for per-test coverage (when Coverlet "
                f"fixes the XPlat data collector pipe). Falling "
                f"back to aggregate-mode runsettings."
            )
            payload_warnings.append(
                {"kind": WARNING_COVERLET_BELOW_FLOOR, "message": coverlet_below_msg}
            )
            result_warnings.append(
                AdapterWarning(
                    code=WARNING_COVERLET_BELOW_FLOOR,
                    message=coverlet_below_msg,
                    details={
                        "csproj": chosen_csproj.name,
                        "detected_coverlet_version": _format_version(
                            coverlet_version
                        ),
                        "coverlet_floor": _format_version(COVERLET_FLOOR_VERSION),
                    },
                )
            )
        else:
            # Coverlet at or above floor — use the per-test template even
            # though the gate is empirically inert today (forward-compat
            # with a future Coverlet release; today's behavior is
            # aggregate-effective, but the runsettings stays per-test).
            coverlet_mode = "per-test"

    # 4. Runsettings generation (coverage runs only).
    runsettings_path: Path | None = None
    if collect_coverage and not is_xunit_v3 and coverlet_version is not None:
        runsettings_path = _generate_runsettings(
            native_dir, mode=coverlet_mode
        )

    # 5. argv composition + subprocess invocation.
    argv = _build_argv(
        dotnet_path=dotnet_path,
        csproj_path=chosen_csproj,
        results_dir=results_dir,
        collect_coverage=(
            collect_coverage and not is_xunit_v3 and coverlet_version is not None
        ),
        runsettings_path=runsettings_path,
        target_expression=test_target.target_expression,
        target_type=test_target.target_type,
    )

    try:
        result, started_ms, completed_ms = await run_and_capture(
            argv,
            cwd=workspace,
            env=env,
            timeout=timeout,
            stdout_path=native_dir / STDOUT_LOG_FILENAME,
            stderr_path=native_dir / STDERR_LOG_FILENAME,
            timeout_label="dotnet test",
        )
    except FileNotFoundError as exc:
        # TOCTOU between `shutil.which("dotnet")` and the actual exec.
        raise AdapterInvocationError(
            "the `dotnet` launcher could not be executed; install .NET "
            "SDK 8.0+ per scripts/dev-host-setup.md §6",
            kind="missing-binary",
            install_hint="install .NET SDK 8.0+ per scripts/dev-host-setup.md §6",
        ) from exc

    # 6. TRX parsing.
    trx_path = results_dir / TRX_FILENAME
    parsed_tests: list[dict[str, object]] = []
    failure_logs: dict[str, str] = {}
    if trx_path.is_file():
        _parse_trx_results(
            trx_path,
            parsed_tests=parsed_tests,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
        )
    elif result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace")
        stdout_text = result.stdout.decode("utf-8", errors="replace")
        detail_source = stderr_text if stderr_text else stdout_text
        raise AdapterInvocationError(
            f"dotnet test exited {result.returncode} but emitted no TRX "
            f"results file at {trx_path}; build failure? detail tail: "
            f"{detail_source[-400:]}",
            kind="unparseable-output",
        )

    # 7. Coverage glob — prefer per-test then fall back to aggregate.
    coverage_xml_artifact: Path | None = None
    coverage_mapping_granularity: str | None = None
    per_test_files: list[Path] = []
    if collect_coverage and not is_xunit_v3 and coverlet_version is not None:
        per_test_files, aggregate_file = _glob_coverage_xml(results_dir)
        if per_test_files:
            # Per-test mode actually produced files (future Coverlet
            # release, or someone patched the XPlat collector). The
            # adapter promotes the granularity automatically. The
            # ``coverage_xml`` artifact key points at the parent
            # directory so a downstream Coverage engine glob finds all
            # of them; ``mapping_granularity`` is ``per-test``.
            coverage_xml_artifact = per_test_files[0].parent
            coverage_mapping_granularity = "per-test"
        elif aggregate_file is not None:
            coverage_xml_artifact = aggregate_file
            coverage_mapping_granularity = "aggregate"

    # 8. NativeResult assembly.
    dotnet_version_str = await _read_dotnet_version(
        dotnet_path, workspace, env=env, timeout=timeout
    )
    summary = _summarize_tests(parsed_tests)
    payload: dict[str, object] = {
        "csproj": str(chosen_csproj.relative_to(workspace))
        if chosen_csproj.is_relative_to(workspace)
        else str(chosen_csproj),
        "xunit_major_version": xunit_major,
        "xunit_version": xunit_version,
        "coverlet_version": _format_version(coverlet_version) if coverlet_version else None,
        "coverage_mode": coverlet_mode if collect_coverage and not is_xunit_v3 else None,
        "tests": parsed_tests,
        "summary": summary,
        "failure_logs": failure_logs,
        "warnings": payload_warnings,
    }

    artifact_paths: dict[str, Path] = {
        "stdout": native_dir / STDOUT_LOG_FILENAME,
        "stderr": native_dir / STDERR_LOG_FILENAME,
    }
    if trx_path.is_file():
        artifact_paths["trx"] = trx_path
    if results_dir.is_dir():
        artifact_paths["results_dir"] = results_dir
    if coverage_xml_artifact is not None:
        artifact_paths["coverage_xml"] = coverage_xml_artifact
    if runsettings_path is not None and runsettings_path.is_file():
        artifact_paths["runsettings"] = runsettings_path

    metadata: dict[str, str] = {}
    if xunit_version:
        metadata["xunit_version"] = xunit_version
    if coverlet_version is not None:
        metadata["coverlet_version"] = _format_version(coverlet_version)
    if coverage_mapping_granularity is not None:
        metadata["coverage_mapping_granularity"] = coverage_mapping_granularity
    metadata["dotnet_sdk_version"] = dotnet_version_str or ""
    # Hotfix #1 F1b's user-visible surface is the ``AdapterWarning`` that
    # the orchestration → CLI projection lifts to ``envelope.warnings[]``
    # (see the emit site above on the ``coverlet_version is None``
    # branch). The v1 metadata bridge keys were removed in the
    # 2026-06-19 sunset slice — they were the one-release-cycle
    # backward-compat bridge introduced by
    # ``decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md``
    # (see the 2026-06-19 amendment). Envelope warnings are now the
    # canonical, single surface.

    return NativeResult(
        engine_name=ENGINE_NAME,
        payload=payload,
        artifact_paths=artifact_paths,
        returncode=result.returncode,
        started_at_ms=started_ms,
        completed_at_ms=completed_ms,
        engine_version=dotnet_version_str,
        metadata=metadata,
        warnings=tuple(result_warnings),
    )


# ---------------------------------------------------------------------------
# Project detection
# ---------------------------------------------------------------------------


def _detect_test_project(
    workspace: Path,
) -> tuple[Path | None, list[Path], list[Path]]:
    """Return ``(chosen, all_csprojs, all_slns)`` for ``workspace``.

    ``chosen`` is None if no ``*.csproj`` was discovered. Otherwise the
    test-project-preferring selection (see below) returns the best
    candidate to keep behavior deterministic across hosts.

    **Discovery** unions two sources:

    1. The workspace root and **one level deep** (``*.csproj`` +
       ``*/*.csproj``) — the canonical library + test split
       (``MathLib/MathLib.csproj`` + ``MathLib.Tests/MathLib.Tests.csproj``).
    2. Every ``*.csproj`` **listed by a root ``*.sln``**, resolved
       relative to the solution file at whatever depth it names.

    Source 2 exists because the depth-1 glob refuses the OTHER canonical
    .NET layout — the one ``dotnet new sln`` conventions produce and
    ``src/Foo/Foo.csproj`` + ``tests/Foo.Tests/Foo.Tests.csproj`` spell.
    Those projects sit at depth **2**, so a solution-rooted workspace
    resolved to no csproj at all and readiness answered
    ``engine-misconfigured`` on a perfectly runnable solution (measured
    on the ``dotnet-expensable`` evaluation seed, 2026-08-04). Walking
    the ``.sln`` is preferred over widening the glob to
    ``src/*/*.csproj`` + ``tests/*/*.csproj`` because the solution file
    is the project list the **user already wrote**: it is exact at any
    depth and under any directory naming, whereas a wider glob only
    guesses two popular directory names and would still refuse
    ``source/``, ``Test/`` or a grouping level. It is also the marker
    that got this workspace detected as .NET in the first place
    (``engine_selector._ENGINE_MARKER_TABLE``'s dotnet row) — the tool
    found the workspace *by* its solution file and then declined to
    read it.

    Solution walking here is **discovery only**. novetest still runs a
    single ``dotnet test <csproj>``; running a whole solution
    (``dotnet test <sln>``, per-project TRX + coverage merge) stays v2
    work per ``design/implementation-plan/engine-adapters.md`` §6.

    **Selection** when multiple ``*.csproj`` are discovered, in order:

    1. Prefer projects that **declare themselves test projects** —
       ``<PackageReference Include="Microsoft.NET.Test.Sdk">`` or
       ``<IsTestProject>true</IsTestProject>``. This tier is
       load-bearing for source 2: a solution routinely also lists
       sample / benchmark / tool / analyzer projects, and some of them
       carry a test-ish *name* (``samples/TestBed/TestBed.csproj``
       sorts BEFORE ``tests/Foo.Tests/Foo.Tests.csproj``), so a
       name-only rule picks the sample and blocks a runnable solution.
       Only ``Microsoft.NET.Test.Sdk`` makes a project runnable by
       ``dotnet test`` at all, which is why it is the discriminator.
       Which *framework* it then declares (xunit vs MSTest / NUnit) is
       readiness's judgment, not discovery's — so this tier stays
       framework-neutral and the MSTest/NUnit diagnostics still name
       the project the user meant.
    2. Within that pool, prefer names containing ``Test`` / ``Tests`` /
       ``Spec`` / ``Specs`` (case-insensitive) — the canonical .NET
       test-project naming conventions.
    3. Otherwise the sort-first candidate (case-insensitive full-path
       sort, so the pick is stable across hosts).

    The returned ``all_csprojs`` is the full list of discovered csprojs
    INCLUDING the chosen one — used by the caller to detect ambiguity.
    Per the rationale above: the library + test split is NOT ambiguous
    (it's the canonical pattern); only the multi-test-project case is.
    The caller does that determination via ``_is_layout_ambiguous``
    below, not in this function.
    """

    all_slns = sorted(workspace.glob("*.sln"), key=lambda p: str(p).lower())
    discovered: set[Path] = set(workspace.glob("*.csproj"))
    discovered.update(workspace.glob("*/*.csproj"))
    for sln_path in all_slns:
        discovered.update(_csprojs_listed_in_sln(sln_path, workspace))
    all_csprojs = sorted(discovered, key=lambda p: str(p).lower())
    if not all_csprojs:
        return None, [], all_slns

    return _pick_test_project(all_csprojs), all_csprojs, all_slns


def _csprojs_listed_in_sln(sln_path: Path, workspace: Path) -> list[Path]:
    """Return the ``*.csproj`` files ``sln_path`` lists, at any depth.

    Every project entry in the (text, format-version-12, 15-year-stable)
    solution format is one line::

        Project("{<type guid>}") = "<name>", "<path>", "{<project guid>}"

    Three quirks of the real format are handled here rather than
    assumed away — all three verified against the ``dotnet-expensable``
    seed's own ``expensable.sln`` before this parser was written:

    - **Paths are Windows-separated** (``tests\\Foo\\Foo.csproj``) even
      in solutions authored on Linux, so ``\\`` is translated before
      the join. Without it, POSIX hosts read the whole thing as one
      absurd filename and match nothing.
    - **Solution folders use the same line shape** — ``= "src", "src",
      "{guid}"`` — with a directory (or a plain label) in the path
      slot. The ``.csproj`` suffix test plus ``is_file()`` drops them,
      which is more robust than matching the folder type GUID.
    - **The file is UTF-8 with a BOM and CRLF line endings**, hence
      ``utf-8-sig``.

    Non-C# project types (``.fsproj`` / ``.vbproj`` / ``.vcxproj``) are
    dropped by the same suffix test: this adapter shells out to
    ``dotnet test`` over C# xUnit only.

    Entries are resolved relative to the solution file and **must stay
    inside the workspace** — a ``..``-escaping entry is skipped, so a
    solution cannot point the run at a project outside the Project
    Store's root. Normalization is lexical (``os.path.normpath``), so
    no symlink is resolved and a symlinked workspace root (pytest's
    ``tmp_path`` on macOS) still compares equal.
    """

    text = _safe_read_text(sln_path, encoding="utf-8-sig")
    listed: list[Path] = []
    for match in _SLN_PROJECT_LINE_RE.finditer(text):
        raw_path = match.group(1).strip().replace("\\", "/")
        if not raw_path.lower().endswith(".csproj"):
            continue
        candidate = Path(os.path.normpath(sln_path.parent / raw_path))
        if not candidate.is_file() or not candidate.is_relative_to(workspace):
            continue
        listed.append(candidate)
    return listed


def _pick_test_project(all_csprojs: list[Path]) -> Path:
    """Choose the one csproj ``dotnet test`` will be pointed at.

    Tiering is documented in ``_detect_test_project``: self-declared
    test projects first, then the test-name token, then sort-first.
    ``all_csprojs`` must be non-empty and already sorted.
    """

    declared = [p for p in all_csprojs if _declares_test_project(_safe_read_text(p))]
    pool = declared or all_csprojs
    test_named = [p for p in pool if _has_test_name_token(p)]
    return test_named[0] if test_named else pool[0]


def _declares_test_project(csproj_content: str) -> bool:
    """Return True iff the csproj declares itself runnable by ``dotnet test``.

    ``Microsoft.NET.Test.Sdk`` is what actually makes a project a test
    project to the .NET SDK (every ``dotnet new xunit`` / ``nunit`` /
    ``mstest`` template references it); ``<IsTestProject>true</...>`` is
    the property that reference sets, and templates frequently spell it
    explicitly too. Either is accepted — deliberately framework-neutral
    (see ``_detect_test_project`` selection tier 1).
    """

    return bool(csproj_content) and _TEST_PROJECT_MARKER_RE.search(csproj_content) is not None


def _has_test_name_token(csproj_path: Path) -> bool:
    """Return True iff the csproj filename carries a test-project token."""

    name = csproj_path.name.lower()
    return any(token in name for token in ("tests", "test", "specs", "spec"))


def _workspace_relative(path: Path, workspace: Path) -> str:
    """Render ``path`` for an envelope: workspace-relative, POSIX form.

    POSIX separators are load-bearing for the same reason they are in
    ``engine_selector._marker_evidence``: these strings reach AI agents
    through the envelope, so one workspace must serialize identically on
    Windows and POSIX hosts. Falls back to the absolute path for the
    (unreachable-by-construction, since ``_csprojs_listed_in_sln``
    enforces containment) out-of-workspace case.
    """

    if path.is_relative_to(workspace):
        return path.relative_to(workspace).as_posix()
    return path.as_posix()


def _is_layout_ambiguous(
    all_csprojs: list[Path], all_slns: list[Path]
) -> bool:
    """Return True iff the discovered layout warrants an
    ``ambiguous-project-layout`` warning.

    The canonical .NET library + test split (``MyLib/MyLib.csproj`` +
    ``MyLib.Tests/MyLib.Tests.csproj`` at workspace root) is NOT
    ambiguous — that's the recommended pattern for any non-trivial
    .NET project. We only warn when:

    1. **Multiple test-named csprojs** are present (e.g.
       ``MyLib.Tests/`` + ``MyLib.Integration.Tests/``). The adapter
       picks one, but the user might have meant the other; surface the
       ambiguity.
    2. A ``*.sln`` is present alongside the csprojs. A solution builds
       and tests **several** projects; novetest runs exactly one
       ``dotnet test <csproj>`` per invocation, so the warning tells
       the user which project of theirs the run actually covered.
       (Before solution walking landed the reason was different — the
       one-level glob could not *see* solution-listed projects at all.
       It now sees them; what remains is that only one of them runs.)

    Pure library/test split (1 test csproj + N non-test csprojs at
    one level deep, no .sln) is the silent happy path — no warning.
    """

    if all_slns:
        return True
    return len([p for p in all_csprojs if _has_test_name_token(p)]) > 1


# ---------------------------------------------------------------------------
# xUnit version detection (from csproj content)
# ---------------------------------------------------------------------------


def _detect_xunit_major_version(csproj_content: str) -> int:
    """Return ``2`` / ``3`` / ``0`` for the user's xunit major version.

    ``0`` means no xunit ``<PackageReference>`` found at all (could be
    MSTest / NUnit / something else). The readiness probe is supposed to
    catch this earlier; the adapter defaults to v2 behavior at the
    argv layer so a misconfigured workspace produces a clean
    ``unparseable-output`` (no TRX) rather than crashing.
    """

    if not csproj_content:
        return 0
    if _XUNIT_V3_PACKAGEREF_RE.search(csproj_content) is not None:
        return 3
    if _XUNIT_V2_PACKAGEREF_RE.search(csproj_content) is not None:
        return 2
    return 0


def _detect_xunit_resolved_version(csproj_content: str) -> str | None:
    """Return the literal Version="..." string for xunit, or None.

    Best-effort metadata pin. Used by ``payload["xunit_version"]`` and
    ``metadata["xunit_version"]``.
    """

    if not csproj_content:
        return None
    match = re.search(
        r"<PackageReference\s+[^>]*Include\s*=\s*[\"']xunit[\"'](?![.])[^>]*"
        r"Version\s*=\s*[\"']([^\"']+)[\"']",
        csproj_content,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Project restore (hotfix #1 F1a — 2026-06-06)
# ---------------------------------------------------------------------------


def _clamp_preflight_timeout(
    default_budget: float, caller_timeout: float | None
) -> float:
    """Cap a coverage pre-flight subprocess budget by the caller's timeout.

    RUN-08: ``run_xunit``'s ``timeout`` governs the whole invocation, but
    the coverage pre-flight subprocesses (restore / coverlet probe / SDK
    version) historically used fixed budgets (300 / 30 / 10 s) that could
    each dwarf a small caller timeout — a cold-cache ``dotnet restore``
    alone could block up to 300 s despite a caller asking for 30 s. Clamp
    every pre-flight budget to ``min(default, caller)`` so no single
    pre-flight step can exceed the caller's contract. ``caller_timeout is
    None`` (no bound) keeps the historical default.
    """

    if caller_timeout is None:
        return default_budget
    return min(default_budget, caller_timeout)


async def _ensure_csproj_restored(
    dotnet_path: str,
    csproj_path: Path,
    workspace: Path,
    *,
    env: dict[str, str],
    timeout: float | None,
) -> None:
    """Run ``dotnet restore <csproj>`` to materialize ``obj/project.assets.json``.

    Called by ``run_xunit`` on the coverage path BEFORE
    ``_probe_coverlet_version``. The probe (``dotnet list <csproj>
    package --include-transitive --format json``) requires the assets
    file to enumerate the resolved package graph; on a freshly-copied
    user project the assets file doesn't exist and the probe silently
    returns ``None``, which the adapter then misreads as "Coverlet
    absent". That was Manual Test 2026-06-05 D1 — the verdict-blocking
    defect this hotfix closes.

    Restore IS idempotent:
    - Warm cache + already-restored: ~50-200 ms (file-stamp comparison)
    - Cold NuGet cache, fresh fixture: ~1-3 s on first invocation
    - Subsequent invocations of the same fixture: ~50-200 ms

    Non-zero exit is tolerated rather than raised — callers (the F1b
    safety-net + the existing ``coverlet-absent`` warning) will
    surface a structured user-facing message if the probe ALSO returns
    None after a failed restore. Pre-existing ``obj/`` from a prior
    ``dotnet test`` may still satisfy the probe even when today's
    restore fails (e.g. offline + cold cache); we want to give that
    path a chance to succeed before degrading to no-coverage.

    The 300-second default matches the upper bound for a cold NuGet
    cache pulling all of xunit + Microsoft.NET.Test.Sdk + coverlet.collector
    on a slow connection. Restore should never take longer than this
    in practice; the budget is a safety belt rather than an expected
    latency budget. RUN-08: the default is clamped to the caller's
    ``timeout`` (``min(300, caller)``) so a small caller budget is not
    silently blown by a slow restore; ``timeout=None`` keeps the 300 s
    default. ``env`` carries the sanitized child env (RUN-18) so the
    telemetry opt-out / first-run skip applies to this FIRST dotnet call
    on the coverage path.

    A ``FileNotFoundError`` during exec (TOCTOU after
    ``shutil.which`` resolved earlier in ``run_xunit``) is allowed to
    propagate — the caller will then re-encounter the same condition
    when spawning ``dotnet test`` itself, mapping to the canonical
    ``missing-binary`` AdapterInvocationError there. Doing the same
    here would duplicate the error-shape construction; one source of
    truth is cleaner.
    """

    await run_subprocess(
        [dotnet_path, "restore", str(csproj_path)],
        cwd=workspace,
        env=env,
        timeout=_clamp_preflight_timeout(300.0, timeout),
    )


# ---------------------------------------------------------------------------
# Coverlet version detection (probe via ``dotnet list package``)
# ---------------------------------------------------------------------------


async def _probe_coverlet_version(
    dotnet_path: str,
    csproj_path: Path,
    workspace: Path,
    *,
    env: dict[str, str],
    timeout: float | None,
) -> tuple[int, int, int] | None:
    """Probe the user's resolved ``coverlet.collector`` version.

    Sequence per decision §4 + R3-low:
    1. Try ``dotnet list <csproj> package --include-transitive --format
       json`` (SDK ≥ 7.0). Parse the JSON; pluck ``resolvedVersion`` for
       ``id == "coverlet.collector"`` across both ``topLevelPackages`` and
       ``transitivePackages``.
    2. On JSON-format failure, fall back to tabular text. Tolerate
       line-wrapping (Windows terminals + narrow consoles).
    3. Return parsed ``(major, minor, patch)`` tuple, or None if not
       found in the package graph.

    RUN-08: each probe's 30 s budget is clamped to the caller's ``timeout``
    (``min(30, caller)``). RUN-18: ``env`` is the sanitized child env.
    """

    probe_timeout = _clamp_preflight_timeout(30.0, timeout)
    # Path 1: JSON format.
    json_result = await run_subprocess(
        [dotnet_path, "list", str(csproj_path), "package",
         "--include-transitive", "--format", "json"],
        cwd=workspace,
        env=env,
        timeout=probe_timeout,
    )
    if json_result.returncode == 0:
        version = _parse_coverlet_version_from_json(json_result.stdout)
        if version is not None:
            return version

    # Path 2: tabular fallback.
    text_result = await run_subprocess(
        [dotnet_path, "list", str(csproj_path), "package",
         "--include-transitive"],
        cwd=workspace,
        env=env,
        timeout=probe_timeout,
    )
    if text_result.returncode == 0:
        return _parse_coverlet_version_from_text(
            text_result.stdout.decode("utf-8", errors="replace")
        )

    return None


def _parse_coverlet_version_from_json(stdout_bytes: bytes) -> tuple[int, int, int] | None:
    """Parse ``dotnet list package --format json`` output for coverlet.collector.

    Schema (SDK 8.0; stable since SDK 7.0):
    ``{"version": 1, "parameters": "...", "projects": [
       {"path": "...", "frameworks": [
         {"framework": "net8.0",
          "topLevelPackages": [{"id", "requestedVersion", "resolvedVersion"}, ...],
          "transitivePackages": [{"id", "resolvedVersion"}, ...]
         }, ...]
       }, ...]}``
    """

    try:
        payload = json.loads(stdout_bytes.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    projects = payload.get("projects")
    if not isinstance(projects, list):
        return None
    for project in projects:
        if not isinstance(project, dict):
            continue
        frameworks = project.get("frameworks")
        if not isinstance(frameworks, list):
            continue
        for framework in frameworks:
            if not isinstance(framework, dict):
                continue
            for kind in ("topLevelPackages", "transitivePackages"):
                packages = framework.get(kind)
                if not isinstance(packages, list):
                    continue
                for pkg in packages:
                    if not isinstance(pkg, dict):
                        continue
                    if pkg.get("id") != "coverlet.collector":
                        continue
                    version_str = pkg.get("resolvedVersion")
                    if not isinstance(version_str, str):
                        continue
                    parsed = _parse_semver(version_str)
                    if parsed is not None:
                        return parsed
    return None


def _parse_coverlet_version_from_text(stdout_text: str) -> tuple[int, int, int] | None:
    """Parse ``dotnet list package`` tabular output for coverlet.collector.

    Output shape (SDK 6.0 ish, no ``--format`` flag):

    ```
       Top-level Package      Requested   Resolved
       > coverlet.collector   6.0.2       6.0.2

       Transitive Package                          Resolved
       > Microsoft.CodeCoverage                    17.8.0
    ```

    Tolerates line-wrapping by accepting any ``coverlet.collector``
    followed-by-whitespace followed-by version-shape token, regardless
    of column alignment. The first match wins (topLevelPackages comes
    before transitivePackages in the output so this prefers the
    top-level resolved version, matching JSON's preference order).
    """

    if not stdout_text:
        return None
    # Match ``coverlet.collector`` followed by whitespace and then either
    # a ``Requested  Resolved`` pair (top-level) or just a ``Resolved``
    # version (transitive). Prefer the rightmost version token in each
    # match: it is always the resolved version (Requested is to its
    # left in top-level, absent in transitive).
    pattern = re.compile(
        r"coverlet\.collector"
        r"\s+(?:[\d.]+\s+)?"  # optional Requested column
        r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)",
        re.IGNORECASE,
    )
    match = pattern.search(stdout_text)
    if match is None:
        return None
    return _parse_semver(match.group(1))


def _parse_semver(version_str: str) -> tuple[int, int, int] | None:
    """Parse ``"6.0.2"`` / ``"6.0.2-beta1"`` / ``"6.0.2+abc"`` → ``(6, 0, 2)``.

    Pre-release / build metadata suffixes are ignored — version comparison
    against the floor uses the base semver triple only.
    """

    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if match is None:
        return None
    try:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    except ValueError:
        return None


def _format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


# ---------------------------------------------------------------------------
# Runsettings generation
# ---------------------------------------------------------------------------


def _generate_runsettings(native_dir: Path, *, mode: str) -> Path:
    """Write the hermetic ``coverlet.runsettings`` for this run.

    Always under ``<native_dir>/coverlet.runsettings`` so the file lives
    in the same subtree as stdout.log / stderr.log / TRX and survives
    postmortem inspection. The per-run hermetic placement also means
    the user's existing ``coverlet.runsettings`` (if any) is NEVER
    overwritten — strict respect for the non-modification contract.

    ``mode`` is ``"per-test"`` or ``"aggregate"``; the template choice
    is documented in the module docstring.
    """

    runsettings_path = native_dir / RUNSETTINGS_FILENAME
    template = (
        _COVERLET_RUNSETTINGS_PER_TEST
        if mode == "per-test"
        else _COVERLET_RUNSETTINGS_AGGREGATE
    )
    runsettings_path.write_text(template, encoding="utf-8")
    return runsettings_path


# ---------------------------------------------------------------------------
# argv composition
# ---------------------------------------------------------------------------


def _build_argv(
    *,
    dotnet_path: str,
    csproj_path: Path,
    results_dir: Path,
    collect_coverage: bool,
    runsettings_path: Path | None,
    target_expression: str,
    target_type: str,
) -> list[str]:
    """Compose the ``dotnet test`` argv for a run.

    Base shape (always):
    ``dotnet test <csproj> --logger "trx;LogFileName=results.trx"
    --results-directory <results_dir>``

    With coverage (xUnit v2 + Coverlet >= 6.0.2):
    ``+ --collect:"XPlat Code Coverage" --settings <runsettings>``

    With non-directory non-empty target_expression:
    ``+ --filter "FullyQualifiedName~<target_expression>"``

    Target-type handling mirrors cargo Fix A (2026-06-05 cargo CLI
    orchestration defect closure) — ``target_type="directory"`` (the
    ``novetest run .`` case) does NOT inject a ``--filter`` argument
    because ``--filter`` is xUnit's discovery expression language, not
    a filesystem path. ``--filter`` is only added when the user typed
    something more specific than a directory.
    """

    argv: list[str] = [
        dotnet_path,
        "test",
        str(csproj_path),
        "--logger",
        f"trx;LogFileName={TRX_FILENAME}",
        "--results-directory",
        str(results_dir),
    ]
    if collect_coverage:
        argv.append("--collect:XPlat Code Coverage")
        if runsettings_path is not None:
            argv.extend(["--settings", str(runsettings_path)])
    if target_expression and target_type != "directory":
        # Use the ``~`` (contains) operator: more forgiving than ``=`` for
        # users who type a partial path like ``MathTests.TestAddPasses``
        # without the full namespace. The user can opt into exact match
        # by passing the FQN — xUnit's filter DSL `~` becomes redundant
        # but harmless on full matches.
        argv.append(f"--filter")
        argv.append(f"FullyQualifiedName~{target_expression}")
    return argv


# ---------------------------------------------------------------------------
# Child env
# ---------------------------------------------------------------------------


def _build_child_env() -> dict[str, str]:
    """Build the subprocess env for ``dotnet test``.

    Mirrors the determinism intent of the prior five adapters:
    - ``DOTNET_NOLOGO=1`` strips the "Welcome to .NET" banner.
    - ``DOTNET_CLI_TELEMETRY_OPTOUT=1`` opts out of telemetry — silences
      the first-run notice and respects user privacy by default.
    - ``DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1`` skips the first-run NuGet
      cache population (we never use it; saves ~5s on cold runs).
    - ``NO_COLOR=1`` strips ANSI escapes from VSTest's diagnostics.
    - ``MSBUILDTERMINALLOGGER=off`` disables MSBuild's 17.8+ terminal
      logger (which prints progress bars that break TRX correlation in
      pipelined CI logs).

    Notably absent:
    - NO ``DOTNET_ROOT`` override — we honor the user's already-resolved
      SDK location.
    - NO ``DOTNET_GENERATE_ASPNET_CERTIFICATE=false`` — irrelevant to
      test runs.
    """

    env = os.environ.copy()
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
    env["NO_COLOR"] = "1"
    env["MSBUILDTERMINALLOGGER"] = "off"
    return env


# ---------------------------------------------------------------------------
# TRX parsing
# ---------------------------------------------------------------------------


def _parse_trx_results(
    trx_path: Path,
    *,
    parsed_tests: list[dict[str, object]],
    failure_logs: dict[str, str],
    failures_dir: Path,
    artifact_dir: Path,
) -> None:
    """Walk ``trx_path`` and append normalized test entries to
    ``parsed_tests``.

    Mutates in place to match the gotest / cargo / junit adapter
    pattern. TRX is XML; the namespace is the canonical Microsoft
    schema (`_TRX_NS`). Outcomes encountered:

    | TRX `outcome` attribute | Normalized status |
    |---|---|
    | "Passed" | "passed" |
    | "Failed" | "failed" |
    | "NotExecuted" / "Skipped" | "skipped" |
    | "Inconclusive" | "skipped" (safer default per task brief §6.2) |
    | "Aborted" / "Error" / "Timeout" | "errored" (safer default per §6.2) |
    | anything else | "errored" (defensive default per
    |                | decisions/2026-05-25-supported-engine-matrix.md §2) |

    Resilient to malformed TRX: a parse error is surfaced via a
    raise-once-with-context message rather than a silent empty list,
    because TRX parsing failure is much more likely to be a tooling
    issue than a transient malformed line.
    """

    try:
        tree = ET.parse(trx_path)
    except ET.ParseError as exc:
        raise AdapterInvocationError(
            f"TRX file at {trx_path} is malformed: {exc!s}",
            kind="unparseable-output",
        ) from exc

    root = tree.getroot()
    ns_map = {"vs": _TRX_NS}

    # Build a testId → testName lookup from <TestDefinitions> so the
    # parametrized test entries (which use TRX's expanded display name
    # in the testName attribute of UnitTestResult) round-trip cleanly.
    # Mirror UnitTest <-> UnitTestResult by testId. Falls back to using
    # UnitTestResult's testName attribute when the cross-reference fails.
    test_method_by_id: dict[str, dict[str, str]] = {}
    for ut in root.findall(".//vs:TestDefinitions/vs:UnitTest", ns_map):
        test_id = ut.get("id", "")
        method = ut.find("vs:TestMethod", ns_map)
        if not test_id or method is None:
            continue
        test_method_by_id[test_id] = {
            "className": method.get("className", "") or "",
            "name": method.get("name", "") or "",
            "adapterTypeName": method.get("adapterTypeName", "") or "",
        }

    for utr in root.findall(".//vs:Results/vs:UnitTestResult", ns_map):
        entry = _normalize_unit_test_result(
            utr,
            ns_map=ns_map,
            test_method_by_id=test_method_by_id,
            failure_logs=failure_logs,
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
        )
        parsed_tests.append(entry)


def _normalize_unit_test_result(
    utr: ET.Element,
    *,
    ns_map: dict[str, str],
    test_method_by_id: dict[str, dict[str, str]],
    failure_logs: dict[str, str],
    failures_dir: Path,
    artifact_dir: Path,
) -> dict[str, object]:
    """Map one ``<UnitTestResult>`` element to a payload-shaped dict."""

    test_name = utr.get("testName", "") or ""
    test_id = utr.get("testId", "") or ""
    outcome_raw = utr.get("outcome", "") or ""
    duration_attr = utr.get("duration", "0") or "0"
    duration_ms = _parse_trx_duration_ms(duration_attr)

    status = _trx_outcome_to_status(outcome_raw)

    # Identity is the testName (which xUnit emits as the fully-qualified
    # name including parametrized data — e.g. "MathLib.Tests.MathTests
    # .TestParametrized(a: 1, b: 2, expected: 3)"). Preserve this
    # verbatim because Replay / Regression / Localization keys depend
    # on byte-stable identities.
    identity = test_name
    method_info = test_method_by_id.get(test_id, {})
    class_name = method_info.get("className", "")
    method_name = method_info.get("name", "")

    # Failure detail capture for failed/errored statuses.
    failure_payload: dict[str, str] | None = None
    stdout_text = ""
    stderr_text = ""
    output_el = utr.find("vs:Output", ns_map)
    if output_el is not None:
        err_info = output_el.find("vs:ErrorInfo", ns_map)
        if err_info is not None:
            message_el = err_info.find("vs:Message", ns_map)
            stack_el = err_info.find("vs:StackTrace", ns_map)
            failure_payload = {
                "message": (message_el.text or "") if message_el is not None else "",
                "stack": (stack_el.text or "") if stack_el is not None else "",
                "type": "",  # TRX doesn't carry exception type as a separate field
            }
        stdout_el = output_el.find("vs:StdOut", ns_map)
        stderr_el = output_el.find("vs:StdErr", ns_map)
        stdout_text = (stdout_el.text or "") if stdout_el is not None else ""
        stderr_text = (stderr_el.text or "") if stderr_el is not None else ""

    # Per-test failure log file (matches gotest / cargo / junit pattern).
    if status in ("failed", "errored"):
        log_lines: list[str] = []
        if failure_payload is not None:
            if failure_payload.get("message"):
                log_lines.append(f"[message] {failure_payload['message']}")
            if failure_payload.get("stack"):
                log_lines.append(f"[stack]\n{failure_payload['stack']}")
        if stdout_text:
            log_lines.append(f"[stdout]\n{stdout_text}")
        if stderr_text:
            log_lines.append(f"[stderr]\n{stderr_text}")
        # Shared harness: skip-if-empty (RUN-17) — dotnet previously wrote
        # a 0-byte log when no message/stack/stdout/stderr was captured;
        # now it registers nothing, matching the other adapters. Union +
        # dotnet-specific escape charset (RUN-06), POSIX relative path
        # (RUN-04).
        write_failure_log(
            node_id=identity,
            content="\n".join(log_lines),
            failures_dir=failures_dir,
            artifact_dir=artifact_dir,
            failure_logs=failure_logs,
            extra_chars=_FAILURE_LOG_EXTRA_CHARS,
        )

    entry: dict[str, object] = {
        "identity": identity,
        "test_id": test_id,
        "class_name": class_name,
        "method_name": method_name,
        "status": status,
        "duration_ms": duration_ms,
        "failure": failure_payload,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }
    return entry


def _trx_outcome_to_status(outcome: str) -> str:
    """Map a TRX ``outcome`` attribute value to a normalized status.

    See ``_parse_trx_results`` docstring for the mapping table. Case-
    insensitive comparison because TRX is canonically PascalCase but
    sloppy producers emit other cases.
    """

    normalized = outcome.strip().lower()
    if normalized == "passed":
        return "passed"
    if normalized == "failed":
        return "failed"
    if normalized in ("notexecuted", "skipped"):
        return "skipped"
    if normalized == "inconclusive":
        return "skipped"
    if normalized in ("aborted", "error", "timeout"):
        return "errored"
    # Unknown — default to errored so a future TRX schema change
    # surfaces as a visible warning rather than a silent passed.
    return "errored"


def _parse_trx_duration_ms(duration_attr: str) -> int:
    """Parse TRX TimeSpan format ``HH:MM:SS.fffffff`` to milliseconds.

    Examples observed on the equipped host:
    - ``"00:00:00.0007743"`` → 0 ms (rounded; TimeSpan precision is
      100 ns ticks)
    - ``"00:00:01.2345678"`` → 1234 ms

    Tolerant of missing fractional component and leading-zero variants.
    Returns 0 on parse failure (informational metadata only).
    """

    if not duration_attr:
        return 0
    match = re.match(
        r"(\d+):(\d+):(\d+)(?:\.(\d+))?",
        duration_attr.strip(),
    )
    if match is None:
        return 0
    try:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        fractional = match.group(4) or ""
        # Pad / truncate the fractional component to 7 digits (TimeSpan
        # ticks are 100 ns; 7 fractional digits = sub-second precision).
        fractional = fractional[:7].ljust(7, "0")
        ticks = int(fractional)
        # Convert: seconds → ms; fractional → ms via /10000 (since 10000
        # ticks per ms at 100 ns precision).
        total_ms = (
            hours * 3_600_000
            + minutes * 60_000
            + seconds * 1_000
            + ticks // 10_000
        )
        return total_ms
    except ValueError:
        return 0


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


# ---------------------------------------------------------------------------
# Coverage artifact globbing
# ---------------------------------------------------------------------------


def _glob_coverage_xml(
    results_dir: Path,
) -> tuple[list[Path], Path | None]:
    """Glob Coverlet output under ``results_dir``.

    Returns ``(per_test_files, aggregate_file)``:
    - ``per_test_files`` matches ``coverage.<slug>.cobertura.xml`` (i.e.
      filename has at least one dot before ``.cobertura.xml`` beyond the
      ``coverage`` prefix). Currently empty in practice on Coverlet 6.0.x
      / SDK 8.0 (the XPlat data collector does not honor
      ``<PerTestCoverage>true</PerTestCoverage>`` — see module docstring).
    - ``aggregate_file`` matches exactly ``coverage.cobertura.xml``. This
      is the practical output of every Coverlet 6.0.x XPlat run today.

    Prefers the **first GUID directory** alphabetically when multiple
    are present (which happens because VSTest creates both a
    ``<guid>/coverage.cobertura.xml`` and a ``_<machine>_<date>/In/
    <machine>/coverage.cobertura.xml`` for the same single run — same
    content; we pick the GUID-dir version for determinism).
    """

    if not results_dir.is_dir():
        return [], None

    # Per-test glob: ``coverage.<something>.cobertura.xml`` — exclude the
    # plain ``coverage.cobertura.xml`` from this list because that's the
    # aggregate file with no slug component.
    per_test: list[Path] = []
    for candidate in sorted(results_dir.rglob("coverage.*.cobertura.xml")):
        if candidate.name == "coverage.cobertura.xml":
            continue
        # Exclude opencover / json / lcov siblings — only Cobertura XML
        # belongs to the per-test glob.
        if not candidate.name.endswith(".cobertura.xml"):
            continue
        per_test.append(candidate)

    # Aggregate: the bare ``coverage.cobertura.xml``. Pick a deterministic
    # one when multiple GUID dirs exist (which happens normally — VSTest
    # writes one per "attachment set").
    aggregate_candidates = sorted(
        results_dir.rglob("coverage.cobertura.xml"),
        key=lambda p: str(p).lower(),
    )
    aggregate = aggregate_candidates[0] if aggregate_candidates else None

    return per_test, aggregate


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _safe_read_text(path: Path, *, encoding: str = "utf-8") -> str:
    """Return ``path``'s text content, or empty string on any error.

    ``encoding`` exists for the solution file, which Visual Studio
    writes as UTF-8 **with a BOM** (``utf-8-sig`` strips it; plain
    ``utf-8`` would leave ``\\ufeff`` glued to the first line).
    ``UnicodeDecodeError`` joins ``OSError`` in the caught set because a
    non-UTF-8 build manifest is a real thing in older Windows-authored
    trees and "empty content" is the same degradation path the caller
    already handles for an unreadable file.
    """

    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        return ""


async def _read_dotnet_version(
    dotnet_path: str,
    workspace: Path,
    *,
    env: dict[str, str],
    timeout: float | None,
) -> str | None:
    """Best-effort SDK version read via ``dotnet --version``.

    Returns ``"8.0.421"`` shape strings. None silently on any subprocess
    failure (informational metadata only; never load-bearing for the
    Run Record's correctness).

    RUN-08: the 10 s budget is clamped to the caller's ``timeout``
    (``min(10, caller)``). RUN-18: ``env`` is the sanitized child env.
    """

    try:
        result = await run_subprocess(
            [dotnet_path, "--version"],
            cwd=workspace,
            env=env,
            timeout=_clamp_preflight_timeout(10.0, timeout),
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.decode("utf-8", errors="replace").strip()
    return text or None


__all__ = [
    "COVERLET_FLOOR_VERSION",
    "ENGINE_NAME",
    "RESULTS_DIR_NAME",
    "RUNSETTINGS_FILENAME",
    "STDERR_LOG_FILENAME",
    "STDOUT_LOG_FILENAME",
    "TRX_FILENAME",
    "WARNING_AMBIGUOUS_PROJECT",
    "WARNING_COVERLET_ABSENT",
    "WARNING_COVERLET_BELOW_FLOOR",
    "WARNING_XUNIT_V3_DEFERRED",
    "_COVERLET_RUNSETTINGS_AGGREGATE",
    "_COVERLET_RUNSETTINGS_PER_TEST",
    "_csprojs_listed_in_sln",
    "_declares_test_project",
    "_detect_test_project",
    "_detect_xunit_major_version",
    "_detect_xunit_resolved_version",
    "_ensure_csproj_restored",
    "_format_version",
    "_glob_coverage_xml",
    "_is_layout_ambiguous",
    "_parse_coverlet_version_from_json",
    "_parse_coverlet_version_from_text",
    "_parse_semver",
    "_parse_trx_duration_ms",
    "_trx_outcome_to_status",
    "run_xunit",
]
