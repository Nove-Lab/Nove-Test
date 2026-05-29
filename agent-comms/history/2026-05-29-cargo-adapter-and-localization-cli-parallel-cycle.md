---
from: novetest-pm-team
to: all
type: history
created: 2026-05-29
slug: cargo-adapter-and-localization-cli-parallel-cycle
related:
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - design/implementation-plan/delivery-phasing.md
---

# History: 2026-05-29 parallel cycle — cargo adapter + Localization CLI

The second parallel two-team cycle of the project (after 2026-05-28's
gotest + Localization-engine-entry). Both slices landed; the cargo
slice surfaced the first explicit **polyglot host parity** decision,
and the Localization CLI slice completed the 4th application of the
project's `engine → CLI → freeze` cadence (freeze itself slips to the
next cycle, see "What the next cycle is" below).

## Slices in scope

| Team | Commit | Verdict | Phase touched |
|---|---|---|---|
| Run | `6d9f463` | partial (running-cargo paths unverified at Manual Test layer) | Phase 3 adapter backlog 3/6 → 4/6 |
| Orchestration | `385e2dc` | passed (full E2E green) | Phase 4 §4 — Localization CLI surface + envelope discriminator |

Manual Test merge cycle: `3e0fe93` (verifications) → `99bdbdb`
(findings). Cycle-close commit: this one.

## Decisions made / pinned in this close

1. **`2026-05-29-cargo-adapter-v1-without-rust-e2e.md`** (NEW) —
   the first **polyglot host parity** decision. Establishes
   permanently that every Native engine MUST receive Manual Test
   E2E verification at the same fidelity as Python pytest before MVP.
   Defines three closure triggers for the cargo gap; CEO indicated
   trigger (b) — host gains Rust toolchain at a short-future
   appropriate time — as the preferred near-term path.
