---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-25
slug: test-reruns-flag-and-replay-integration
related:
  - agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md
  - agent-comms/tasks/orchestration-team-2026-06-25-test-reruns-flag.md
  - src/novetest/orchestration/recommendation/categories.py
  - src/novetest/orchestration/workflows/test.py
  - design/workflows/orchestration.md
---

# Decision: `novetest test --reruns N` opt-in flag + Replay integration into the synthesizer

- **Date**: 2026-06-25
- **Status**: approved by CEO
- **Authors**: PM (drafted), CEO (approved)
- **Updates**: `design/workflows/orchestration.md` (new § "Integrated replay sub-workflow"), `design/implementation-plan/delivery-phasing.md` (post-MVP queue entry), `design/user-doc/{human,agent}/quick-start.md` + `after-test.md` (document the new flag), `design/website-plan/handoff/docs/quick-start.md` + `understanding-results.md` (same)

---

## The decision (binding)

1. **Add an opt-in flag `--reruns N` to `novetest test`.** Default `N = 0` (current behavior; no replay invoked). When `N > 0`, after the Run Record is persisted, the integrated workflow invokes `replay` for each failed test with `--reruns N`, collects the per-test `ReplayResult`s, and passes them to the recommendation synthesizer via `FactBundle.replay_result`.
2. **The synthesizer's `match_flaky_suspected` matcher (already wired in `categories.py`) becomes reachable** through this single user command. Today it returns `[]` for every real run because `replay_result` is always `None`; this decision closes that gap.
3. **Default behavior unchanged.** Without `--reruns`, `novetest test` runs exactly as it does today. No perf regression for the canonical happy path.
4. **Scheduled as the second post-MVP slice**, after the `reset` verb cycle merges. Same `Orchestration` team owns; same `src/novetest/cli/app.py` file is touched — sequential reduces merge churn.

## Surface (frozen by this decision)

### Flag signature

```
novetest test [<target>] [--coverage|-c] [--reruns N]
```

- `--reruns N` accepts a positive integer.
- `0` (default) = current behavior, no replay.
- `1` = single replay per failed test (cheapest opt-in).
- `5` = recommended floor for flake detection (matches `novetest replay` default in similar contexts).
- Upper bound: none enforced at the CLI; runtime cost is the natural ceiling.

### Envelope (happy path, with `--reruns N > 0`)

The envelope shape is **unchanged** from current `novetest test`. The only differences:

- `data.stage_eligibility.replay` transitions from `"not_run"` to `"available"`.
- `data.recommendations[]` may include one or more `category: "flaky_suspected"` entries (one per test classified `"inconsistent"`).
- The persisted Run Evidence gains per-failed-test `ReplayResult` artifacts under `.novetest/replay/results/`.

Exit code: same matrix as today (0 / 3 dominated by Run Record status; not affected by replay outcomes).

### Error paths

| Trigger | Exit | `errors[0].code` | Recovery |
|---|---|---|---|
| `--reruns` value negative or non-integer | 2 | `invalid-flag` | Re-invoke with a non-negative integer. |
| Replay invocation fails for one or more failed tests (e.g., engine binary disappeared mid-run) | 0 or 3 (dominated by Run) | (no error) | The synthesizer treats that test's `replay_result` as unavailable and falls back to the today-behavior recommendations for that test. **Partial replay failure does NOT fail the whole `test` invocation.** |

### Integrated workflow sequence (load-bearing)

The brief pins the exact composition. High-level intent:

1. Run tests via existing path; persist Run Record.
2. Derive Coverage, Regression, Localization Facts as today.
3. **NEW**: if `--reruns N > 0` AND Run Record has failed tests, iterate failed tests in deterministic order; call `replay_run(...)` for each; collect into a list of `ReplayResult`s.
4. **NEW**: build `FactBundle` with the replay results attached (exact shape — single field or list — pinned by the brief based on current FactBundle / matcher contract).
5. Synthesize recommendations as today.

The replay sub-workflow is **always opt-in via the flag**. Auto-replay (replay-on-every-test) is explicitly NOT in this decision's scope.

## Why now (in the queue)

- The `flaky_suspected` category is currently UNREACHABLE through any user command. The matcher exists, is tested in unit tests at the matcher level, but never fires in real runs. That is a real product gap: the closed taxonomy advertises 7 categories, one of which is dead from the user's point of view.
- The marketing demo for `ailovestesting.com` does NOT include `flaky_suspected` (decision recorded in this same conversation cycle, 2026-06-25). That is the right call for *today*; this decision makes the category demoable *post-integration*, so the next marketing iteration can showcase it honestly.
- Cost is small: no new engine, no new verb, no schema change. One flag, ~50 LOC + tests. Comparable to recent flag additions on `run`.

