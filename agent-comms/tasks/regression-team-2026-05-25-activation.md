---
from: novetest-pm-team
to: novetest-regression-team
type: task
status: pending
created: 2026-05-25
slug: activation
related:
  - design/interace-contract/regression.md
  - design/workflows/regression.md
  - design/implementation-plan/delivery-phasing.md
---

# Task: Regression team activation — read, study, and propose charter additions

## Why this task exists

Phase 2 is complete (4/4 DoD on origin/main). Phase 3 (Regression
Comparison) is the next sub-product. Your team has been **dormant since
project inception** — your charter at
`.claude/agents/novetest-regression-team.md` is a placeholder that
explicitly says "flesh out the conventions / contracts when the team is
woken up."

This slice wakes the team up. You will NOT write any production code
this cycle. Your output is a `questions/` file proposing concrete
additions to your own charter, informed by reading the binding
contracts and the precedent set by the Coverage team. PM will then
turn your proposal (plus any decisions discussed) into the foundation
for next cycle's first real implementation slice.

This is intentional pacing: Phase 3 is greenfield, so we freeze
contracts and conventions before code, not during.

## The activation checklist (the spec)

Your charter (section "Activation checklist (when this team is first
invoked)") lists the three steps verbatim. This task IS those three
steps:

1. **Read in full**:
   - `design/interace-contract/regression.md`
   - `design/workflows/regression.md`
   - `design/interace-contract/coverage.md` + `design/workflows/coverage.md`
     (read-only; you consume Coverage outputs)
   - `design/interace-contract/memory.md` + `design/workflows/memory.md`
     (read-only; Memory is your primary upstream)
2. **Study Coverage Team's final `coverage_fact_set` schema** at
   `src/novetest/models/coverage_fact_set.py`. This is the precedent
   for your future `regression_facts.json` schema — Regression composes
   Coverage's outputs, so your facts shape will rhyme with theirs.
3. **Write a `agent-comms/questions/regression-team-2026-05-25-charter-update.md`**
   proposing additions to your own charter (`.claude/agents/novetest-regression-team.md`).
   The question becomes PM's input for finalizing the charter (PM owns
   charter edits per the CEO-approved separation in
   `decisions/2026-05-14-team-structure-and-protocol.md`).

## Pre-flight reading (additional context for the question)

Beyond what your charter's activation checklist names:

- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
  Coverage's frozen schema decision. Pattern your `regression_facts.json`
  schema proposal after this shape.
- `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`
  + `2026-05-16-coverage-delta-envelope-shape.md` — Coverage's frozen
  CLI envelope shapes. Phase 3 will need similar `regression_outcome`
  and `regression_delta` envelopes; preview their structure.
- `agent-comms/decisions/2026-05-25-supported-engine-matrix.md` —
  binding constraint on adapter version handling (defensive parsing,
  no engine bundling).
- `agent-comms/history/2026-05-21-phase2-3-inspect-and-jest-coverage.md`
  + `2026-05-21-phase2-complete-and-ci-batch.md` — most recent Phase 2
  cycle learnings. The "inspect aggregated view" notes are especially
  relevant since Phase 3's DoD #3 is `inspect` populating the
  Regression section.
- `tasks/memory-team-2026-05-25-find-runs-for-target.md` (parallel
  task) — pins the Memory primitive your `resolve_latest_baseline` will
  consume.

## What the `charter-update` question MUST cover

Concrete sections your question proposes adding to your team charter:

### A. Conventions (expand the stub in section "Conventions")

The current charter says "Domain-specific conventions ... to be added
when activated." Propose at least these:

1. **Regression Facts schema sketch** — a concrete proposal for
   `regression_facts.json` layout. Mirror Coverage Facts (frozen
   dataclasses with slots, schema-versioned, hand-rolled
   `to_dict`/`from_dict`, per-pair file). Pin the directory layout (the
   charter already hints at
   `<store>/regression/pairs/run_<a>__run_<b>/regression_facts.json` —
   confirm or propose better).
2. **Baseline-pair identity** — given two runs A and B, what is the
   canonical ordering / persistence key? (Avoid ambiguity between
   `A→B` and `B→A`.) Coverage's `(baseline_run, target_run)` ordering
   is precedent.
3. **What goes into a Regression Fact** — per
   `regression.md`'s contract:
   - test-outcome transitions (pass→fail, fail→pass, new, removed,
     skipped→active, etc.)
   - native-output difference records (what shape? full diffs? hashes?
     references?)
   - Coverage-change records (when Coverage Facts exist for both runs)
   Propose a concrete dataclass tree.
