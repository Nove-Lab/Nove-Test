---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-04
slug: equip-and-exercise-for-adapter-cycles
related:
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
  - scripts/dev-host-setup.md
---

# Decision: Manual Test MUST equip the host and exercise the CLI-level smoke for every new Native Engine adapter cycle

CEO-approved on 2026-06-04 in response to the JUnit cycle's failed verdict
(`findings/manual-test-team-2026-06-04-phase2.5-junit-adapter.md`).

## Context

The 2026-06-04 JUnit cycle (merged tip `b2bd10f`) was verdict-failed
because three independent code defects (P0 + 2× P1) plus one process gap
survived **all three** guard layers — Run team's local gate, Main Branch's
pre-merge gate, and the Manual Test pass — because every layer was
skip-gated on a host lacking a JDK. The team's `tests/integration/run/
test_junit_*.py` cases evaluated `shutil.which("java") is None or
shutil.which("mvn") is None` → skip, AND the suite contained zero
CLI-level subprocess invocations of `novetest run`, so the orchestration
layer's `.relative_to(store.path)` invariant was never exercised end-to-end
even on a notionally equipped host.

The defects were:

1. **P0** — `artifact_paths["reports_dir"]` pointed at Maven/Gradle's native
   output (outside `store.path`), violating the `.relative_to` invariant
   and producing a `cli-error` envelope on every `novetest run`/`novetest
   test` invocation against JUnit.
2. **P1** — `artifact_paths["coverage_xml"]` was never populated even with
   `collect_coverage=True`; coverage path silently degraded to `unavailable`.
3. **P1** — Gradle's JUnit XML reporter produces `<testcase name="testFoo()">`
   (with parens); Maven's Surefire strips them. The normalizer kept the
   parens, yielding cross-build-tool `identity` divergence.
4. **Process** — the integration tests called `run_junit()` directly, bypassing
   `src/novetest/orchestration/workflows/run.py:85-88` where the
   subpath invariant lives.

The 2026-05-29 polyglot-host-parity decision
(`2026-05-29-cargo-adapter-v1-without-rust-e2e.md`) established the forward
commitment to full Manual Test E2E parity for every adapter but
allowed cargo to ship as a v1 exception with the gap closed via
triggers (a/b/c) at a later time. The structural availability of that
"v1 exception" path is what let the JUnit cycle default into the same
skip-gated posture without a counterweight. This decision adds the
counterweight.

## What this decision pins

### 1. Equip-and-exercise is a verdict-blocking gate for every new Native Engine adapter cycle

For any cycle that introduces a new Native Engine adapter (or that
materially modifies an existing adapter's CLI-execution path), the
Manual Test pass MUST:

- **Equip the host with the relevant toolchain** per `scripts/dev-host-setup.md`
  (or equivalent local installation) *before* running Gate B.
- **Exercise the CLI-level smoke**: invoke `subprocess.run(["uv", "run",
  "novetest", "run"], …)` (or the equivalent verb under test) against the
  canonical happy-path fixture, AND assert the resulting exit code
  ∈ {0, 1}. An exit code of 2-or-higher (`cli-error` envelope) is a
  P0 blocker — the verdict CANNOT be `passed`.
- **NOT verdict-pass** while any of the relevant
  `tests/integration/run/test_<engine>_*.py` cases skip on the verification
  host. If those cases skip, the verification is `partial` (not `passed`),
  and the cycle remains open until the equipping path is exercised and the
  integration tests run rather than skip.

### 2. Run team adds the CLI-level smoke at adapter-introduction time

Every new Native Engine adapter task brief from PM MUST require Run team
to add at least one CLI-level smoke under `tests/integration/run/
test_<engine>_*.py`, shaped roughly as:

```python
import subprocess

def test_cli_smoke_run_emits_envelope(<fixture_workspace>: Path):
    """End-to-end CLI smoke — exercises orchestration `.relative_to` invariant."""
    if shutil.which(<toolchain_cli>) is None:
        pytest.skip("<toolchain> required; install per scripts/dev-host-setup.md §N")
    init = subprocess.run(["uv", "run", "novetest", "init"],
                          cwd=<fixture_workspace>, capture_output=True, text=True, timeout=60)
    assert init.returncode == 0, init.stderr
    run = subprocess.run(["uv", "run", "novetest", "run"],
                         cwd=<fixture_workspace>, capture_output=True, text=True, timeout=300)
    assert run.returncode in (0, 1), (
        f"unexpected cli-error: returncode={run.returncode} stderr={run.stderr!r}"
    )
    envelope = json.loads(run.stdout)
    assert envelope["schema"] == "novetest/v1"
    if envelope["ok"]:
        assert envelope["data"]["run_record"]["engine_name"] == "<engine_name>"
