---
from: novetest-pm-team
to: all
type: history
created: 2026-06-02
slug: phase1-and-phase6-complete-recommendation-synthesis-lands
related:
  - agent-comms/history/2026-06-01-phase4-complete-perf-nfr-loc-002.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/recommendation-synthesis.md
  - design/interace-contract/orchestration.md
  - design/workflows/orchestration.md
---

# History: 2026-06-02 cycle — **Phase 6 entry LANDS; Phase 1 + Phase 6 → 100% complete; MVP user-facing surface ships**

Solo Orchestration-team cycle. Verdict **passed**. This slice
simultaneously closes **5 DoD bullets** across **2 phases**:
- `delivery-phasing.md:96` (Phase 1 lingering bullet — `novetest test`
  on empty downstream facts returns `all_green` / `unavailable_analysis`)
- `delivery-phasing.md:249-252` (Phase 6 DoD #1-4 — fixture category
  sets, syrupy snapshot, AI-agent round-trip, default-verb alias)

**Phase 1 → 100% complete.** **Phase 6 → 100% complete.** This is the
largest single-slice MVP value delivery in the project to date: it
introduces the **load-bearing user-facing surface** (`novetest test
[target]`) that turns Nove Test from a collection of fact-emitting
verbs into a single command that returns cited, deterministic
recommendations consumable by an AI agent (or a human).

