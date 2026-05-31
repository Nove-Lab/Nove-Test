---
from: novetest-pm-team
to: all
type: history
created: 2026-05-31
slug: parallel-cycle-cargo-lcov-and-typed-metadata
related:
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
---

# History: 2026-05-31 parallel cycle — cargo LCOV + typed metadata; **CARGO SLATE CLOSED**

Two-team parallel cycle (Run + Coverage). Both slices verified
**passed** by Manual Test in a single sweep against the merged
tip. **The cargo adapter slate, opened at 2026-05-29 with the
adapter's initial landing under partial verification, is now
fully closed** — every consumer surface (`run`, `run --coverage`,
`inspect`, `coverage show`, `coverage diff`, `regression compare`)
verified end-to-end against the equipped host. Cargo is the
**first non-Python adapter to reach full first-class surface
depth** since pytest set the bar at Phase 1.

## Slices in scope

| Team | Commit | Verdict | Phase touched |
|---|---|---|---|
| Coverage | `53f7920` | passed | Phase 2 (Coverage engine) — cargo LCOV dispatch + parser |
| Run | `4cb5d48` (rebased from `a4d2e31`) | passed | Phase 3 — `NativeResult.metadata` typed slot + cargo migration |

Merge cycle: handoffs from both teams (parallel, zero source-file
conflicts) → Main Branch merged Coverage first then Run (Run's
worktree rebased to resolve a WORKLOG.md textual conflict — both
teams added top-of-file entries at the same insertion point;
source-file diff identical pre/post-rebase) → `d4ebafa`
(combined verification) → `64a5143` (Manual Test combined
findings). Cycle-close commit: this one.

## Decisions made / pinned in this close

**None new.** Both slices implement decisions made in prior
cycles:
- Coverage slice → executes the implicit cargo-LCOV-dispatch
  carry-forward documented in
  `history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`
  §"What the next cycle is".
- Run slice → executes
  `decisions/2026-05-30-native-result-metadata-slot.md` option (b)
  per the dispatch-ordering pin (must land after the 2026-05-31
  env-var hotfix — satisfied).

The 2026-05-30 metadata-slot decision §"What this decision does
NOT decide" item 5 (the original cargo-adapter-nextest-primary
deferred convention question) is now **RESOLVED IN
IMPLEMENTATION** — the typed slot exists, the cargo adapter
uses it, the normalizer copies it through, persistence
round-trips it. No decision-doc amendment needed; the
implementation IS the resolution.

## DoD bullets ticked in `delivery-phasing.md` this close

**None.** Both slices are structural refactors / carry-forward
closures, NOT new DoD-tracked features:

- Run slice → contract-layer typed slot (Issue 2 follow-up; no
  Phase checkbox).
- Coverage slice → cargo engine joining the existing parser
  dispatch (Phase 2 §"Engine adapter coverage" treats cargo as
  Phase 3 implicit-extension, not a numbered DoD bullet).

Phase 3 adapter count stays **4/6** (Python / JS-TS / Go / Rust).
Phase 4 §4 #2 (modes) and #3 (perf) untouched.

## The cargo full-stack milestone (product narrative)

Today's slices complete a 3-cycle arc:

| Cycle | Date | Slice | Cargo state after |
|---|---|---|---|
| Initial landing | 2026-05-29 | cargo adapter `6d9f463` | merged but unverified on real toolchain |
| Trigger-(b) closure | 2026-05-31 (morning) | env-var hotfix `1e736cc` | adapter runs cleanly on real toolchain; Issue 2 design debt + Coverage carry-forward open |
| **This cycle** | 2026-05-31 (afternoon) | typed slot `4cb5d48` + cargo LCOV `53f7920` | **first-class on every consumer surface** |

The cargo first-class achievement means:
- `novetest run` → 4 of 4 supported languages produce canonical `RunRecord` with full metadata (engine version + secondary-runner version where applicable).
- `novetest run --coverage` → 4 of 4 produce canonical `CoverageFactSet` consumable by downstream engines without engine-specific dispatch.
- `novetest inspect` → `sub_reports.coverage == "available"` for all 4 supported languages (was hardcoded `unavailable` for cargo until today).
- `novetest coverage show` / `novetest coverage diff` → cargo runs participate identically to pytest / jest / go-test (Manual Test Scenario 6 verified `coverage diff` end-to-end across two cargo runs for the first time).
- `novetest regression compare` → cargo run records compose cleanly (verified in the 2026-05-31 hotfix Bonus probe 3).

