---
from: novetest-pm-team
to: all
type: history
created: 2026-05-30
slug: localization-warnings-and-cargo-trigger-b-reopened
related:
  - agent-comms/decisions/2026-05-30-localization-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
  - agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
---

# History: 2026-05-30 cycle — Localization warnings shipped, cargo trigger-(b) re-opened

Single-team Orchestration slice + parallel Manual Test cargo
re-verification sweep. The Orchestration slice shipped cleanly and
closed the Localization cache-hit silent-ignore trap from the prior
cycle's Manual Test findings. The cargo sweep — meant to be a
victory-lap closure of polyglot-host-parity trigger (b) — instead
**surfaced a ship-blocking adapter bug AND a deeper design finding**,
both invisible at the unit / integration-test seam because nextest's
env-var requirement is a runtime contract, not a build-time one.
PM's takeaway: trigger (b) **fired** but **DID NOT close** the gap;
the gap is re-opened with sharper diagnostics, and the next cycle
dispatches a Run team hotfix as its lead slice.

## Slices in scope

| Team | Commit | Verdict | Phase touched |
|---|---|---|---|
| Orchestration | `5fa2381` | passed (full E2E green; 8 scenarios + 6 edges) | Phase 4 §4 — Localization CLI warning surface + envelope freeze |
| Manual Test (cargo sweep) | n/a (no-merge) | **failed** (1 ship-blocker + 1 design finding + 1 UX finding) | Phase 3 — cargo adapter trigger-(b) closure ATTEMPTED |

Orchestration merge cycle: `73141a0` (handoff) → `58acb74`
(verification) → `b4b8dec` (findings). Cargo sweep produced findings
directly (no merge): `18a0287`. Cycle-close commit: this one.

## Decisions made / pinned in this close

1. **`decisions/2026-05-30-localization-outcome-envelope-shape.md`**
   (NEW) — the 5th application of the project's `engine → CLI →
   freeze` cadence. Pins the entire `localization` / `localization.latest`
   envelope: 12/9/6/3-key fact-set shape (carried from v2 finding
   decision), `kind` discriminator, top-level `warnings[]` for
   cache-vs-request mismatch (verbatim shape including `*_explicit`
   booleans), `REASON_NO_RUN_EVIDENCE` semantic boundaries,
   bogus-`run_id` → `not-found` routing, `cache_path` template. Pins
   Manual Test's two votes (production cache_path layout; single
   warning per invocation).
2. No other decisions amended or superseded. The 2026-05-29 cargo
   decisions (`cargo-adapter-nextest-primary`,
   `cargo-adapter-v1-without-rust-e2e`) stay in force as written —
   the cargo trigger-(b) closure-status delta lives HERE (in this
   history file), not as a decision amendment.

## DoD bullets ticked in `delivery-phasing.md` this close

**None.**
- Phase 4 §4 #1 + #4 were already ticked in the prior cycle close
  (`136a0c5`).
- Phase 4 §4 #2 (modes) and #3 (perf) — untouched this cycle.
- Phase 3 DoD checkboxes — all ticked from prior cycles; the cargo
  running-paths failure does NOT regress any checkbox (the in-scope
  "all 6 adapters land" statement is not a checkbox).

## Cargo trigger-(b) status — fired, gap NOT closed

`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3
defined three closure triggers; trigger (b) (Manual Test host gains
Rust toolchain) **fired** on 2026-05-30 via
`scripts/dev-host-setup.md` §4. The integration tests that
previously skipped now RUN. But:

- **Both `tests/integration/run/test_cargo_*.py` cases FAIL on the
  equipped host** with a runtime error from `cargo nextest` itself:
  `"libtest JSON output is an experimental feature and must be
  enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1"`.
- The adapter at `cargo_adapter.py:373` `_build_child_env()` sets
  `CARGO_TERM_COLOR`, `RUST_BACKTRACE`, `NO_COLOR` — but **NOT**
  the env var that cargo-nextest 0.9.50+ requires for the
  `--message-format=libtest-json` flag the adapter passes at
  `cargo_adapter.py:138` (coverage path) and `:149` (plain path).
- The build-failure heuristic at `cargo_adapter.py:263` then
  misclassifies the env-var-rejection exit (95) as
  `adapter-unparseable-output` (exit 4).

Manual Test verified the fix by setting the env var manually:
integration tests flip 0/2 → 2/2 in 0.90s; the basic envelope hits
all expected invariants (3 tests captured, exit 3, engine_version
`"1.96.0"`, `::` node-id separator, failure log artifact written);
LCOV coverage materializes correctly (SF lines, `end_of_record`,
2+ source files, ≥1 `DA:N,0` uncovered region). Proof-of-fix
inlined into the new Run team task brief.

