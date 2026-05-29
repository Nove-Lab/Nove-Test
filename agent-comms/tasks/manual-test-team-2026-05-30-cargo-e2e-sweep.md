---
from: novetest-pm-team
to: novetest-manual-test-team
type: task
status: pending
created: 2026-05-30
slug: cargo-e2e-sweep
related:
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
  - scripts/dev-host-setup.md
---

# Task: cargo adapter E2E sweep — close polyglot-host-parity trigger (b)

## Why this task exists (unusual provenance)

This is **not a verification of a new merge**. It is a re-verification
sweep of the cargo nextest adapter (commit `6d9f463`, merged
2026-05-29) against an actual Rust toolchain — the toolchain that was
**missing** on the Manual Test host at the original verification time.

History context (`history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md`):
the cargo slice shipped v1 with only the `engine-missing` readiness
branch Manual-Test-verified; running-cargo paths (Steps 2-5 of the
since-deleted verification doc) skipped because the host had no
`cargo` / `cargo-nextest` / `cargo-llvm-cov`. The
`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3
established three closure triggers; **trigger (b) has now fired**:

> CEO equipped the host on 2026-05-30 via `scripts/dev-host-setup.md`
> §4. Observed versions: `cargo 1.96.0`, `cargo-nextest 0.9.137`,
> `cargo-llvm-cov 0.8.7`, `llvm-tools-x86_64-unknown-linux-gnu`
> rustup component installed (per refined Verify block — see commit
> `a0f6582`).

This sweep is the operational closure step that the decision §3 names.

## Provenance shape (read carefully)

- **No Main Branch verification doc this time.** This brief replaces
  it. The original 2026-05-29 cargo verification doc was deleted at
  the prior cycle close; PM reconstructed Steps 2-5 below from the
  history file + decision §Context + the adapter's integration test
  source (`tests/integration/run/test_cargo_basic.py`,
  `tests/integration/run/test_cargo_coverage.py`).
- **Findings doc is the normal channel.** Write
  `agent-comms/findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md`
  per your charter format on completion.
- **No source / test changes will land.** This is purely an
  observation pass; no PRs, no merges. If the sweep surfaces a real
  bug, raise it as a finding for PM to triage (likely producing a
  follow-up Run-team or Coverage-team task next cycle).

## Pre-flight host check (MUST run first)

In a fresh shell:

```sh
. "$HOME/.cargo/env"   # only needed if the shell isn't from a fresh login
cargo --version          # expect: 1.74 or newer (observed 1.96.0)
cargo nextest --version  # expect: 0.9.50 or newer (observed 0.9.137)
cargo llvm-cov --version # expect: any (observed 0.8.7)
rustup component list --installed | grep llvm-tools
```

If any command above fails or prints below-floor versions, **STOP**
and report — the host is not equipped per decision §3 trigger (b)
preconditions. PM will refresh `scripts/dev-host-setup.md` §4 before
the sweep proceeds.

## Sweep scope (5 steps, derived from history + decision §Context)

### Step 1 — confirm integration tests no longer skip

The headline outcome of trigger (b). On the equipped host:

```sh
uv run pytest tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py -v
```

**Expected:**
- Both tests **RUN** (not `SKIPPED`).
- Both PASS.
- Total runtime under ~3 minutes combined (cargo nextest is fast;
  cargo llvm-cov takes longer due to instrumentation).

**Record in findings:**
- Exact pytest verdict line (`2 passed`, runtimes).
- The `_require_cargo_and_nextest` / `_require_cargo_nextest_and_llvm_cov`
  guards being non-skip is the entire point of the sweep — call this
  out explicitly.

If either test SKIPS or FAILS, that is the headline finding —
proceed to other steps to gather context but flag this as the
primary outcome.

### Step 2 — basic envelope via `novetest run` (CLI-level)

Drive the adapter through the CLI rather than the integration test
seam. From the `cargo-test-basic` fixture root:

```sh
cd tests/fixtures/projects/cargo-test-basic
novetest init --output json | head -40
novetest run --output json > /tmp/cargo-basic-envelope.json
echo "exit: $?"
```

**Expected envelope properties** (`/tmp/cargo-basic-envelope.json`):
- `schema == "novetest/v1"`
- `command == "run"`
- `ok` reflects the test outcome (the fixture has 1 failing test by
  design → `ok: false` and exit code 3 = `EXIT_USER_TESTS_FAILED`).
- `data.engine_name == "cargo-test"`.
- `data.engine_version` starts with `"1."` (e.g. `"1.96.0"`).
- Captured test count: **3 leaf tests across 2 binaries**:
  - `cargo_test_basic::tests::test_add_passes` (unit, passes)
  - `cargo_test_basic::tests::test_subtract_intentionally_fails` (unit, fails)
  - `<integration_test binary>::test_add_via_integration` (integration, passes)
- Node IDs use `::` separator (the libtest-json convention).
- Failure log artifact written under `.novetest/run/artifacts/.../`
  for the failing test; log body contains `panicked` OR `subtract`.

**Record in findings:**
- Verbatim `data.engine_name`, `data.engine_version` values.
- Test count and per-test outcomes (3 expected; if not 3, headline
  this).
- Full path of the failure log artifact + a 10-line excerpt of its
  body.
- Exit code from shell.

### Step 3 — coverage path via `novetest run --coverage`

From the `cargo-test-basic-coverage` fixture root:

```sh
cd tests/fixtures/projects/cargo-test-basic-coverage
novetest init --output json | head -10
novetest run --coverage --output json > /tmp/cargo-coverage-envelope.json
echo "exit: $?"
```

**Expected envelope properties:**
- `ok: true`, exit 0 (all 4 tests in this fixture pass by contract).
- `data.engine_name == "cargo-test"`.
- `data.artifacts.coverage_lcov` is a present, absolute path; the
  file exists; the file's basename is `coverage.lcov`.
- LCOV body invariants:
  - Contains literal `SF:` (file delimiter).
  - Contains literal `end_of_record`.
  - References both `classifier.rs` AND `arithmetic.rs`.
  - At least one `DA:<line>,0` line (the negative branch of
    `classifier::classify` is intentionally uncovered).
- **Important deferred-state callout**: per Run team's handoff
  §Open items #2, the Coverage engine LCOV parser is NOT yet
  dispatched on `engine_name == "cargo-test"`. Therefore
  `data.availability.has_coverage_facts` (or equivalent flag) should
  be **`false`** even though `coverage_lcov` artifact is registered.
  This is **expected, not a bug** — it is one of the carry-forward
  Coverage-team slices that this sweep can confirm is real.

**Record in findings:**
- LCOV path + first 20 lines verbatim.
- The `availability.has_coverage_facts` flag value (confirm `false`).
- If `has_coverage_facts` is `true`, that means Coverage already
  picked this up automatically — surface as a finding (would be
  surprising).

### Step 4 — `engine-misconfigured` (no nextest) readiness path

The basic-fixture host has cargo + nextest. To exercise the
misconfigured branch:

```sh
# Temporarily hide cargo-nextest from PATH for one command:
cd tests/fixtures/projects/cargo-test-basic
env PATH="$(echo "$PATH" | tr ':' '\n' | grep -v -E '/(home/.*/)?\.cargo/bin' | paste -sd:)" \
    bash -c 'export PATH="$PATH:$HOME/.cargo/bin"; ls $HOME/.cargo/bin | grep -v nextest; novetest run --output json' \
    > /tmp/cargo-no-nextest-envelope.json 2>&1