After this cycle, MVP scope shrinks to: **Phase 5** (Replay + SQLite
derived index) + **Phase 3** JUnit/.NET adapters (gated on Open Q
#4/#5) + **Phase 7** MCP transport (post-MVP).

## Slice in scope

| Team | Commit | Verdict |
|---|---|---|
| Orchestration (Phase 6 entry) | `fa3be73` | passed |

Lineage: PM brief queued (`dd02942`) → Orchestration team handoff
→ Main Branch FF-merge as `fa3be73` → Manual Test findings.

## What shipped

### 1. Closed 7-category taxonomy frozen at `recommendation_schema_version: 1`

The brief's §1 PM decision (Open Q #10 closure) is now committed code.
`src/novetest/orchestration/recommendation/categories.py` (~480 lines)
implements the priority registry + trigger predicates per the binding
table:

| P | Category | Trigger |
|---|---|---|
| 1 | `regression_with_localization` | regressed_tests ∩ related_failed_tests ≠ ∅ |
| 2 | `investigate_location` | confidence ∈ {high, medium} AND rank ≤ 3 |
| 3 | `investigate_regression` | newly_failing test in regressed_tests |
| 4 | `coverage_gap` | uncovered line overlaps localization file/range |
| 5 | `flaky_suspected` | Replay classification = "inconsistent" (Phase 5 dep, mock-tested only) |
| 6 | `unavailable_analysis` | downstream stage(s) unavailable AND tests failed |
| 7 | `all_green` | no failed AND no regression AND no flake |

Compound rule (`regression_with_localization` swallows constituents)
implemented and unit-test-pinned. Mutual exclusion (`all_green` drops
when any other category fires) implemented.

### 2. Integrated `novetest test [target]` workflow

`src/novetest/orchestration/workflows/test.py` (~310 lines) implements
the brief §5 binding sequence:

```
run/execute → memory/store_run_evidence → evaluate_stage_eligibility →
coverage/derive_coverage_facts → regression/resolve_latest_baseline →
regression/compare_runs → localization/derive_localization_findings →
build_fact_bundle → synthesize_recommendation → cite_recommendation_evidence
```

Best-effort error policy for downstream stages: any single-engine
failure surfaces as `stage_eligibility.<stage> = "unavailable"` with
the engine's `unavailable.reason`; the workflow continues. Run-execute
failures remain fatal.

### 3. Default-verb alias activated (with reserved-verb disambiguation)

`_inject_default_verb_alias` is a pure pre-Cyclopts argv
pre-processor. Disambiguation rule binding: reserved verbs
(`init/test/run/memory/inspect/compare/status/coverage/regression/localization/replay`)
ALWAYS win, even if a same-named path exists.

E2E pinned by `tests/integration/cli/test_default_verb_alias.py` (6
subprocess scenarios) + `tests/unit/cli/test_default_verb_alias.py`
(9 disambiguation cases).

### 4. AI agent round-trip contract (NFR-ORCH-002)

`tests/integration/orchestration/test_recommendation_round_trip.py`
runs `novetest test` against `localization-branch`, picks the first
`investigate_location`, and resolves every citation via the canonical
retrieval interface. Asserts:

1. Each citation resolves to a non-null fact
2. Slot values in the recommendation match resolved fact values
3. Every emitted recommendation has ≥1 citation (REQ-ORCH-005)

This is the load-bearing NFR-ORCH-002 evidence — any future change
that breaks citation traceability fails this pin loudly.

### 5. Empirical determinism contract

3 consecutive cache-rederives on the same `localization-branch` run_id
produce **byte-identical digests** (`-0x6a313cf878c7dabd`).
Pinned by
`test_determinism_localization_branch_three_consecutive_rederives`.

### 6. Numbers

| Metric | Baseline (`dd02942`) | This slice (`fa3be73`) | Delta |
|---|---|---|---|
| Default-suite pytest | 781 + 10 skipped | 871 + 5 skipped | **+90 net tests** |
| mypy --strict src files | 72 | 80 | +8 |
| Pre-merge gate wall time | ~32 s | ~39 s | +7 s |

## DoD bullets ticked in `delivery-phasing.md`

- **Phase 1 line 96** — `novetest test` integrated workflow on empty
  downstream facts → `all_green` / `unavailable_analysis`. **Phase 1
  → 100% complete.**
- **Phase 6 #1** (line 249) — fixture category sets byte-identical
- **Phase 6 #2** (line 250) — syrupy snapshots pinned
- **Phase 6 #3** (line 251) — AI-agent round-trip integration test
- **Phase 6 #4** (line 252) — default-verb alias activated

**Phase 6 → 100% complete.**

## Phase progress map after this cycle

| Phase | Status | Notes |
|---|---|---|
| 0 — Foundations + install | ✅ 100% | Closed 2026-05-16 |
| 1 — Onboarding + Run + Memory | ✅ 100% | **Closed 2026-06-02 (this cycle, last bullet)** |
| 2 — Coverage | ✅ 100% | Closed 2026-05-21 |
| 3 — Regression | ✅ 100% | Closed 2026-05-28 (JUnit/.NET deferred to separate cycles per supported-engine-matrix decision) |
| 4 — Localization | ✅ 100% | Closed 2026-06-01 |
| 5 — Replay + SQLite | ❌ 0% | Open Q #19 (SQLite schema + rebuild trigger) blocks brief scoping |
| 6 — Recommendation synthesis | ✅ 100% | **Closed 2026-06-02 (this cycle)** |
| 7 — MCP transport | ❌ 0% | post-MVP |

Plus deferred engine adapters:
- Phase 3 JUnit (Open Q #5: vendor vs download Console Launcher)
- Phase 3 .NET (Open Q #4: Coverlet PerTestCoverage config key)

## Product framing — what just shipped

Before this cycle, a user wanting to find a bug had to chain three
commands manually:

```
$ novetest run tests/        # produce raw run
$ novetest coverage show <id>  # see facts
$ novetest localization latest  # see ranked locations
```

After this cycle:

```
$ novetest tests/              # default-verb alias
[ JSON envelope with stage_eligibility + recommendations,
  each carrying cited evidence resolvable back through Memory ]
```

The recommendation envelope is **deterministic**, **AI-agent-friendly**
(structured fields, no LLM-rendered prose), and **traceable** (every
recommendation cites ≥1 fact, every citation resolves to a non-null
source). This is the product's **load-bearing UX promise** in
executable form.

## The non-obvious story — sort-invariant trap surfaced and pinned

The brief §1 binding stable-sort key is
`(priority asc, category asc, primary_slot asc)` where `primary_slot`
is the category-specific deterministic key (e.g. `"src/calc.py:32"`
for `investigate_location`).

The team's first draft sorted by `recommendation_id` — the SHA-1
hash of `f"{category}|{primary_slot}"`. Deterministic, yes — but
**breaks the "lex-min file wins" intent**. The `localization-branch`
fixture surfaces this vividly: `tests/test_calculator.py` (Ochiai 1.0
because it runs ONLY failing tests) sorts ahead of the actual bug
site `localization_branch/calculator.py` by SHA-1 hash. Rank-1
first-invariant violated.

Fix: `Recommendation` carries `primary_slot: str` as an **internal
field** (NOT in `to_dict()` — keeps wire shape minimal). Future
maintainers MUST keep it on the dataclass; removing silently regresses
the brief's binding sort.

Regression-pinned by
`test_localization_branch_first_run_yields_investigate_location`.

**Lesson for future briefs**: when prescribing a sort, also prescribe
the `primary_slot` extraction per category. The brief §1 already did
this (table column "primary_slot"), and that explicit pre-design
caught the issue when the team encountered the empirical
manifestation. Without that table, the team might have shipped the
SHA-1 sort and the bug would have surfaced months later.

## Verification doc transcription errors (Manual Test surfaced)

Three documentation issues in the verification doc, all
**non-blocking** and **non-defect**:

### Sub-obs #1 — Scenario D `ok`/`exit_code` mismatch

Verification doc expected: `ok: False, exit_code: 2`.
Implementation emits: `ok: True, process_rc: 3` (consistent with
Phase 1 `novetest run` convention: `ok` is `True` whenever transport
succeeded; user's tests failing is **data**, not transport error;
exit code 3 = `EXIT_USER_TESTS_FAILED`).

Manual Test cross-checked: `novetest run tests/` on the same failing
fixture emits `rc=3, ok=True` — identical convention. The handler
docstring at `cli/handlers/test.py:27-35` is explicit about this.

**Disposition**: verification doc transcription error. Implementation
internally consistent with Phase 1 convention. No code change needed.
This history entry records the correction permanently; the verification
doc itself is transient and rotated out at cycle close.

### Sub-obs #2 — Scenario F determinism design flaw

Verification doc instructed 3 sequential `novetest test` invocations
asserting byte-identical envelopes. Actual behavior: Run 1 differs
from Run 2/3 by construction because pipeline re-execution creates
NEW run records, and Run 1 has no baseline → `regression: unavailable`
→ `unavailable_analysis` fires; Run 2 has Run 1 as baseline →
`regression: available` → `unavailable_analysis` drops; Run 2 == Run 3
byte-identical.

The actual Phase 6 DoD #1 determinism contract is enforced by
`test_determinism_localization_branch_three_consecutive_rederives`,
which uses `build_test_outcome_from_run_id` (**cache-only
re-derivation**) — same run_id → same facts → same recommendations.
This is the correct path. Integration pin passes green.

**Disposition**: verification doc Scenario F design flaw. The actual
determinism claim is upheld by the cache-rederive integration test.
No code change. Future verification docs should specify cache-rederive
path explicitly when asserting determinism on a stateful pipeline.

### Sub-obs #3 — `inspect.recommendations` deferred

`novetest inspect <run_id>` does NOT populate a `recommendations` field.
The brief §3 used permissive language ("inspect.py MAY receive an
additive call to `synthesize_recommendation`"), so this is within
spec.

**PM disposition: (a) deferred — no follow-up needed for MVP.**
Rationale:
1. `inspect`'s core surface is raw facts; recommendations are the
   `test` workflow's final output (different consumer model: facts vs
   actionable advice).
2. Adding recommendations to inspect would mean re-running the synth
   pipeline on every inspect call. Cheap (it's a pure function over
   already-stored facts), but no MVP user requested it.
3. Users wanting recommendations re-derive simply re-run
   `novetest test` — same workflow, fresh recommendations.

If post-MVP UX iteration surfaces this as a real need, a small
follow-up cycle can wire `synthesize_recommendation(fact_bundle)` into
`inspect_cmd`'s envelope (no schema bump required — the field is
additive).

## Forward-looking Qs from handoff (carry-forwards, NOT queued)

The Orchestration team's handoff surfaced three substantive forward-
looking questions. PM disposition for each:

### Q1 — `score_normalized > 0` floor for `investigate_location`

Empirical: `localization-branch` produces 10× `investigate_location`
because dense-rank ties under SBFL push many score-0.0 entries to
rank ≤ 3. Most carry no actionable signal.

**Disposition**: **v2 carry-forward, NOT queued.** Requires
`recommendation_schema_version` bump (Phase 6 ships v1; changing trigger
predicate semantics post-v1 is a v2 surface change). The current
cardinality (10 on `localization-branch`) is empirically pinned as a
regression-pin against future v2 PR.

**PM note**: I lean toward shipping this in v2 — score-0 entries are
noise to AI agents. But the v2 trigger conditions should be designed
holistically (Q1 + Q2 + any new v2 categories together), not piecemeal.
Park until a v2 design cycle.

### Q2 — Drop redundant `unavailable_analysis` when actionable guidance exists

When ≥1 stage is unavailable AND tests failed, `unavailable_analysis`
fires. But when OTHER categories (e.g. `investigate_location`) also
fire on the same run, the `unavailable_analysis` recommendation
becomes somewhat redundant.

**Disposition**: **v2 carry-forward, NOT queued.** Same v2 surface
change reasoning as Q1. Park.

**PM note**: I lean toward keeping `unavailable_analysis` as-is in v2
— it's informational (which stage was unavailable + why) and an AI
agent can choose to suppress display when other actionable cats fire.
The cost of emitting is near-zero; the value to a "why didn't I get
regression info?" query is meaningful. But again — v2 design cycle.

### Q3 — `handlers/` package precedent

This slice introduced `src/novetest/cli/handlers/` for one verb (test).
Other verbs (init / run / status / inspect / memory / coverage /
regression / compare / localization) remain inlined in `cli/app.py`
(~1200 lines).

**Disposition**: **B (inline-by-default) — `handlers/` is reserved for
verbs with substantial envelope-building or multiple-outcome surfaces.**

Reasoning:
1. `cli/app.py` at ~1200 lines is large but not unmanageable; inline
   handlers keep the verb's wiring + envelope-building visible at one
   read.
2. `test`'s handler is substantial (3-stage envelope per Run outcome)
   AND will receive future polish (e.g. progress streaming for long
   runs); extraction was justified.
3. Future cycle: if a verb's handler grows past ~80 lines OR has
   ≥3 envelope outcomes, migrate it to `handlers/`. Otherwise inline.

**This disposition is not a binding decision (no
`decisions/` entry yet); it's a working policy that PM may revisit when
the next verb's handler implementation surfaces a counter-case.**

## Process notes

### Brief's pre-frozen §1 taxonomy paid off enormously

The brief's §1 binding table (7 categories × priority × trigger
predicates × required slots × citation kinds) was the largest pre-
design artifact the project has shipped. Without it, the
implementation would have spent multiple sub-cycles debating slot key
names and trigger boundary conditions. With it, the team translated
the table into Python in ~1 day and spent the rest of the cycle on
the sort-invariant trap, FactBundle ergonomics, and the alias hook.

**Lesson**: for closed-taxonomy work, freeze the taxonomy in the
brief as a binding table BEFORE dispatch. The taxonomy is design
work; implementation is translation. Mixing them in one slice causes
churn.

### Manual Test surfaced 3 verification-doc transcription errors

This is the first cycle where Manual Test surfaced ONLY verification-
doc-side issues (no slice defects). The verification doc had:
- Scenario D wrong `ok`/`exit_code` literals
- Scenario F design flaw (asserted pipeline-re-execution determinism on
  a stateful pipeline)
- `inspect` invocation without `--run-id`

All three were caught by Manual Test's independent cross-check
(reading the handler docstring; running the actual command; counting
fields in the actual envelope). This validates the "fresh-eyes
independent verification" pattern — Manual Test reads the source as a
**user** and surfaces drift between what the doc claims and what the
code actually does.

**Lesson**: Main Branch's verification doc should be dry-run before
filing. The "informal best practice" mentioned in
`history/2026-06-01-defects-5-6-...md` re-took hold in the perf cycle
but slipped here. Suggest re-emphasizing: **Main Branch runs the exact
predicted CLI invocation, captures the empirical envelope, then
transcribes the literals — never transcribes from memory or from
unit-test fixtures.**

### Largest single-slice MVP delivery

By the numbers:
- **+8 new src files** (5 recommendation modules + 1 workflow + 2 CLI
  handler shims + 1 handlers package marker)
- **+90 net new pytest tests**
- **3 substantive forward-looking Qs** surfaced (Q1, Q2, Q3) — all
  v2 carry-forwards or working policies
- **2 phases LANDED in one slice** (Phase 1 + Phase 6)

This is the project's pattern for **closed-taxonomy phase exit**: a
deeply-pre-designed brief + a single high-throughput Orchestration
team slice + an independent Manual Test verification cross-check.
Apply the same pattern to Phase 5 (Replay + SQLite) when its brief
scopes.

## What's next

### Immediate options (CEO's call)

1. **Phase 5 entry** — Replay engine + SQLite derived index.
   - Open Q #19 (SQLite schema for `run` + `test_outcome` tables;
     rebuild trigger: lazy / explicit `novetest reindex` / both) blocks
     brief scoping. PM should ping CEO with options before scoping.
   - 2 slices: Memory team (SQLite infrastructure) + Replay team
     (engine). Sequence recommended (SQLite first; Replay depends on
     it).
   - Estimated effort: 5-7 days.