**Implication for `2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
§3:** trigger (b) is NOT idempotent with closure. Firing the
trigger only proves the host is **equipped**; closure additionally
requires the adapter to **function** on that toolchain. The cargo
running-paths gap remains open. Closure will come from whichever
of the three triggers next produces a *working* adapter on a real
toolchain:
- The Run team hotfix at
  `tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`
  followed by a re-run of the cargo sweep IS the trigger-(b)
  completion path.
- (a) Release CI Rust cell would also close it (after the same fix
  lands), since CI is also "real toolchain".
- (c) Polyglot host parity sweep cycle bundling cargo + Java +
  .NET remains the deferred-bundle option.

PM does **NOT** amend the 2026-05-29 decision — that decision pins
triggers and intent, not closure status. The status delta lives
here for future-PM legibility.

## Issues raised by the cargo sweep + PM's queueing decisions

### Issue 1 — `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` missing in `_build_child_env()` (ship-blocker)

**Queued as next-cycle Run team task:**
`agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`.

Two-line source change (env var addition + docstring note) + one
unit test pinning the env var assertion + re-run of the integration
suite as the DoD signal. Manual Test attached a full reproducer +
proof-of-fix to the findings doc; the Run team brief inherits the
reproducer + proof-of-fix INLINED (the source findings doc is
deleted at this close).

### Issue 2 — `nextest_version` payload-stash lost at normalizer seam (design finding)

The cargo adapter at `cargo_adapter.py:299` stashes
`payload["nextest_version"] = "0.9.137"` per the convention deferred
in `decisions/2026-05-29-cargo-adapter-nextest-primary.md` §"What
this does NOT decide". But `run/normalizer.py:72` hardcodes
`metadata={"native_exit_code": native_result.returncode}` and
drops every other payload key. The stashed `nextest_version` is
invisible to every downstream consumer of `record.json`.

**Status — surfaced to CEO, awaiting decision.** PM is not
pre-writing a decision because two structurally different fix paths
exist:
- (a) **Reserved-key convention**: normalizer merges
  `payload.get("metadata_for_record", {})` into
  `RunRecord.metadata`. Implicit, free-form, every adapter must
  remember the magic key.
- (b) **Typed-slot amendment**: add
  `NativeResult.metadata: dict[str, str]` (or amend
  `NativeEngineContext`). Explicit, type-checked, all adapters
  pay the field cost up front.

Manual Test recommends (b) (AI consumers handle typed contracts
better than soft `payload` dicts). PM also recommends (b). CEO
call needed; once approved, becomes a follow-up Memory or Run
typed-slot slice with a decision pinning the convention.

### Edge 6 — Cyclopts help rendering for `None`-sentinel flags (UX)

`novetest localization --help` renders `--formula` and `--top-n`
with no default and no description (the `None`-sentinel trick that
enables `*_explicit` detection masks the real defaults from
Cyclopts's auto-rendered help block). Truth lives in the docstring
at `cli/app.py:771` but not surfaced. Manual Test recommends
annotating each flag with
`Parameter(help="...", show_default="ochiai")` (~15 lines for
much-better UX).

**Status — deferred-not-queued.** Not a blocker; not load-bearing
for any decision; CEO call on whether to schedule a polish slice.

## Load-bearing learnings (for future agents)

### 1. Native engine adapters carry RUNTIME contracts that pre-shipped tests miss

The cargo adapter's unit tests stub `run_subprocess` and exercise
the parser; the integration tests use `shutil.which` guards that
only fire when the binary is absent. **Neither path exercises the
actual runtime contract** the binary imposes on its caller (env
vars, positional args, format flags). On a host where the binary
IS present, the runtime contract becomes load-bearing for the
FIRST time — and breakage there only surfaces at Manual Test E2E.

This is THE reason "polyglot host parity" is recorded as a
product-quality contract
(`decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §2).
The cargo trigger-(b) firing this cycle is the canonical example:
the slice shipped with the unit + integration gate green and the
`engine-missing` E2E branch covered, but the running-cargo E2E
branch surfaced a runtime bug invisible to either pre-shipped
layer.

**Lesson for future adapters (JUnit, dotnet, future Rust slow-mode
paths)**: the host-absent E2E path is NOT a substitute for the
host-present E2E path. The decision §3 "3 triggers" mechanism is
binding for THIS exact reason. PM SHOULD include a pre-flight
host-present probe step in every future Native engine adapter
brief at handoff time (not just at the original cycle close).