2. **`2026-05-29-cargo-adapter-nextest-primary.md`** (AMENDED) —
   §"What this does NOT decide" gains a paragraph deferring the
   `nextest_version` payload-stash convention question (raised by
   Run team in handoff §Open items #1) until the polyglot-host
   trigger fires and a real Rust workspace exposes the surface.
3. **`2026-05-25-supported-engine-matrix.md`** (AMENDED) — adds
   three Rust rows (`cargo` floor 1.74, `cargo-nextest` floor
   0.9.50, `llvm-tools-preview` rustup component) per the Run team's
   handoff proposal §"Supported-engine-matrix proposal". Tested
   ceilings stay TBD until trigger (a) — Release CI Rust cell — or
   trigger (b) fires.

Localization CLI slice raised three issues for PM/CEO review; the
resolutions agreed at this close:

- **Bogus run_id shape divergence** (Manual Test Issue §1): resolved
  by Option A — product unchanged (`not-found` envelope error is
  consistent with `inspect` / `coverage` / `regression` verbs). The
  upcoming `localization_outcome` envelope-shape freeze decision
  will explicitly clarify that `REASON_NO_RUN_EVIDENCE` fires only
  on the `latest` verb against empty store, and on a resolvable run
  that lacks expected upstream evidence — NOT for non-existent run
  IDs (those route to `not-found`).
- **Cache-hit silent-ignore of re-passed flags** (Manual Test Issue
  §2): resolved by Option B — Orchestration team adds `warnings[]`
  emission in the NEXT cycle, bundled with the envelope-shape freeze
  (avoids a v1→v2 supersede). Warning text shape: "requested
  --formula='X' --top-n=Y but cached findings were derived with
  --formula='X0' --top-n=Y0; delete cache and re-run to override".
- **Test-code at SBFL rank-1** (Manual Test Issue §3): no action
  required — already decided in v1 §N and v2 §N′ of the
  Localization Finding shape freeze. Test code is intentionally not
  filtered; the formula degrades naturally as N (total failed tests)
  grows. The Manual Test surfacing is a small-N artifact of the
  `localization-branch` fixture (N=1).

## DoD bullets ticked in this close

`delivery-phasing.md` Phase 4 §4:

- **#1 (line 186)** — "`novetest localization latest --output json`
  against `localization-branch` ranks the bug in top 3" — TICKED.
  Manual Test verified rank-1 with Ochiai score 1.0 (tied with the
  detecting test function — see Issue §3 above for the math
  rationale).
- **#4 (line 189)** — "All four formulas computed and persisted;
  `--formula` flag selects which is presented as primary" — TICKED.
  Manual Test verified all 4 formulas (ochiai / dstar2 / op2 /
  tarantula) cycle through `formula` (top-level) and
  `alternate_scores_available` (3 sorted entries with primary
  excluded) invariantly.

NOT ticked:

- **#2 (line 187)** — Mode field across all three fixtures: only
  `sbfl_per_test` exercised in this slice. The `sbfl_aggregate` /
  `failure_proximity` mode population is gated on separate slices.
- **#3 (line 188)** — NFR-LOC-002 perf: separate perf cycle.

## Load-bearing learnings (for future agents)

### 1. Polyglot host parity is a product-quality contract, not a backlog item

Up through 2026-05-28, every Native engine that landed
(pytest, jest, gotest) was verified at full Manual Test E2E because
the Manual Test host happened to have the relevant toolchain. The
cargo cycle is the first where the host lacked the toolchain
(Rust absent on the current WSL dev box), and rather than blocking
the slice indefinitely, the project chose to ship v1 with the unit
+ integration gate as the E2E signal **AND** record a permanent
forward commitment that the gap MUST close before MVP.

The structural insight: **all engines have been host-toolchain-
dependent the whole time** — we just hadn't named it because hosts
were always equipped. The cargo gap forced the naming. Future
JUnit / dotnet adapters will hit the same pattern; the
`2026-05-29-cargo-adapter-v1-without-rust-e2e.md` decision now
establishes the disclosure-and-trigger template that those adapters
inherit.

CEO's framing at close — "궁극적으론 러스트 등도 모두 파이썬처럼
제대로 테스트는 해야해 (꼭 당장 다음 사이클이어야한다는 말은아니야)" —
crystallized into the "forward commitment, not deferred backlog"
language. The latter would let it slip; the former binds it.

### 2. Verification-doc drift caught at Manual Test layer, captured here

The 2026-05-29 cargo verification doc (`verifications/2026-05-29-run-cargo-adapter.md`,
deleted at this close) stated at line 81:

> Exit code: `0` at the shell (the orchestrator treats engine
> readiness as a soft failure surfaced in JSON; `ok: false` is the
> machine signal).

This is wrong. The actual exit code on the engine-missing path is
**4** — `EXIT_ENGINE_MISSING` from `src/novetest/cli/output.py:16`,
mapped at `src/novetest/cli/app.py:236, 255`. Exit 4 is the
**intentional** documented signal for "engine not ready", distinct
from EXIT_GENERIC (1), EXIT_USER_TESTS_FAILED (3), etc. Manual Test
caught the drift via direct observation (`$ echo $?` after the
probe → `4`).

Captured here so future PMs reusing the verification-doc prose as a
spec source know to use exit 4 verbatim for the engine-missing
path. If a future cycle templates from the 2026-05-29 cargo
verification doc, copy the envelope shape but NOT the exit-code
prose.

### 3. Worktree-isolation guard remains a known blocker for in-place comms edits

Both `Write` and `Edit` tools failed mid-session with the
"background session hasn't isolated its changes yet" guard,
identical to prior cycles (per `GOTCHAS.md`). The sanctioned
fallback (Bash heredoc for new files + Python script for in-place
edits) worked on first attempt. No new symptom — re-flagging here
only as a maintenance reminder: if EnterWorktree-vs-shared-checkout
behavior changes upstream, the heredoc fallback can be retired.

## What the next cycle is

**Single-team Orchestration slice**: Q4 `warnings[]` emission
implementation + `localization_outcome` envelope-shape freeze
decision. Bundled so freeze v1 captures the warnings shape from the
start (avoids a v1→v2 supersede). Specific scope:

- Orchestration adds `warnings[]` emission when CLI-passed
  `--formula` / `--top-n` differ from the cached values.
- PM authors `decisions/2026-05-30-localization-outcome-envelope-shape.md`
  pinning: (a) the 12/9/6/3-key shapes; (b) the `kind ∈ {"fact-set",
  "unavailable"}` discriminator; (c) the cache-vs-request mismatch
  warning shape; (d) `REASON_NO_RUN_EVIDENCE` semantic boundaries
  (see Issue §1 above); (e) the bogus-run_id → `not-found` envelope
  routing.
- After the freeze, the natural follow-on cycles are: Phase 4 §4 #3
  (NFR-LOC-002 perf slice), Phase 4 §4 #2 (`sbfl_aggregate` +
  `failure_proximity` modes + their fixtures), or Phase 3 adapter
  backlog progress (JUnit + dotnet pending Open Questions #4 + #5,
  also pending CEO preference on whether to consolidate with the
  polyglot-host trigger b/c).

## Other deferred items (visible to future PM)

1. **Polyglot host equipping** — trigger (b) from the new decision.
   When CEO equips the host, dispatch a Manual Test sweep covering
   Steps 2-5 of the deleted 2026-05-29 cargo verification doc
   (reconstruct from this history entry + the
   `2026-05-29-cargo-adapter-nextest-primary.md` decision).
2. **Coverage engine LCOV parser dispatched on
   `engine_name == "cargo-test"`** — flagged in Run team's cargo
   handoff §Open items #2. Natural Coverage team slice; until it
   lands, `novetest run --coverage` against a Cargo workspace
   produces a Run Record with `coverage_lcov` artifact but
   `has_coverage_facts` stays `False`.
3. **`design/implementation-plan/engine-adapters.md` §5** — the
   Run team already edited this in the cargo slice per the cargo
   nextest-primary decision §Affected; PM reviewed at close and
   accepted. No further edits queued.
4. **Memory `delete` CLI workflow polish** — carry-forward from
   prior Regression cycle, still pending.
5. **Q4 / Q5 (JUnit / dotnet Open Questions)** — still open in
   `delivery-phasing.md`; resolution gates the remaining 2/6
   Phase 3 adapters.