2. **Phase 3 JUnit adapter** — Open Q #5 CEO answer needed first
   (vendor vs download Console Launcher).

3. **Phase 3 .NET adapter** — Open Q #4 CEO answer needed first
   (Coverlet PerTestCoverage config key in the version pinned).

4. **Polish backfill** — Defect 7 (failure_proximity warning loop),
   Regression `fixed_tests` clarification, peak-RSS smoke for
   NFR-LOC-002, slow-CI host sampling, Memory `delete` polish, UX
   normalizations, envelope freeze v2 amendment, Q1+Q2 v2 design.

### PM recommendation

**Phase 5 entry**. Reasoning:
- Phase 5 is the LARGEST remaining structural piece. Phase 3
  JUnit/.NET are gated on Open Qs that need CEO investigation;
  Phase 7 MCP is post-MVP.
- Phase 5's Replay engine activates the `flaky_suspected` category
  (currently mock-tested only) — completing the v1 recommendation
  surface.
- Phase 5 SQLite index is also the first architecture milestone
  introducing a derived cache layer; pre-MVP timing is correct
  (pre-MVP MEMs are ≤O(1000) runs, but designing for >O(10000) is
  cheap now and expensive later).
- After Phase 5 closes, MVP scope is **only** Phase 3 JUnit/.NET
  (Open-Q-gated) — release-ready trajectory.

