---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-25
slug: supported-engine-matrix
related:
  - design/implementation-plan/foundations.md
  - design/implementation-plan/engine-adapters.md
---

# Decision: Native engines stay user-owned; version drift is mitigated by a supported matrix, not bundling

CEO-approved on 2026-05-25 after a structural risk review of "what happens
when pytest / jest / coverage.py / Istanbul change shape under us?"

## Decision

Nove Test **does not bundle native test engines** (pytest, jest,
coverage.py, Istanbul, future adapters). The Native Engine remains the
user's local install, discovered via readiness probes — the design
principle stated in `foundations.md` ("The Native Engine is the source of
truth for discovery, execution, assertion semantics, and native
reporting").

Version-drift risk is mitigated by **three engineering practices**, not
by taking ownership of the engines:

1. **A supported version matrix** documented per ecosystem (floor + tested
   ceiling).
2. **Defensive parsing** in the Run / Coverage adapters (graceful
   handling of unknown fields, missing fields, new outcome strings).
3. **Health monitoring** of single-maintainer plugin dependencies
   (specifically `pytest-json-report`) so an abandonment signal triggers
   a fork-plan task, not a fire.

## Rationale — why bundling is structurally wrong

Bundling was raised as a candidate. License compatibility was confirmed
(all dependencies — pytest, jest, coverage.py, pytest-cov,
pytest-json-report — are MIT or Apache 2.0, all bundle-compatible), but
license is not the binding constraint. The binding constraints are:

1. **User test code is environment-coupled.** A user's pytest run is not
   just `pytest`; it is `pytest + their conftest.py + their plugins +
   their fixtures + their Python interpreter + their installed
   dependencies`. Either we execute their code in our isolated
   interpreter (which cannot import their dependencies → tests fail), or
   we inject our pytest into their interpreter (which collides with
   their installed pytest). Neither works.

2. **jest is intrinsically workspace-coupled.** It reads `package.json`,
   requires `node_modules/jest/`, and resolves test files relative to
   the workspace root. "Bundling our jest" is not a meaningful
   operation; jest's resolution is rooted at the user's project. Same
   for Node.js.

3. **The Native Engine principle defines the product.** Bundling
   inverts it: we would *be* the engine. That makes us a test framework,
   not a test orchestrator — a different product with upstream-bug /
   security-patch / ecosystem-compatibility burdens we are not
   resourced to take on.

4. **CI parity breaks.** A user expects `pytest tests/` (local) and
   `novetest run tests/` to give the same results. Bundling our own
   pytest diverges this.

License is therefore a moot point — the architectural answer is "no"
before licensing enters the discussion.

## Supported version matrix (initial)

Floor = the minimum version we promise to support (engine-readiness
probe warns when below). Ceiling = the latest version routinely
exercised in CI. The matrix is maintained by PM; each engine team may
propose floor/ceiling movements via `agent-comms/questions/`.

| Dependency | Floor | Tested ceiling | Notes |
|---|---|---|---|
| pytest | 7.0 | 8.x | pytest 9.0 release triggers a re-validation slice |
| pytest-json-report | 1.5 | 1.5.x | **Single maintainer — health-monitored quarterly by PM** |
| pytest-cov | 4.0 | 5.x | |
| coverage.py | 7.0 | 7.x | major 7.0 (2022) — schema stable in the 7.x line |
| jest | 28 | 29.x | jest 30 beta tracked; pre-emptive compatibility slice when released |
| Node.js | 18 LTS | 22 LTS | tracks GHA `actions/setup-node` default LTS |
| Python | 3.11 | 3.13 | matches CI matrix in `.github/workflows/ci.yml` |
| Istanbul JSON (via jest) | — | — | format is jest-bundled; no separate floor |
| go (toolchain) | 1.21 | TBD (pending CI Go cell; Release adds) | `go test -json` schema is 1.18+ compatible; floor 1.21 matches the fixture `go.mod` directive. `GOTOOLCHAIN=local` is set so older binaries don't auto-fetch a newer toolchain. Added 2026-05-29 (amendment) for the `go-test` adapter that landed 2026-05-28 (`adf7bac`). |
| cargo (Rust toolchain) | 1.74 | TBD (pending CI Rust cell; Release adds) | matches edition 2021 + nextest 0.9.50 baseline; floor pinned by `decisions/2026-05-29-cargo-adapter-nextest-primary.md`. Added 2026-05-29 (amendment) for the cargo adapter that landed 2026-05-29 (`6d9f463`). |
| cargo-nextest | 0.9.50 | TBD | floor pinned by `libtest-json --message-format` stability per `decisions/2026-05-29-cargo-adapter-nextest-primary.md` §1. Absence surfaces as `engine-misconfigured`. |
| llvm-tools-preview (rustup component) | — | — | required by `cargo-llvm-cov` for coverage; absence surfaces as `engine-misconfigured` via the LCOV-not-emitted check. |
| JDK | 17 (LTS) | 21 (LTS) | matches JUnit Platform 1.10+ minimum bytecode level. Added 2026-06-03 (amendment) for the JUnit adapter pending Phase 2.5; floor pinned by `decisions/2026-06-03-junit-console-launcher-vendor.md`. |
| JUnit Platform | 1.10 | 1.11.x | user-project dependency; floor matches the vendored Console Launcher's API contract. Added 2026-06-03. |
| junit-jupiter | 5.10 | 5.11.x | user-project dependency; absence surfaces as `engine-misconfigured`. Added 2026-06-03. |
| Maven (Surefire) OR Gradle (`useJUnitPlatform()`) | Surefire 3.0 / Gradle 7.6 | latest | one of the two MUST be present. Added 2026-06-03. **Maven CLI floor amended 2026-06-04: 3.9 → 3.8.** Ubuntu noble's `apt-get install maven` yields 3.8.7 and the JUnit adapter's argv (`-B`, `-Dmaven.test.failure.ignore=true`, Surefire 3.x goals) uses no 3.9-specific syntax. Three independent gates (Run team's, Main Branch's, Manual Test's) all ran Maven 3.8.7 against the canonical fixture cleanly across the 2026-06-03 → 06-04 JUnit cycle. Floor 3.8 matches `scripts/dev-host-setup.md §5` recipe (apt path) and the `.claude/settings.json` pre-authorized install. Per `agent-comms/history/2026-06-04-phase2.5-junit-adapter-three-hotfix-cycle.md` §8. |
| JaCoCo | 0.8.11 | 0.8.x | coverage path; absence surfaces as `mapping_granularity: aggregate` (no coverage). Added 2026-06-03. |
| junit-platform-console-standalone (vendored by us) | 1.11.4 (pinned) | 1.11.4 (pinned) | shipped inside the binary at `src/novetest/run/adapters/_vendor/`; user does not install. Pinned by `decisions/2026-06-03-junit-console-launcher-vendor.md`. Added 2026-06-03. |
| .NET SDK | 8.0 (LTS) | TBD (.NET 9 STS, after CI cell) | xUnit v2 + Coverlet path; xUnit v3 / MTP coverage deferred from MVP per `decisions/2026-06-03-coverlet-pertestcoverage-key.md` §6. Added 2026-06-03 (amendment) for the .NET adapter pending Phase 2.5. |
| coverlet.collector | 6.0.2 | 6.0.x | floor pinned by `decisions/2026-06-03-coverlet-pertestcoverage-key.md`; sibling `<SingleHit>false</SingleHit>` required in generated runsettings. Added 2026-06-03. |
| xunit (v2) | 2.6 | 2.9.x | v3 detected and routed to `xunit-v3-coverage-deferred` warning per `decisions/2026-06-03-coverlet-pertestcoverage-key.md` §6. Added 2026-06-03. |
| Microsoft.NET.Test.Sdk | 17.6 | 17.x | bundled with .NET 8 SDK; absence surfaces as `engine-misconfigured`. Added 2026-06-03. |

This matrix is the contract surface for engine readiness probes and
adapter version negotiation. When a probe sees an engine below floor it
emits a structured `warnings` entry in the envelope (does not block
execution — informational).

## Risk classification (carried from the review)

The risk is concentrated NOT in pytest / jest themselves (their core
contracts are decade-stable) but in **the plugins between us and them**:

- 🟡 **`pytest-json-report`** — third-party, single maintainer. JSON
  shape stable, but maintainer abandonment would land directly on us.
  Mitigation: PM quarterly health check; the plugin is ~500 LoC, fork
  is feasible if needed.
- 🟡 **pytest-cov + coverage.py version pairing** — the user controls
  the combination; we generate `.coveragerc` per run to control what we
  can.
- 🟡 **Outcome / status string drift** — pytest / jest may add new
  outcome categories; current adapters fall back to `unknown` (visible,
  not silent), but a defensive-parsing audit is on the future-cycle
  list.
- 🟠 **Imminent watch**: pytest 9.0 (date TBD), jest 30 (beta in
  progress 2026; deprecates `--testLocationInResults` which we use).

## Maintenance discipline

- **New engine added** (Phase 3 onward — go test, JUnit, dotnet, cargo)
  → PM extends the matrix with floor + ceiling in the engine's onboarding
  decision doc.
- **Floor bump** (drop support for an old version) → PM proposes via a
  new `decisions/` entry; never bury in a code commit.
- **Ceiling bump** (validated latest in CI) → routine; team that
  validates writes a `WORKLOG.md` entry referencing this decision.
- **`pytest-json-report` health check** → PM, quarterly: read the repo's
  last-commit date and open-issue trend; if dormant > 6 months, write a
  fork-plan task targeted at Run team.
- **pytest 9 / jest 30 release** → PM writes a pre-emptive compatibility
  slice task as soon as the release is announced (do not wait for a user
  to report breakage).

## Mitigation slices — backlog for future cycles

The CEO approved this decision but deferred the implementation slices to
later cycles. The following are recorded here as future-cycle candidates,
NOT as queued `tasks/`:

1. **Defensive parsing audit** (Run + Coverage; ~½ day each)
   - Verify every adapter / parser handles unknown outcome strings,
     missing optional fields, and new status enums gracefully.
   - Existing code already does ~70% of this (e.g.
     `entry.get("missing_branches", [])`); audit closes the gap.
2. **Floor-version CI lane** (Release; ~½ day)
   - Add a CI matrix cell pinned to the floor versions (pytest 7.0,
     pytest-cov 4.0, coverage.py 7.0). Current CI only validates the
     latest; this lane catches drift on the lower bound.
3. **Engine-readiness probe enhancement** (Run; ~½ day)
   - Compare detected `engine_version` against this matrix's floor;
     emit a structured `warnings` entry in the envelope when below.

PM should consider these after Phase 3 (Regression) opens — Regression
will inherit the same engine-dependency surface, so a defensive baseline
under it is well-timed.

## Affected teams / files

- **All teams** — bundling native engines is off the table. When a
  version-drift concern arises, route to PM for matrix maintenance, not
  to a "ship our own engine" proposal.
- **PM** — owns this decision; owns the matrix; performs the quarterly
  `pytest-json-report` health check; writes pre-emptive compatibility
  slices when an upstream major release is announced.
- **Run team** — when a new adapter lands, propose its floor/ceiling in
  the adapter's introduction handoff for inclusion in this matrix.
- **Coverage team** — same, for any coverage-format dependency.
- **Release team** — when the floor-version CI lane slice is dispatched,
  it lives in their territory.
- **`foundations.md`** — Native Engine principle stands; no edit needed
  but this decision should be linked from foundations' persistence /
  distribution section when the doc is next revised.

## Effective date

2026-05-25.

## Supersedes

Nothing. First explicit articulation of the supported-engine-version
contract. The implicit principle ("Native Engine is the source of
truth") existed in `foundations.md` from project inception; this
decision makes the operating model concrete.