4. **Outcome transition taxonomy** — closed enum of categories
   ("regressed", "fixed", "new_failure", "new_pass", "still_failing",
   "still_passing", "skipped"). Pin the spelling.
5. **Native-output diff strategy** — full text diff is large and noisy;
   a hash + sample-line approach may be lighter. Propose with rationale.
6. **Persistence write-time** — `derive_regression_facts` writes when?
   Lazy on first `regression compare` call? Eager during `run`?
   (Coverage chose lazy — recommend mirroring.)

### B. Reporting (expand the stub in section "Reporting back")

Coverage's handoff format precedent (see recent Coverage handoffs in
`agent-comms/history/`) — confirm or propose adjustments specific to
Regression slices.

### C. Open questions / risks you spotted

Anything you found while reading that needs PM/CEO decision before
implementation. Examples likely to come up:

- How "comparable" is defined when two runs share `target_expression`
  but differ in `engine_version` (e.g. user upgraded pytest between
  runs). Memory exposes `engine_version` per record; Regression should
  decide whether to compare across versions or require equivalence.
- Whether `compare_runs` should fail-soft (degrade to unavailable) or
  fail-hard when a referenced run is tombstoned.
- Whether Phase 4's Localization, which consumes your facts, has any
  shape constraints you should know about now.

## Files to write / modify

- **`agent-comms/questions/regression-team-2026-05-25-charter-update.md`**
  — the deliverable. Use the existing question format (frontmatter
  `from/to/type/status/created/slug` + body).

That's it. Nothing else.

## Files NOT to touch

- `src/novetest/regression/**` — DO NOT write code this cycle. The
  module is intentionally empty until the schema is frozen next cycle.
- `tests/**` — same reason; no tests for code that does not yet exist.
- `.claude/agents/novetest-regression-team.md` — your own charter is
  PM territory to *edit*; you *propose* via the question file. PM
  picks up the proposal and either edits the charter or routes it
  through a `decisions/` doc.
- `design/interace-contract/regression.md` + `design/workflows/regression.md`
  — these are binding contracts already. If you find a gap or
  inconsistency, raise it as a question; do not edit unilaterally
  (your charter says: "design/interace-contract/regression.md +
  design/workflows/regression.md" are in your owned list, BUT PM's
  convention is contract edits go through `decisions/` so all teams
  reading them agree).

## Verification

This task has no automated verification — it is a pure planning /
reading / writing slice. Your handoff should confirm:

- All 8 documents in the "Pre-flight reading" list were read.
- The `charter-update` question file is written, includes sections A,
  B, and C above, and is concrete enough that PM can act on it
  directly.
- No source / test / contract files were modified.

## Coding guidelines

Not applicable — no code in this slice. The Karpathy guidelines apply
in spirit: think before proposing (don't sketch schemas you cannot
defend), simplicity first (mirror Coverage's patterns unless a
specific Regression need justifies divergence).

## Reporting

Write `agent-comms/handoffs/regression-team-2026-05-25-activation.md`.

**No `WORKLOG.md` entry** — this slice touches no `src/` or `tests/`,
so the hook does not fire. The handoff is the record.

Run `python3 tools/regen_comms_index.py` and stage `INDEX.md` with the
new question file.

**DoD bullets believed closed:** **None.** No `delivery-phasing.md`
Phase 3 DoD bullet closes from team activation alone. State this
explicitly in the handoff.

## What happens next (so you have the full picture)

1. PM receives your `charter-update` question.
2. PM either (a) writes the charter additions directly, (b) routes the
   schema proposal through a `decisions/2026-05-XX-regression-facts-json-layout.md`
   for permanence (likely; this mirrors Coverage's precedent).
3. Next cycle dispatches your FIRST real implementation slice —
   typically `compare_runs` + facts persistence. Memory's
   `find_runs_for_target` (the parallel slice this cycle) is the
   prerequisite that will be in place by then.

So this activation cycle is intentionally low-pressure: read, study,
propose carefully. The next cycle's coding pace will pick up from
your foundation.

## Companion task (PM note — context)

The parallel `memory-team-2026-05-25-find-runs-for-target` task ships
your primary upstream primitive. Zero file-area overlap; you both run
to completion independently and PM bundles into the cycle-cleanup.
