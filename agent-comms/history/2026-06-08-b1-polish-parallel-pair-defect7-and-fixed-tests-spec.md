---
from: novetest-pm-team
to: all
type: history
created: 2026-06-08
slug: b1-polish-parallel-pair-defect7-and-fixed-tests-spec
related:
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
---

# B1 critical-polish parallel pair — Defect 7 + Regression `fixed_tests` spec (both PASSED)

## Cycle outcome

Two parallel B1 polish slices closed in one cycle, both passed Manual
Test verification, both merged to `main`:

| Slice | Team | Verdict | Functional commit | Headline |
|---|---|---|---|---|
| Defect 7 — `failure_proximity` formula-noop warning loop | Localization | PASSED | `2fd968d` | Cache file mtime UNCHANGED across two `--formula op2` calls (nanosecond precision); the 6-defect arc began 2026-05-31 closes here |
| Regression `fixed_tests` spec — D6 F+ Q&A | Regression | PASSED (verdict: **INTENT**) | `94c1c7a` | Disjoint `node_id` sets yielding `regressed=0 AND fixed=0` is the correct behavior; signal lives in `summary.added` + `summary.removed`. Zero `src/` changes; contract strengthened |

Cycle commits in chronological order: `4184cd1` (PM brief) → `2fd968d`
(Localization fix) → `945f8de` (Localization handoff) → `1325307`
(Localization verification) → `94c1c7a` (Regression docs) → `55fd693`
(Regression handoff) → `a1d6fad` (Regression verification) → this
cycle-close commit.

## Track-status update — MVP path remaining

| Track | Status | Notes |
|---|---|---|
| **C** envelope-warnings-projection | ✅ closed 2026-06-07 | Option C MVP-blocker |
| **D** dotnet-cobertura-derive | ✅ closed 2026-06-07 | 6th-engine Coverage promise |
| **A — B1** critical polish | ✅ **CLOSED THIS CYCLE** | Defect 7 + Regression contract; the two carry-forwards that had load-bearing user-trust weight |
| **B — B2** UX normalization | NOT YET SCOPED | Category, not a slice — PM scopes into concrete briefs on CEO request |

**MVP completion path next**: B2 UX normalization (metadata shape +
path absoluteness) OR direct MVP release-readiness check. v1 metadata-
channel sunset stays parked at "post-MVP cleanup" per the
`2026-06-06-adapter-warning-surface-v1-metadata-channel` decision —
explicitly NOT folded into B1 even though I originally mis-grouped it
there (caught + corrected mid-cycle; see §"Load-bearing lessons" #5).

## Load-bearing lessons (read these in future cycles)

### 1. Wire-level mtime equality as the strongest possible "loop is broken" proof

Defect 7's verification doc demanded `stat -c %Y` of the localization
cache file BEFORE and AFTER a second `novetest localization <run_id>
--formula op2` call. Manual Test captured both values to nanosecond
precision (`1780885290.650330642`) and reported "mtime invariant:
HOLDS." Unit tests with mocked filesystem state cannot produce this
kind of proof — only a real subprocess + real cache file + real stat
can. The cache-untouched invariant is the strongest single-line proof
that the re-derive loop is structurally gone, not just absent in some
mocked path. Future "loop / idempotency" verifications should reach
for the same wire-level invariant.

### 2. Q&A → Fix-or-Document brief shape is now a validated PM pattern

The Regression `fixed_tests` brief was deliberately 2-phase:
**Phase 1** (Q&A — judge intent vs bug) + **Phase 2** (branch on the
judgment — strengthen docs OR fix logic + symmetry-check the mirror).
The team executed exactly that shape — judged INTENT after walking
`compare.py::_build_transitions` lines 386-406 + the model docstring
invariant + decision `2026-05-26-regression-facts-json-layout.md` §3 +
§C.7, then delivered Phase 2a (contract strengthening) with zero `src/`
changes.

This shape works because the handoff's INTENT-vs-BUG verdict literally
becomes a load-bearing field in the handoff front-matter, forcing the
team to commit to a conclusion before scoping the fix. Future "Manual
Test surfaced something quirky in engine X" cycles should use the same
shape rather than auto-assuming a code change is needed.

### 3. Architectural deviation acceptance pattern

PM brief recommended `localization-formula-noop-in-mode` be emitted at
**orchestration layer** (mirroring the existing `localization-cache-
rederived` orchestration-derived warning). Localization team instead
placed the emit at the **CLI layer** —
`src/novetest/cli/app.py::_rederive_if_cache_overrode_flags` carve-out
branch + helper `_build_localization_formula_noop_warning`. Two
different layer placements; both reach `envelope.warnings`.

The team's deviation rationale was crisp: the existing rederive trigger
point already lived at the CLI layer (cache-vs-flag comparison runs
there in `_rederive_if_cache_overrode_flags`), and a mode-aware carve-
out adjacent to the existing logic was structurally simpler than
threading the noop signal through the orchestration layer. **The brief
had already given Localization team explicit "정확한 emit 위치는 코드
inspect 후 Localization팀이 결정" license** — the deviation is exactly
what that clause anticipated.

Pattern to keep: **briefs that pin shape + name a recommended location
but cede final placement to the implementing team** produce better
outcomes than briefs that pin location rigidly. Future briefs that
recommend a layer placement should explicitly invite reasoned
deviation with a single-paragraph "ceded-to-team" clause.

### 4. Parallel pair pattern — 4th application, perfect file-ownership disjointness

`localization/` + `orchestration/workflows/` + `cli/app.py` (Localization
slice) vs `regression/` + `design/interace-contract/regression.md` +
`tests/integration/regression/` (Regression slice). Zero file overlap;
zero merge friction; alphabetical FF-merge order respected. The pattern
established by 06-06 cargo+dotnet and 06-07 envelope-warnings+cobertura
is now a routine operating mode for parallel PM slices.

### 5. PM mid-cycle correction — contract reading discipline

Initial PM proposal in this cycle was 3-team parallel (Run + Localization
+ Regression), with Run's slice being "v1 metadata key sunset." On
re-reading the source decision
`2026-06-06-adapter-warning-surface-v1-metadata-channel` §"Notes on
co-existence" line 163 ("Schedule for removal: **post-MVP**") and
06-07 history's "Future-cycle backlog" #2 ("**post-MVP cycle**" +
"NOT MVP-blocking"), PM caught the misgrouping before writing the
brief and scaled down to 2-team parallel. Net result: zero contract
violation; one fewer slice this cycle; v1 sunset correctly parked.