**Implication for Phase 3 6/6 completion**: when JUnit / .NET adapters land (gated on Open Q #4 / #5), they will inherit ALL of:
- The polyglot host parity 3-trigger machinery (production-validated this week).
- The canonical normalization contract (4 engines now confirm "downstream consumers do not branch on `engine_name`" holds).
- The typed `NativeResult.metadata` slot for secondary-runner versions.
- The Coverage parser-dispatch pattern (early-branch helper per ecosystem; LCOV / istanbul / coverage-py / TBD).

Each future adapter's add-cost is now structurally LOWER than cargo's was. The 3-cycle cost-curve was investment; the next two adapters pay it forward.

## Load-bearing learnings (for future agents)

### 1. Parallel cycle works cleanly when territories are disjoint

This was the project's **third successful parallel two-team cycle** (after 2026-05-28's gotest + Localization-engine-entry, and 2026-05-29's cargo + Localization-CLI). The pattern is now production-validated:

- PM authors briefs with explicit "no file overlap" cross-references in both directions.
- Both teams base their worktrees at the same commit.
- Main Branch picks the merge order pragmatically (smaller / earlier-ready first).
- Source-file conflicts: zero.
- **WORKLOG.md conflicts: expected** (both teams add top-of-file entries at the same insertion point). Main Branch resolves surgically — last-merged on top per most-recent convention — and BOTH teams' entries land byte-for-byte preserved in their original prose.

The WORKLOG.md textual conflict is the ONE structural friction in the parallel pattern. Future parallel cycles can confidently expect (and instruct Main Branch to surgically resolve) the same.

### 2. The "canonical normalization holds for 4 ecosystems" empirical confirmation

`agent-comms/history/...` from yesterday hypothesized that downstream engines (Regression, Localization, Coverage, Inspect) are engine-agnostic because `grep 'engine_name' src/novetest/{regression,localization,coverage,orchestration}/` returns zero. This cycle TESTS that hypothesis at runtime:

- Manual Test Scenario 1: cargo `run --coverage` envelope contains BOTH typed-slot fingerprint AND `coverage_outcome.kind: fact-set` from a single command. No special-case routing.
- Manual Test Scenario 6: cargo `coverage diff` between two cargo runs returns canonical `coverage_delta` envelope. `compare_coverage_facts` operates engine-agnostically on set equality.
- Manual Test Scenario 8: pytest run UNAFFECTED. The cargo-specific dispatch in `coverage/derive.py:93` short-circuits before the JSON path; pytest path runs exactly as before.

The canonical-normalization architecture is now confirmed at 4 ecosystems × 4 downstream consumers × parallel-cycle stress. Future ecosystems (Java JaCoCo XML, .NET Cobertura) extend the same pattern.

### 3. Decision-doc file-path drift is real (Run handoff Open Q #1)

The 2026-05-30 metadata-slot decision and the 2026-05-31 task brief both referenced `src/novetest/models/native_result.py` as `NativeResult`'s location. **Actual location: `src/novetest/run/types.py:80`**. The cross-territory authorization PM wrote in the brief was therefore unnecessary — the slice was purely Run-territory.

Implementation is correct; only the prose drifted. Lesson: **PM should grep file paths VERBATIM against the source tree before pinning them in decisions or briefs**. The next adapter brief authoring pass should include a `grep -n` pre-flight against every pinned path.

### 4. Manual Test verification-doc-template gap (Obs 1, 2)

Manual Test surfaced two doc-level discrepancies in Main Branch's verification doc:
- **Obs 1**: Scenario 5 glob path was `.novetest/memory/runs/**/coverage_facts.json` — actual location is `.novetest/coverage/facts/**/coverage_facts.json` (Coverage engine has its own facts root, mirroring Regression's `regression/facts/`).
- **Obs 2**: Scenario 5 example python referenced `f['path']` — actual field name is `f['file_path']`.

Both are doc-authoring nits, not source bugs. The pattern: **verification-doc examples that contain executable Python snippets should be smoke-run against the merged tip before the doc is committed**. Suggested follow-up for Main Branch's verification template — a 1-paragraph "self-test your own examples" gate. Not urgent; recorded here so the next Main Branch verification author sees it.

## Issues raised + PM queueing decisions

### Coverage handoff Open Q's

1. **CI lane for `tests/integration/coverage/test_cargo_lcov_e2e.py`** — DEFERRED to Release team's next CI sweep. Currently skips cleanly on Rust-less runners; becomes a real gate when Rust cell lands per `decisions/2026-05-29-cargo-adapter-nextest-primary.md` §"What this implies".
2. **`branch_arc_semantics` discriminator placement** (currently a `metadata` key; alternatives are model-level discriminator or compare-pipeline normalization). DEFERRED — non-blocking; current `metadata` approach is forward-compatible with both alternatives. PM revisits before the post-MVP `sbfl_aggregate` slice (which consumes branch sets) lands.
3. **Outside-workspace path handling deviates from istanbul precedent** (cargo keeps absolute + emits `lcov_warnings`; istanbul uses `../`-prefixed relpath). DEFERRED — current behavior is correct per brief; harmonization would touch both parsers + amendment to `decisions/2026-05-15-coverage-facts-json-layout.md`. Low priority; flagged in this history for future awareness.
4. **`coverage diff` for two cargo runs** — RESOLVED by Manual Test Scenario 6.
5. **Per-test cargo Coverage** — DEFERRED to post-MVP per `engine-adapters.md:363` (slow-mode path; out of scope for v1).

### Run handoff Open Q's

1. **Decision-doc + task-brief file-path drift** (`models/native_result.py` vs actual `run/types.py:80`) — captured in learning #3 above. Not queued as a slice; PM doc-cleanup will catch it on the next decisions/charters revision pass.

### Manual Test observations

- **Obs 1 / Obs 2** (verification-doc examples) — captured in learning #4 above. Not queued; Main Branch verification template self-correction.

## What the next cycle is

**Open territory** — no PM-queued slice this close. Next cycle is **CEO's choice** from the post-MVP backlog. The candidates, ordered by my read on impact/effort:

| Candidate | Status | Effort | Product impact |
|---|---|---|---|
| **Phase 4 §4 #2** (`sbfl_aggregate` + `failure_proximity` modes) | Ready | Medium-large (2 algorithms + 3 fixtures + integration) | Enables Localization for projects without per-test coverage (covers cargo aggregate-only, gotest aggregate-only, jest per-file-degraded) |
| **Phase 4 §4 #3** (NFR-LOC-002 perf — 500 failed × 50k locations < 8s) | Ready | Medium (benchmark + tune) | MVP exit criterion; Phase 4 cannot close without it |
| **Phase 3 JUnit adapter** | GATED on Open Q #5 (launcher: vendor vs download-on-first-use) — CEO call needed | Large (full adapter) | Phase 3 → 5/6 |
| **Phase 3 dotnet adapter** | GATED on Open Q #4 (Coverlet PerTestCoverage exact config key) — CEO call needed | Large (full adapter) | Phase 3 → 6/6 (Phase 3 complete) |
| **Memory `delete` CLI workflow polish** | Carry-forward from 2026-05-27; scope to be defined | Small | UX polish |
| **Build-failure heuristic UX polish** at `cargo_adapter.py:263` | Carry-forward; Manual Test surfaced as low-priority | Small | Better error code when nextest stderr matches env-var literal |

PM recommendation: ask CEO whether to (a) push Phase 4 forward (#2 or #3), (b) resolve Open Q #4 / #5 to unlock Phase 3 → 5/6 or 6/6, or (c) clean up a small carry-forward first. Each is a defensible direction.

## Other deferred items (visible to future PM)

1. **Edge 6 (Cyclopts help UX for `None`-sentinel flags)** — permanently deferred per CEO 2026-05-30 decision (MVP-post user-feedback re-evaluation).
2. **`scripts/dev-host-setup.md` §4** — stable across 3 trigger-(b) firings (initial install, hotfix verification, this cycle's verification). No drift detected.
3. **Memory `delete` polish** — carry-forward from 2026-05-27; scope undefined.
4. **Open Q #4 / #5** — both still gating Phase 3 → 5/6 or 6/6.
5. **CI Rust cell** — Release team task, queued per `decisions/2026-05-29-cargo-adapter-nextest-primary.md`. Once landed, automatically replaces trigger-(b) re-verifications.
6. **branch_arc_semantics discriminator placement** — non-blocking design choice; PM revisits before sbfl_aggregate.
7. **Outside-workspace path handling harmonization** between istanbul and lcov parsers — non-blocking; if PM wants to harmonize, separate slice.
8. **Decision-doc + brief file-path drift cleanup** (models/native_result.py → run/types.py) — doc-only; PM cleans up on next charter / decision revision.
9. **Main Branch verification-doc self-test gate** — process improvement; flagged in learning #4.