## Why this scope (not bigger)

- **No auto-replay-on-every-test.** That would multiply default `novetest test` wall-time by N — silent perf regression. Always opt-in.
- **No new verb (e.g. `novetest reanalyze <run_id>`).** Adding `--reruns` to the existing `test` verb is strictly smaller surface. A separate reanalyze verb could come later if real demand exists.
- **No re-synthesis on `replay <run_id>`.** That would require the Replay engine to call the synthesizer, which inverts the current dependency direction (orchestration depends on engines, not vice versa). Keep the dependency graph clean.
- **No `--reruns` on `novetest run`.** The `run` verb is the raw, no-orchestration entry point. Replay belongs to the integrated workflow only.

## Relationship to existing decisions / open questions

- **Reset verb decision (2026-06-24)** — adjacent cycle. Same Orchestration team. Sequence: reset merges first, then `--reruns` cycle starts. No file conflict expected (reset adds a new verb function; this adds a flag to an existing function).
- **Open question #20 (marker-file filter index)** — independent.
- **Replay engine (Phase 5, completed 2026-06-03)** — provides the primitive this cycle consumes. No engine work needed.

## Schedule pin

- **NOT in 0.1.x stable.** Ships in the post-MVP queue.
- Entry conditions: `reset` verb merged on `main`; no open `findings/` blockers.
- Exit conditions: `novetest test --reruns 5` round-trips end-to-end on Linux/macOS/Windows; `flaky_suspected` category demonstrably fires from a failed-test invocation in the integration test; user-doc + Docs handoff updated to document the flag.

## Implementation owners

- **Orchestration team** (`src/novetest/cli/app.py`, `src/novetest/orchestration/workflows/test.py`, possibly `src/novetest/orchestration/recommendation/fact_bundle.py`): the flag, the sub-workflow, the FactBundle wiring, integration test, snapshot pin update.
- No Memory team work needed (Replay engine already persists results; this cycle just consumes them).

PM coordinates with the marketing-PM / website team if a follow-on demo update is desired post-merge.

## Out of scope for this decision

- A `novetest reanalyze <run_id>` verb (would re-synthesize from persisted facts; saved for separate cycle if demand surfaces).
- Auto-tuning of `--reruns` based on test characteristics.
- Replay budgeting / timeout aggregation across multiple failed tests (the per-test `--timeout` from the existing `replay` primitive is used as-is).
- MCP transport surface for the new flag (Phase 7 inherits).

---

## Amendment 2026-07-03 — whole-run replay adaptation ratified

The original §"Decision" item 1 and §"Integrated workflow sequence" item 3
pinned a **per-failed-test loop** (`replay_run(..., target=test_id)` per
failed test). That composition was unimplementable against the shipped
Replay engine: `replay_run` has no `target` parameter (attempt granularity
is the whole original run, `src/novetest/replay/engine.py:49`);
`ReplayUnavailableError` is a returned discriminator, never raised; and
persistence is keyed by original run id only, so N iterations would
overwrite one another while re-executing the full suite `N_failed × reruns`
times.

**Ratified adaptation** (shipped `0a6cddf`, question
`orchestration-team-2026-07-03-reruns-replay-api-mismatch`): when
`--reruns N > 0` and the Run Record has failed tests, ONE whole-run
`replay_run(store, original_ref, reruns=N, timeout=...)` attempt is made;
the Replay classifier performs per-test divergence analysis internally.
`FactBundle.replay_results: tuple[ReplayResult, ...]` holds 0 or 1 elements
today and is forward-compatible with a future per-test-scoped Replay API.
Every element of the frozen surface (flag signature, default-0 byte
identity, `invalid-flag` handling, envelope diff shape, exit-code
dominance, persistence location) ships exactly as originally pinned.

Behavioral nuance for the user-doc pass (Wave 3): with multiple flaky
tests in one run, v1 emits ONE `flaky_suspected` recommendation whose
`test_id` is empty when divergence spreads across several tests. Per-test
attribution would be a Replay-engine feature request (per-test scoping),
not an orchestration change — out of scope unless demand surfaces.

The retired task brief (`orchestration-team-2026-06-25-test-reruns-flag`,
removed with the wave-1 cycle close) is amended by reference: its §2
pseudocode is superseded by this section.