**Pattern**: when a PM is about to dispatch a slice that touches a
recently-decided surface, the last pre-dispatch reading should be the
relevant decision's effective-dates / scheduling clause. Mis-bucketing
a contract-bound cleanup into the wrong cycle is a category of error
that's reversible only if caught pre-dispatch.

### 6. Verification-doc precision: `.data.memory_entry.run_record.*` is the canonical envelope path

Manual Test's Regression findings Issue #2 surfaced (again) that the
`jq` path `.data.run_record.run_reference.run_id` is wrong — the
canonical path is `.data.memory_entry.run_record.run_reference.run_id`.
The `memory_entry` wrapper is the persisted Run Record entity; the
`run_record` lives inside it. This is the **second time in three
cycles** that a verification doc has dropped the `memory_entry`
wrapper (first was the .NET adapter hotfix cycle's D2 finding —
documented in `2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md`
§"Load-bearing lessons" 6).

**Pattern to internalize for Main Branch**: when authoring a
verification doc, spot-check every `jq` selector by piping the live
envelope through `jq keys` at the matching level. Briefs should
consider pre-pinning the canonical envelope path in their "Verification
shape" section so Main Branch can copy-paste verbatim.

### 7. Pytest `__pycache__` contamination is a fixture-mutation trap

Regression findings Scenario D (mixed-set independence) initially
failed because Manual Test mutated `tests/test_set.py` contents
between two runs, but `tests/__pycache__/` retained the stale bytecode.
Pytest's discovery picked up the cached compiled module, not the
re-written `.py`, and the second run's `RunRecord.test_results` carried
the BASELINE's tests instead of the mutated set.

The fix is a one-liner: `rm -rf tests/__pycache__ .pytest_cache`
between runs that mutate the same `tests/` directory. This belongs in
every future Manual Test cycle that uses the "mutate-and-re-run" idiom
on pytest fixtures. Worth incorporating into the Manual Test charter
in a future polish pass.

### 8. Contract strengthening as a slice deliverable

The Regression slice delivered zero `src/` changes — only docs + tests.
This is a perfectly valid slice outcome when the underlying engine is
already correct and the gap is interpretability. The slice produced:

- `design/interace-contract/regression.md` +29 lines (new "Transition
  Detection Semantics" subsection pinning union-walk semantics +
  disjoint-set behavior + consumer-guidance filter expression)
- `tests/unit/regression/test_compare.py` +52 lines (1 headline pin
  test placed adjacent to the 9 existing `test_category_*` cases)
- `tests/integration/regression/test_transition_set_semantics.py` NEW
  (4 integration tests: same-set fail→pass, symmetric same-set
  pass→fail, D6 F+ reproducer, mixed-set independence)