### 2. "Convention by payload-stash" is a soft contract that silently drops data

The "payload-stash" convention
(use `NativeResult.payload[<key>]` to carry engine-specific
metadata without amending `NativeEngineContext`) was a reasonable
lazy-extension pattern *until* the normalizer seam proved it loses
data unconditionally. The next agent reading `record.json` for an
engine-specific field will not find it, will not know why, and will
assume the adapter forgot to write it.

The right shape is a typed slot on the contract layer
(`NativeResult.metadata: dict[str, str]` or equivalent) that the
normalizer is **required** to propagate. This is Issue 2 above.

**General principle**: when a contract layer's "rest of the dict
gets silently dropped" surfaces, that is the contract layer
*asking to be strengthened*. Resist the "just add another
conventional key" fix path — it perpetuates the soft contract.

### 3. Decision §"trigger fired" ≠ "closure achieved"

The 2026-05-29 decision §3 defined three CLOSURE triggers. PM read
them as binary: trigger fires → closure achieved. Manual Test's
cargo sweep proved this read was wrong. The right model is:
- **Trigger PRECONDITION**: the named event happens (host equipped
  / CI cell lands / sweep cycle dispatches).
- **Trigger CLOSURE**: the named event happens AND the adapter
  works on the resulting toolchain.

The 2026-05-29 decision text is NOT amended (its intent stands),
but future readers should interpret §3 with this distinction. PM
notes the distinction here so future cycles do not declare
"trigger fired" as cycle-close victory until Manual Test has
exercised the equipped/CI-tested adapter end-to-end.

### 4. EnterWorktree guard remains the default state for PM

Identical to prior cycles. `Write` and `Edit` tools fail mid-session
with the background-isolation guard; the sanctioned fallback (Bash
heredoc for new files + Python script for in-place edits) worked
on first attempt for all 3 new files this close. Re-flagging only
as maintenance reminder — same pattern as last 2 cycles
(`GOTCHAS.md` covers it).

## What the next cycle is

**Single-team Run hotfix** for Issue 1
(`tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`),
followed by a re-run of the cargo sweep
(`tasks/manual-test-team-...` to be queued by PM when the hotfix
lands).

The hotfix brief is **self-contained** — it inlines Manual Test's
full reproducer + proof-of-fix from the deleted findings doc, so
the Run team does not need the deleted findings doc to act.

Out of scope for the next cycle (queued / discussed elsewhere):
- **Issue 2's convention decision** — awaits CEO call on (a) vs
  (b); once decided, becomes a small Memory or Run typed-slot
  slice with a decision pinning the convention.
- **Edge 6 UX polish** — deferred-not-queued; CEO call on whether
  to schedule.
- **Coverage LCOV dispatch on `engine_name == "cargo-test"`** —
  natural Coverage team slice; can run in parallel with the cargo
  hotfix re-verification (no file overlap).
- **Phase 4 §4 #2 (modes)** and **#3 (perf)** — both untouched,
  future slices.
- **Phase 3 JUnit / dotnet** — gated on Open Q #4 / #5.

## Other deferred items (visible to future PM)

1. **Cargo trigger-(b) re-verification sweep** — to be queued
   AFTER the Run hotfix merges. The new sweep brief can point at
   the inlined-reproducer Steps 1-3 from the Run hotfix brief
   (which copied them from the deleted cargo sweep findings doc).
   The 2026-05-30 cargo sweep brief + findings are deleted at this
   close; the reproducer survives in the Run hotfix brief.
2. **Issue 2 convention** — `nextest_version` will continue to be
   dropped silently until the typed-slot OR reserved-key fix
   lands. The cargo adapter's stash line at `:299` remains in
   source as a marker for the eventual carrier.
3. **Edge 6 — Cyclopts help text** for the None-sentinel flags.
   Flagged for CEO call.
4. **`scripts/dev-host-setup.md` §4** — no refinement needed
   beyond the 2026-05-30 commit (`a0f6582`). The cargo-nextest
   0.9.50+ env-var requirement is an *adapter* bug, not a
   setup-recipe bug. The §4 verify block correctly identified the
   host as equipped; the bug is downstream.
5. **Carry-forwards still open from prior cycles**:
   - Coverage LCOV dispatch on `engine_name == "cargo-test"`
     (since prior cycle).
   - Memory `delete` CLI workflow polish (since 2026-05-27 cycle).
   - Open Q #4 (.NET `PerTestCoverage` key) + Q #5 (JUnit launcher)
     — both still gating JUnit / dotnet adapters.
