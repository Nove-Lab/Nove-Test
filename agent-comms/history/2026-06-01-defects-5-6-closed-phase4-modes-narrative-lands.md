---
from: novetest-pm-team
to: all
type: history
created: 2026-06-01
slug: defects-5-6-closed-phase4-modes-narrative-lands
related:
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
---

# History: 2026-06-01 cycle — **Defects 5+6 closed; Phase 4 §4 modes-related work narrative LANDS**

Parallel two-team cycle (Localization Defect 5 + Orchestration
Defect 6). Both verdicts **passed**. The two slices **compose
cleanly** — Defect 5 generates the `localization_findings.json`
that Defect 6's status surface honestly reports as available.
Phase 4 §4 modes-related work is now structurally complete: 4
languages × 3 modes × 2 verbs (`<run_id>` + `latest`) + trustworthy
`status` reporting all wired correctly.

## Slices in scope

| Team | Commit | Verdict |
|---|---|---|
| Localization (Defect 5) | `4895847` | passed |
| Orchestration (Defect 6) | `0895e59` | passed |

Composition: Main Branch FF-merged both independently
(`9f56e38` verification for D5, `1ef49bd` verification for D6).
Manual Test ran them as a combined verification on the merged tip
(`5a0031b` findings — covers both). Gate: 776+5 / mypy clean 72 src
/ Orch+status integration trio 44+0 in 19.82s.

## What shipped

### Defect 5 (Localization team) — re-derive on flag mismatch

CLI layer detects when explicit `--formula` / `--top-n` flags don't
match the cached findings' baked-in values. On mismatch:
1. Unlink `localization_findings.json`
2. Re-invoke `derive_localization_findings` (engine sees cache
   miss, full pipeline runs at requested flags)
3. Emit `EnvelopeWarning(code="localization-cache-rederived")`
   with `previous` + `requested` + `cache_path` + per-flag
   `formula_explicit` / `top_n_explicit` booleans
4. Persist the new findings (cache-as-source-of-truth)

Engine API unchanged — `derive_localization_findings`'s signature
stays the same. The fix lives entirely in the CLI/orchestration
layer's pre-call peek-after-call detection. Cleanly scoped.

Manual Test verified:
- 3-step canonical re-derive: byte-accurate to predicted envelope
- mtime-unchanged on no-op (cache-hit when nothing changes — zero
  cost)
- 3 sequential flips: no state pollution; each flip's `previous`
  matches prior flip's `requested`
- Symmetric across `<run_id>` and `latest` verbs
- On-disk persistence reflects new state post-rederive

### Defect 6 (Orchestration team) — `status.sub_reports.*` reflects on-disk facts

`build_status_view` was the Phase 1 stub: it only populated
`latest_entry` + `run_history_size` and left the three
`*_available` fields at their `False` default. Result: `status`
always reported every sub-engine as `"unavailable"` regardless of
on-disk state.

Fix: lifted the SAME cache-only retrieval functions `inspect.py`
already uses (`get_coverage_facts` / `get_localization_findings` /
`get_regression_facts`) into `build_status_view`. Each does
`isinstance(result, FactSet)` against the cached return to compute
the boolean.

**Cache-only contract preserved**: regression uses
`get_regression_facts` NOT `compare_runs`, so a run pair that has
never been compared keeps reporting `regression: unavailable`
(no implicit compute on `status` calls).

Manual Test verified:
- Coverage flip: `unavailable → available` after `--coverage` run
- Localization flip: same after `localization latest` derive
- 3-source agreement: status ↔ inspect ↔ on-disk all align
- Mid-cycle deletion: removing `coverage_facts.json` mid-stream
  immediately flips status to `unavailable` (real-time contract,
  no in-memory staleness)
- Empty store stays universally `unavailable` (gate not over-relaxed)
- Phase 5 boundary: `replay: unavailable` pinned (Phase 5 hasn't
  shipped yet)

### Composition

Defect 5+6 ship together and reinforce each other:
```
User: novetest localization latest --formula op2 --top-n 3
  ↓
[D5 fix] CLI peeks → mismatch → unlinks cache → re-derives
  ↓
Engine: writes localization_findings.json at op2/top_n=3
  ↓
User: novetest status
  ↓
[D6 fix] build_status_view calls get_localization_findings
  ↓ returns LocalizationFinding (not LocalizationUnavailable)
  ↓
status.sub_reports.localization = "available"  ← honest
```

D5 generates the data; D6 honestly reports it. Without D5, D6's
report would be honest-but-stale; without D6, D5's data would be
invisible to the gating surface. Both needed.

## DoD bullets ticked in `delivery-phasing.md`

**None.** Both slices are bug fixes; Phase 4 §4 #2 was ticked at
prior close (`97285e5`). Phase 4 §4 #3 (perf NFR) remains the only
open Phase 4 bullet.

## Phase 4 §4 modes-related work — full narrative LANDS

After this cycle, the **6-defect arc** that started 2026-05-31
with the original Localization fallback-modes slice is fully
resolved:

| # | Defect | Resolved by | Verdict |
|---|---|---|---|
| 1 | cargo-llvm-cov `--no-fail-fast` blocks LCOV on failures | `18fc224` | closed |
| 2 | fixture panic site ≠ bug site | `3ccfd72` | closed |
| 3 | parser catch-all + stdlib pollution | `05f86bc` | closed |
| 4 | `localization latest` rejects non-per-test runs | `4b5fd1d` | closed |
| 5 | CLI flags ignored on cache-read path | `4895847` | **closed this cycle** |
| 6 | `status.sub_reports.*` disconnected from on-disk state | `0895e59` | **closed this cycle** |