- Total: +609 lines, -0 lines

The contract section now explicitly tells future Localization consumers
to filter with
`category == "added" AND target_outcome in fail-like` to catch
newly-introduced failures — a guidance the existing decision §C.7 had
written but had not been operationalized into the engine's interface
contract until now.

## PM dispositions this cycle (cycle-close ratifications)

These dispositions are recorded here, not in separate decision files
(they are surface ratifications, not cross-team structural rulings):

### 1. Compound `--formula op2 --top-n 5` falls through to `cache-rederived`

Localization handoff §"Open Items §1" flagged that the compound case
(both flags differ from cache) does NOT emit
`localization-formula-noop-in-mode` — it falls through to the existing
`localization-cache-rederived` path. Manual Test §"Critical edge case
probe #1" verified this is structurally correct: a user passing both
flags is signaling "I want a re-derive"; the noop helper is a beginner-
helper pattern that need not multiplex with the power-user cache-
rederived pattern.

**Ratified**: current shape (Localization handoff's Option C). The
trade-off is documented in `_rederive_if_cache_overrode_flags` docstring
+ tests cover the SBFL+compound paths. No follow-up action needed.

### 2. CLI-layer emit placement (vs PM-recommended orchestration layer)

See §"Load-bearing lessons" #3 above. Ratified retroactively. Future
briefs should anticipate reasoned layer-placement deviations with a
"ceded-to-team" clause.

### 3. Manual Test verification-doc nits — Main Branch process polish, not slice rework

The two doc bugs Manual Test surfaced (Regression Scenario B
`target_expression` mismatch + jq path missing `memory_entry`) are
verification-doc-writing precision issues, not slice defects. The
slice implementations are correct; the docs around them just needed
to use the canonical envelope path + the same-`target_expression`
reproducer pattern. No re-verification needed for THIS cycle — both
findings explicitly mark these as "cosmetic" with documented
workarounds. Main Branch should internalize the canonical-envelope-
path practice (see §"Load-bearing lessons" #6).

## Cycle-close bookkeeping summary

Transient files retired in this cycle's close commit:

- `tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
- `tasks/regression-team-2026-06-08-fixed-tests-spec.md`
- `handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
- `handoffs/regression-team-2026-06-08-fixed-tests-spec.md`
- `verifications/2026-06-08-defect7-failure-proximity-warning-loop.md`
- `verifications/2026-06-08-fixed-tests-spec.md`
- `findings/manual-test-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
- `findings/manual-test-team-2026-06-08-fixed-tests-spec.md`

Retained:

- `findings/manual-test-team-2026-06-04-host-equip.md` (institutional;
  equipped host #1)
- `findings/manual-test-team-2026-06-06-host-equip.md` (institutional;
  equipped host #2)
- This history file

No `design/implementation-plan/delivery-phasing.md` DoD bullet ticks —
this was a polish cycle that closed two carry-forwards. Phase 4 and
Phase 3 DoD were already 100% checked before this cycle; the only
remaining unchecked DoD bullets are Phase 7 (post-MVP MCP transport),
which is unaffected by this cycle.

## Future-cycle backlog (recorded; NOT auto-queued)

These observations will be surfaced to CEO at the right time, but are
NOT auto-dispatchable:

1. **B2 UX normalization scope-out** — next natural slice after this
   cycle if CEO wants to continue polish before MVP release-readiness
   check. Candidates: metadata-shape asymmetry across adapters,
   file-path absoluteness consistency. PM scopes on CEO request.

2. **v1 metadata-channel cleanup** — still parked at post-MVP cleanup
   per decision contract. Re-queue after MVP release.

3. **Manual Test charter polish — fixture-mutation trap pin** — add a
   "when mutating pytest fixture contents between runs, `rm -rf
   tests/__pycache__ .pytest_cache`" line to Manual Test's testing
   practices section. Trivial scope; PM may file when CEO opens a
   charter-maintenance window.

4. **Brief authoring practice — canonical envelope path pre-pin** —
   future briefs should include a "Canonical envelope assertion paths"
   subsection where applicable, so Main Branch can copy-paste verbatim
   into verification docs. Reduces repeat of the
   `.data.memory_entry.run_record.*` drop.

5. **Localization-consumer audit (post-MVP)** — the contract
   strengthening this cycle made the consumer-guidance filter
   (`category == "added" AND target_outcome in fail-like`) explicit.
   IF a future MVP-feedback signal indicates that existing Localization
   consumers are missing newly-introduced failures, file a small slice
   to retrofit the filter. Not blocking; the contract pin is enough
   for forward-correctness.
