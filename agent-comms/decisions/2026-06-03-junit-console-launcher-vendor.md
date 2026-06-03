---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-03
slug: junit-console-launcher-vendor
related:
  - design/implementation-plan/engine-adapters.md
  - design/implementation-plan/delivery-phasing.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - scripts/dev-host-setup.md
supersedes_open_question: 5
---

# Decision: Vendor `junit-platform-console-standalone-1.11.4.jar` inside the distribution at `src/novetest/run/adapters/_vendor/`; ship `THIRD_PARTY_NOTICES.txt`; introduce the vendored-asset pattern

CEO-approved on 2026-06-03 after a PM-led specialist investigation
(java-architect) of JUnit Platform Console Launcher distribution strategies
in the context of enterprise Java CI environments. This closes
[Open Question #5](../../design/implementation-plan/delivery-phasing.md#open-questions)
("JUnit Platform Console Launcher: vendor vs download-on-first-use").

## Decision

The JUnit 5 adapter (`src/novetest/run/adapters/junit_adapter.py`, to be
created at Phase 2.5 JUnit cycle) MUST:

1. **Vendor `junit-platform-console-standalone-1.11.4.jar`** inside the
   distribution at the canonical location:

   ```
   src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
   ```

   The jar is bundled byte-identical from Maven Central. `pyproject.toml`
   MUST include the jar as package data:

   ```toml
   [tool.setuptools.package-data]
   "novetest.run.adapters._vendor" = ["*.jar", "THIRD_PARTY_NOTICES.txt"]
   ```

2. **Resolve the jar path at runtime via `importlib.resources.files()`**, NOT
   via `__file__`-relative paths, so the resolution works when the package is
   running inside a PyApp single-binary extraction:

   ```python
   import importlib.resources
   _vendor = importlib.resources.files("novetest.run.adapters._vendor")
   LAUNCHER_JAR = _vendor.joinpath("junit-platform-console-standalone-1.11.4.jar")
   ```

3. **Ship `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt`** with
   EPL 2.0 attribution for the bundled Console Launcher. Contents MUST cite:
   the EPL 2.0 license text URL, the Console Launcher artifact coordinates
   (group / artifact / version), the JUnit 5 source repository URL, and the
   pinned SHA-256 of the jar. The `novetest --licenses` CLI surface (added at
   Phase 2.5 JUnit cycle) MUST surface this notice file's contents.

4. **No download-on-first-use path is implemented.** No network calls. No
   `~/.cache/novetest/jars/`. The jar is unconditionally available inside the
   binary.

5. **Doctor probe**: when JUnit 5 is detected as the engine, the adapter MUST
   run `java -jar <LAUNCHER_JAR> --version` once during
   `assess_engine_readiness()` to confirm the bundled jar extracts cleanly
   and is executable with the user's JVM. Failure surfaces as
   `engine-misconfigured` of kind `vendored-launcher-extraction-failed`.

6. **`discover` subcommand only.** The adapter invokes the Console Launcher
   exclusively for test discovery. Execution defers to the user's Maven
   Surefire / Gradle build as designed in `engine-adapters.md` §3. The
   Console Launcher's `execute` subcommand is NOT used and MUST NOT become
   load-bearing without a separate decision.

## Rationale

### Why vendor wins decisively

The class of environment where the JUnit adapter is most likely to be used
— enterprise Java CI (Jenkins, GitLab CI, GitHub Actions self-hosted runners,
Kubernetes-based ephemeral pods) — is precisely the class of environment that
most commonly:

- Blocks outbound network access to Maven Central (corporate firewall,
  air-gapped datacenter).
- Performs TLS inspection (Zscaler, Blue Coat) that breaks SHA-256
  verification of downloaded artifacts.
- Uses ephemeral agents that start from clean container images, so any
  `~/.cache/novetest/` cache is never warm — every first invocation in every
  CI job triggers a fresh download.

Download-on-first-use would either fail outright in air-gapped environments
or introduce flaky CI runs in ephemeral-agent environments. The +3–5 MB
binary size cost (current ~25–30 MB → ~28–35 MB, 12–17%) is acceptable in
exchange for unconditional correctness in the target deployment surface.

### Why EPL 2.0 is fine

EPL 2.0 is a weak copyleft. §3.3 explicitly permits including the Covered
Software in a "Larger Work" under different terms, provided the Covered
Software is not modified. We ship the jar byte-identical from Maven Central;
we do not modify it. The only required obligation is to make the source
available (which Maven Central + the JUnit 5 GitHub repository already do)
and to ship a NOTICE file pointing to the license + source. There is no GPL
contamination and no obligation to re-license any Nove Test source code.

### Why this is the first vendored asset

Per the Explore audit (2026-06-03), no prior Nove Test adapter has shipped a
vendored binary blob. The pattern established by the JUnit adapter is:

- Vendored assets live under `src/novetest/<engine>/adapters/_vendor/` (or
  the engine-specific `_vendor/` if not in `run/`).
- The directory ships a `THIRD_PARTY_NOTICES.txt` with one entry per
  vendored artifact.
- `pyproject.toml`'s `[tool.setuptools.package-data]` declares the inclusion.
- Runtime resolution uses `importlib.resources.files()`, NEVER
  `__file__`-relative paths.

Future adapter cycles that need vendored assets (e.g., a hypothetical JaCoCo
CLI helper or a Coverlet diagnostic helper) MUST follow this pattern.

### Why `1.11.4`

`junit-platform-console-standalone 1.11.4` is the current stable in the
JUnit 5.11.x line as of mid-2025. The `discover` subcommand's command-line
surface has been stable since 1.10.0 with no breaking changes documented
through 1.11.x. The 1.10 floor matches JUnit Platform 1.10 (released 2023),
which is the oldest version a current enterprise Java user is likely to have
configured. Ceiling will be bumped to 1.12.x when JUnit 5.12 stabilizes and
we confirm the `discover` API has not changed.

Pin coordinates:

```
Group ID:    org.junit.platform
Artifact ID: junit-platform-console-standalone
Version:     1.11.4
Classifier:  (none)
SHA-256:     <CAPTURED AT JUNIT CYCLE-WRITE TIME from Maven Central .sha256 sidecar>
```

The SHA-256 is captured by the JUnit adapter task brief at the time the jar
is downloaded into the source tree (not pinned in this decision, because the
brief is the artifact that triggers the actual download).

## Risks (carried into the JUnit adapter cycle brief)

The JUnit adapter cycle's DoD MUST include bullets addressing R4 and R5.

- **R4 (medium, MVP-affecting)** — PyApp binary blob extraction has not been
  exercised in prior cycles (only Python source files have). The JUnit
  adapter cycle MUST include an integration test that invokes `java -jar
  <extracted_launcher_jar> --version` from within a PyApp-launched process
  on all three target binary platforms (Linux x86_64, Linux aarch64, macOS
  universal2). If extraction is blocked, the fallback is to extract the jar
  to a temporary directory on first use within the same process (still
  vendor-side, still no network) — implement only if R4 fires.

- **R5 (low)** — Console Launcher CVE patches require a Nove Test binary
  release. The Launcher only runs the `discover` subcommand (no user code
  loading, no test execution, narrow attack surface). This risk is accepted.

- **Windows** — Phase 0 PyApp matrix does not include Windows (deferred per
  Open Question #16). The JUnit adapter MUST gate on OS support and emit
  `engine-misconfigured` of kind `os-unsupported` with the message "JUnit
  adapter requires a non-Windows host until the Windows binary pipeline
  ships" until that gap closes.

## Supported-engine matrix amendment

Adds to `decisions/2026-05-25-supported-engine-matrix.md`:

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| JDK | 17 (LTS) | 21 (LTS) | matches JUnit Platform 1.10+ minimum bytecode level |
| JUnit Platform | 1.10 | 1.11.x | floor matches the bundled Console Launcher's API contract |
| junit-jupiter | 5.10 | 5.11.x | user-project dependency; absence surfaces as `engine-misconfigured` |
| Maven (Surefire) OR Gradle (`useJUnitPlatform()`) | Surefire 3.0 / Gradle 7.6 | latest | one of the two MUST be present |
| JaCoCo | 0.8.11 | 0.8.x | coverage path; absence surfaces as `mapping_granularity: aggregate` (no coverage) |
| junit-platform-console-standalone (vendored by us) | 1.11.4 (pinned) | 1.11.4 (pinned) | shipped inside the binary; user does not install |

PM updates the matrix decision in the same commit as this decision.

## Dev host setup amendment

`scripts/dev-host-setup.md` §5 (currently a placeholder) is filled in this
same commit with concrete `apt-get install openjdk-17-jdk maven` /
`brew install openjdk@17 maven` recipes and a Maven Surefire smoke probe.

## Implementation notes for the JUnit adapter task brief

When PM writes the JUnit adapter task brief, it MUST:

1. Pin §1's vendored-asset location + filename verbatim.
2. Pin §3's `THIRD_PARTY_NOTICES.txt` requirement.
3. Include the R4 PyApp binary blob extraction test as a DoD bullet covering
   all three target binary platforms.
4. Include the Windows OS gate as a DoD bullet.
5. Reference the supported-engine matrix amendment for JDK + JUnit Platform
   floors.
6. Reference the dev-host-setup Java section so Manual Test can equip the
   host before E2E verification.
7. Establish the `_vendor/` pattern as a load-bearing convention — note that
   future adapter vendored assets follow this directory + NOTICE + package-data
   shape.

## Future intent — vendoring removal as the ultimate target (CEO direction 2026-06-04)

Per CEO direction on 2026-06-04, vendoring the Console Launcher is the
**pragmatic v1 choice but NOT the desired end state**. The other five
ecosystems (Python, JavaScript/TypeScript, Go, Rust, .NET) follow a
consistent policy: Nove Test does not bundle any native tooling; the
user installs the toolchain themselves, and absence surfaces as a
structured `engine-misconfigured` warning with install guidance. JUnit
currently deviates because the JUnit 5 ecosystem uniquely lacks a
`--list-only` CLI surface in Maven Surefire / Gradle (only the JUnit
Platform `discover` API exists, exposed solely by the Console
Launcher).

### Endgame

Drop the `_vendor/` jar; route the absence of a user-installed Console
Launcher into a JUnit-specific **feature degradation**, not a vendored
workaround. The relevant degradation:

- `novetest run --list` on a JUnit project where the user has not
  installed `junit-platform-console-standalone` (on PATH or as a
  Maven/Gradle dependency) emits `engine-misconfigured` of kind
  `junit-list-unavailable` with the message "JUnit list-only mode
  requires `junit-platform-console-standalone`; install or invoke
  `novetest run` without `--list`."
- `novetest run` (full execution) MUST remain unaffected — it already
  routes through user Maven Surefire / Gradle and never touches the
  Console Launcher.

This re-aligns JUnit with the **fail-with-specific-message** pattern
used in all other ecosystems (e.g. cargo's `cargo-nextest missing`
warning, gotest's `go binary missing` warning) instead of vendoring
around the gap.

### Triggers to scope the removal cycle

The vendoring stays in place until ALL of:

1. `novetest run --list` verb has been formally designed (not yet in
   any brief; today's vendoring carries the verb's contract implicitly).
2. Real user feedback indicates `--list` is in actual use AND users
   are willing to install Console Launcher when they need it.
3. (Alternative) A Phase-2.5-era hardening cycle scopes the removal as
   part of a broader "policy consistency" sweep across all ecosystems.

### What does NOT change before removal

- The hotfix cycle (`tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`)
  MUST NOT touch the vendoring — out of hotfix scope; re-opening the
  vendoring surface would expand the cycle and re-introduce decision
  risk during a defect-fix cycle.
- The vendored-asset *pattern* (`_vendor/` directory convention,
  `THIRD_PARTY_NOTICES.txt` attribution, `importlib.resources`
  resolution, Hatchling force-include) remains established and may be
  re-used by future cycles that DO need vendored helpers — the
  removal removes only the JUnit Console Launcher specifically, not
  the pattern.

### Open Question tracking

Tracked as `delivery-phasing.md` Open Question #21 (Post-MVP polish).

## Effective date

2026-06-03.

## Supersedes

Open Question #5 in `delivery-phasing.md`. The "we vendor a copy as a
fallback" phrasing in `engine-adapters.md` §3 is corrected to "we vendor the
Console Launcher (the only supported strategy)" in the same commit.