The full user-facing surface for Phase 4 §4 #2 modes work
(`sbfl_per_test` + `sbfl_aggregate` + `failure_proximity`) is now
**production-grade across all 4 supported languages**:
- Both verbs (`<run_id>` + `latest`) work for all 3 modes
- CLI flags take effect on every call (cache invalidates correctly)
- `status` honestly reports availability
- All 3 sources (`status`, `inspect`, on-disk files) agree

→ **Phase 4 §4 modes-related work is structurally complete**. Only
the perf NFR (#3, 500 failed × 50k locations < 8s) remains for
full Phase 4 closure.

## Carry-forwards from Manual Test (NOT queued — optional polish)

### Defect 7 (low priority, optional) — `failure_proximity` warning loop

In `failure_proximity` mode (no coverage), the engine returns
`formula: "ochiai"` as a placeholder regardless of `--formula`
input. So a user passing `--formula op2` against a no-coverage
fixture:
1. CLI compares `requested formula="op2"` vs cached/returned
   `formula="ochiai"` → mismatch
2. Re-derive triggered → engine returns finding with
   `formula="ochiai"` (still — placeholder doesn't change)
3. Warning emits again with same `previous`/`requested` shapes
4. Loop indefinitely if AI agent retries based on warning

Two fix options (Manual Test's recommendation):
- (a) Skip formula mismatch check in CLI when engine returns
  `mode == "failure_proximity"`
- (b) Emit a distinct warning code like
  `localization-formula-noop-in-mode` so AI agent can recognize
  this is a structural noop, not a fixable misconfig

**Status: deferred carry-forward**, not queued as task brief.
- Severity: LOW (only fires when explicitly passing `--formula`
  against a no-coverage run; defaults always work)
- Workaround: don't pass `--formula` in no-coverage mode
- PM call: file as Defect 7 if/when AI-agent iteration on formulas
  becomes a real UX pain point. Until then, deferred.

### Regression engine subtle question (carry-forward to Regression team)

Manual Test noticed during D6 Scenario F+: regression engine
returned `kind: fact-set` with **empty `regressed_tests` AND empty
`fixed_tests`** even though run 1 was failing and run 2 was
passing (a clear pass→fail or fail→pass transition).

Possible interpretations:
- Intentional: regression engine considers "transitions" only as
  outcome-changes within the SAME test target, and run 1+2 had
  different test sets
- Bug: `fixed_tests` should populate for a fail→pass transition
  of the same test node_id

**Status: deferred carry-forward, NOT queued**. Out of this cycle's
scope (Manual Test was probing D6's status surface, not the
regression engine itself). PM may surface as a Regression team
question when next touching that engine.

## Process notes

### Two slices ship clean from parallel dispatch

Localization team's D5 fix touches `cli/app.py` (mainly) + small
helpers. Orchestration team's D6 fix touches `orchestration/workflows/status.py`
exclusively. Zero file conflict expected, zero file conflict
observed. WORKLOG.md conflict resolved by Main Branch surgically
(both teams added top entries — standard pattern, now well-
documented).

### Manual Test composition narrative

Manual Test verified both slices in ONE combined sweep against the
merged tip. Their findings explicitly highlight the composition:
"The two slices compose cleanly: D5 generates the
localization_findings.json that D6's status surface honestly
reports as available." This is the kind of cross-slice integration
analysis Manual Test's territory is designed to surface.

### No verification-doc nit pattern this cycle

The recurring verification-doc nit pattern (typos in predicted
output, stale paths, etc.) did NOT recur this cycle. Manual Test's
findings noted "byte-accurate to Main Branch's predicted envelope"
on both D5 and D6. The "informal best practice" (Main Branch
dry-runs verification snippets before filing) appears to have
re-taken hold.

## What the next cycle is

**Phase 4 §4 #3 perf NFR** is the only remaining Phase 4 bullet
(500 failed tests × 50k covered locations < 8s benchmark). After
that, Phase 4 is fully closed.

After Phase 4 closes, options:
- **Phase 5 entry** (Replay engine + Phase 5 SQLite derived index)
  — Manual Test flagged this as the next major milestone
- **Phase 3 JUnit / dotnet** (gated on Open Q #4 / #5 — CEO calls
  needed)
- **Defect 7** if AI-agent UX iteration becomes priority
- **Regression engine `fixed_tests` clarification** if Regression
  team is next to be touched
- **UX normalizations** (metadata shape + file-path absoluteness
  asymmetries) — low-priority pre-MVP polish

PM recommendation: **Phase 4 §4 #3 perf NFR** next. It's the
canonical Phase 4 closer; tractable scope (benchmark + tune); MVP
exit criterion. After that, Phase 5 entry is the natural roadmap
step.

## Other deferred items (visible to future PM)

1. **Phase 4 §4 #3** (perf NFR-LOC-002) — only remaining Phase 4 bullet
2. **Phase 3 JUnit / dotnet** — gated on Open Q #4 / #5
3. **Defect 7** (`failure_proximity` warning loop) — low priority
4. **Regression engine `fixed_tests` clarification** — Regression
   team triage
5. **UX normalizations** (metadata shape + path absoluteness) —
   pre-MVP polish optional
6. **Memory `delete` polish** — long-standing carry-forward
7. **Envelope freeze v2 amendment** for failure_proximity deviation
   — low priority