PM will ping CEO with Open Q #19 options once Phase 5 dispatch is
agreed.

## Other deferred items (visible to future PM)

1. **Phase 5** (Replay + SQLite index) — Open Q #19 blocks brief
2. **Phase 3 JUnit** — Open Q #5 blocks brief
3. **Phase 3 .NET** — Open Q #4 blocks brief
4. **Phase 7 MCP transport** — post-MVP
5. **v2 recommendation_schema** design cycle — Q1 (score floor) + Q2
   (drop redundant unavailable_analysis) + any new categories
6. **`handlers/` package migration** — working policy: inline by
   default, extract when ≥80 lines or ≥3 envelope outcomes
7. **`inspect.recommendations` field** — deferred, no follow-up unless
   post-MVP UX iteration demands
8. **Defect 7** (`failure_proximity` warning loop) — low priority
9. **Regression engine `fixed_tests` clarification** — Regression team
   triage
10. **UX normalizations** (metadata shape + path absoluteness) — pre-MVP
    polish optional
11. **Memory `delete` polish** — long-standing carry-forward
12. **Envelope freeze v2 amendment** for `failure_proximity` deviation
    — low priority
13. **Peak-RSS smoke assertion** for NFR-LOC-002 perf benchmark
14. **Slow-CI host sampling** for NFR-LOC-002
15. **Snapshot coverage expansion** to all fixtures (currently 1)