```

The `shutil.which` skip-gate keeps the test no-op on hosts without the
toolchain. On Manual Test's equipped host the gate evaluates `False`,
the test runs rather than skips, and the orchestration `.relative_to`
invariant is exercised end-to-end.

### 3. Verification doc template carries the requirement

`agent-comms/README.md` §"Standard body sections (per type) → verifications/"
is amended in the same commit as this decision to require Main Branch to
list the CLI-level smoke gate and the Gate A "tool floor + plugin floor"
pre-flight pattern (§4) in every adapter-cycle verification doc.

### 4. Gate A floor specifies "tool floor + plugin floor in fixture config", not bare tool floor

For build-tool-driven ecosystems (Maven, Gradle, MSBuild, Cargo with
cargo-nextest, future Ruby/Swift/etc.), verification doc Gate A pre-flight
checks the **combination of** the CLI tool floor AND the relevant
plugin / extension floor as declared in the fixture's project config:

- **Maven** — `mvn -v >= 3.8` AND fixture's `pom.xml` pins `maven-surefire-plugin >= 3.0`.
- **Gradle** — `gradle -v >= 7.6` AND fixture's `build.gradle[.kts]` pins relevant plugin floors.
- **MSBuild (.NET adapter, future)** — `dotnet --version >= 8.0` AND fixture's
  `csproj` pins `coverlet.collector >= 6.0` per `2026-06-03-coverlet-pertestcoverage-key.md`.
- **Cargo** — `cargo --version >= 1.74` AND `cargo nextest --version >= 0.9.50`
  per `2026-05-29-cargo-adapter-nextest-primary.md`.

This codifies findings recommendation #6 from the 2026-06-04 JUnit findings:
bare CLI version checks miss the actual semantic floor (which is the plugin),
and adapter brick walls happen at the plugin layer. The supported-engine
matrix (`2026-05-25-supported-engine-matrix.md`) already specifies the plugin
floor; verification docs now MUST surface it as an explicit pre-flight check,
not just the CLI floor.

### 5. Composition with the 2026-05-29 polyglot-host-parity decision

This decision **strengthens** the 2026-05-29 forward commitment but does NOT
retroactively alter the handling of the existing cargo gap:

- **Cargo's specific gap remains open** per `2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  §3 closure triggers (a/b/c). This corollary does NOT force a new cargo
  Manual Test pass; cargo was a documented v1 exception and the
  equip-and-exercise rule does NOT apply retroactively to slices that
  already shipped under the v1-exception clause.
- **For all NEW adapter cycles** — JUnit hotfix re-pass onward, .NET, and
  any future ecosystem — the equip-and-exercise rule is binding. The
  "v1 exception" path that cargo used is closed for new adapters.
- The 2026-05-29 polyglot-host-parity *commitment* (every adapter
  eventually achieves Manual Test E2E parity) continues to govern the
  cargo backlog. This corollary governs the *forward* posture for
  adapters that have not yet shipped.

## Affected teams / files

- **Manual Test team** — applies the equip-and-exercise rule starting with
  the JUnit hotfix re-pass.
- **Main Branch team** — when writing verification docs for adapter cycles,
  includes the CLI-level smoke gate scenario and the Gate A "tool floor +
  plugin floor" pre-flight pattern.
- **Run team** — when writing new adapter task briefs and integration tests,
  includes the CLI-level smoke pattern from §2 and the host equipping
  pointer to `scripts/dev-host-setup.md`.
- **PM team** — when writing new adapter task briefs, includes the
  equip-and-exercise expectation in the brief's "Re-verification" section
  and references this decision file by name.
- **`agent-comms/README.md`** — amended in the same commit as this decision
  to add the two required scenarios to the verification-doc template.
- **`scripts/dev-host-setup.md`** — continues to be the host equipping
  recipe; no edits forced by this decision (the existing maintenance
  protocol from `2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §5 holds).

## What this decision does NOT decide

- **Whether to pre-authorize `sudo apt-get install …` (and similar
  system-wide install commands) in `.claude/settings.json`** — findings
  recommendation #7. That is a CEO operational call about the auto-mode
  classifier's threshold for elevated-privilege host equipping commands;
  PM raises it as a separate question. This decision is verdict policy,
  not classifier configuration.
- **Whether the JUnit Console Launcher vendoring (`2026-06-03-junit-console-launcher-vendor.md`)
  or future vendored-asset patterns need additional gates** beyond what
  those decisions pin. This decision adds the equip-and-exercise rule
  only.
- **MVP release gate composition** — whether all native adapters must be
  equip-and-exercise green before MVP, or whether the automated CI matrix
  can substitute for some. The 2026-05-29 §"What this does NOT decide"
  language still governs.

## Effective date

2026-06-04. Applies immediately to the JUnit hotfix re-verification
(`tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`) and to all
subsequent adapter cycles.

## Supersedes

Nothing. Strengthens `2026-05-29-cargo-adapter-v1-without-rust-e2e.md`;
that decision remains in force.