echo "exit: $?"
```

Simpler alternative (cleaner; preferred):

```sh
cd tests/fixtures/projects/cargo-test-basic
# Move the binary aside for ONE command:
mv "$HOME/.cargo/bin/cargo-nextest" "$HOME/.cargo/bin/cargo-nextest.bak"
novetest run --output json > /tmp/cargo-no-nextest-envelope.json
echo "exit: $?"
mv "$HOME/.cargo/bin/cargo-nextest.bak" "$HOME/.cargo/bin/cargo-nextest"
```

**Expected envelope properties:**
- `ok: false`.
- Exit code: **4** (`EXIT_ENGINE_MISSING` from `cli/output.py:16`;
  verified at the original 2026-05-29 sweep for the no-cargo case;
  the no-nextest case routes through the same exit). If exit is
  different from 4, headline finding.
- `data.engine_readiness` (or equivalent) indicates `engine-misconfigured`
  with `cause` pointing at nextest.
- An error includes the install hint:
  `"install cargo-nextest: cargo install cargo-nextest --locked (or use cargo binstall)"`
  — verbatim from `decisions/2026-05-29-cargo-adapter-nextest-primary.md`
  §1.

**Record in findings:**
- Verbatim error code, message, install hint.
- Exit code.
- Whether the `mv` recovery left the host equipped (re-run Step 1's
  `cargo nextest --version` after Step 4 to confirm).

### Step 5 — `nextest_version` payload-stash surface inspection

The Run team stashed `nextest_version` in
`NativeResult.payload["nextest_version"]` rather than in
`NativeEngineContext` (which is a frozen dataclass without an
extension hook). The convention question (codify payload-stash vs
amend `NativeEngineContext` with an optional `metadata: dict[str, str]`
slot) was deferred until a real Rust workspace exposed the surface —
this is that moment.

From the Step 2 run record (or re-run if needed), locate the
persisted Run Record JSON:

```sh
cd tests/fixtures/projects/cargo-test-basic
RUN_RECORD=$(find .novetest/memory/runs -name record.json | sort | tail -1)
echo "Run record: $RUN_RECORD"
cat "$RUN_RECORD" | python3 -m json.tool | grep -A 2 -B 2 -i nextest
```

**Expected:**
- The Run Record JSON contains `nextest_version` somewhere
  (probably under a `payload` / `native_result` / similar nested
  key). The value looks like a semver (e.g. `"0.9.137"`).

**Record in findings:**
- The exact JSON path where `nextest_version` surfaces (e.g.
  `data.run_record.native_result.payload.nextest_version`).
- The value.
- Whether the surfacing location feels natural for an AI consumer
  (subjective — PM uses this signal for the deferred convention
  decision).

This step's finding feeds the deferred decision in
`decisions/2026-05-29-cargo-adapter-nextest-primary.md` §"What this
does NOT decide" — PM will use Manual Test's observation to decide
whether to codify the payload-stash convention or amend
`NativeEngineContext`.

## Out of scope

- **Broken-cargo-version readiness branch.** Requires a synthetic
  pre-1.74 cargo install which is not practical to set up. Skip.
- **Missing `Cargo.toml` on a Rust-looking workspace.** The original
  `engine-missing` verification already covered the "no cargo" case;
  the "cargo but no Cargo.toml" case is a smaller variant that the
  16 unit tests already exercise at the subprocess seam. Skip unless
  the other steps surface an unrelated issue worth probing.
- **Race detector / thread sanitizer modes.** Decision §"What this
  does NOT decide" — separate flags, future work.
- **Per-test coverage attribution for Rust.** Slow-mode path,
  post-MVP slice.
- **Doctest execution.** Future slice.

## DoD (sweep findings completeness)

The findings doc should answer all of the following:

- [ ] Step 1 — both integration tests RAN (not SKIPPED) and PASSED.
- [ ] Step 2 — basic envelope contains all expected properties
      (engine_name, engine_version, 3 test outcomes, failure log,
      `::` node IDs, exit 3).
- [ ] Step 3 — coverage envelope contains all expected LCOV
      invariants (SF, end_of_record, both source files, ≥1
      uncovered region) and `has_coverage_facts == false`.
- [ ] Step 4 — engine-misconfigured surface verbatim per the
      decision §1 install hint, exit 4.
- [ ] Step 5 — `nextest_version` surfaces in the persisted Run
      Record; the path and value are recorded for PM's deferred
      convention decision.
- [ ] Host left in a clean equipped state after Step 4 recovery
      (re-checked `cargo nextest --version`).

## Findings doc shape

Standard finding format per your charter, plus:

- **Verdict**: `passed` if all 5 steps green; `partial` if some steps
  green and others surface issues; `failed` if Step 1 (the headline
  win) doesn't materialize.
- **Issues**: numbered list per discovered deviation, with verbatim
  observed vs expected.
- **PM follow-up requests**: explicit list of what PM should turn
  into next-cycle tasks (e.g., Coverage LCOV dispatch on
  `engine_name == "cargo-test"`, `NativeEngineContext` metadata slot
  decision).
- **No handoff doc** (no merge happened).
- **No `WORKLOG.md` entry** (no `src/` / `tests/` changes; hook does
  not apply).
- **End-of-work**: run `python3 tools/regen_comms_index.py` if you
  notice INDEX out of sync, then commit the findings doc on its own.

## Cross-references

- Decision: `agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  (§3 trigger (b); §"Affected teams" Manual Test row pointing here)
- Decision: `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
  (§1 install hint verbatim; §"What this does NOT decide"
  nextest_version convention)
- History: `agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md`
  §"Verification-doc drift" (exit code 4 correction baked into
  history)
- Setup recipe: `scripts/dev-host-setup.md` §4 (the recipe just
  applied)
- Integration tests (source for Step 2/3 expected properties):
  `tests/integration/run/test_cargo_basic.py:47-106`,
  `tests/integration/run/test_cargo_coverage.py:50-86`
