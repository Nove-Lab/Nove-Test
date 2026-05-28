---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-05-28
slug: localization-engine-complete
related:
  - agent-comms/decisions/2026-05-28-localization-finding-shape.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - agent-comms/history/2026-05-28-gotest-adapter-and-localization-phase4-entry.md
  - agent-comms/history/2026-05-27-phase3-regression-engine-complete.md
  - design/interace-contract/localization.md
---

# History: Phase 4 Localization engine surface 100% complete (cycle close 2026-05-28)

## What shipped this cycle

Single-team slice (Localization team) added the four remaining engine
items on top of the Phase 4 entry surface shipped earlier the same day:

- Item 1: `REASON_MISSING_DERIVED_FACTS` split (`run_not_analyzable`
  overload narrowed; cache-empty now routes to the new reason).
- Item 2: `LocalizationUnavailable.to_dict()` 3-key serializer.
- Item 3: `resolve_latest_analyzable_run(store) -> RunReference | LocalizationUnavailable`.
- Item 4: `derive_latest_localization(store, *, formula, top_n) -> LocalizationFinding | LocalizationUnavailable`.

4 src modules edited (no new src files — `derive.py` extended per the
brief), **+25 net new tests** (11 to_dict + 9 latest-resolution unit +
2 latest-resolution integration + 3 results closure expansion, plus 1
retrieval-test reroute). Commit `8ec124a`; verification `5731f5d`
(`status: record-only`, Manual Test waived — engine-only, no
user-facing surface). pytest **611 passed + 5 skipped** (worktree
base `0c76a21`: 586+5), mypy clean 69 source files (`--strict`,
unchanged).

## Milestone — `design/interace-contract/localization.md` Internal table 100% covered

This is the load-bearing fact future agents need to know.

All 5 Internal-row entry points are now implemented and re-exported
from `novetest.localization`:

| Row | Function | Shipped in |
|---|---|---|
| 1 | `derive_localization_findings` | `bbb0356` (Phase 4 entry, 2026-05-28 earlier) |
| 2 | `resolve_latest_analyzable_run` | `8ec124a` (this cycle) |
| 3 | `derive_latest_localization` | `8ec124a` (this cycle) |
| 4 | `get_localization_findings` | `bbb0356` |
| 5 | `check_localization_availability` | `bbb0356` |

The 2 External rows (`novetest localization <run_id>` /
`novetest localization latest`) are pure CLI projection — Orchestration
team's territory for the next cycle.

**Implication for future work:** no further Localization engine surface
is needed until the post-CLI degraded-mode slices (`sbfl_aggregate`,
`failure_proximity`) land. The CLI cycle is pure projection — it
consumes these five entry points and emits envelope shapes
(`localization_outcome` discriminated by `kind`, same pattern Coverage
and Regression follow). After that ships, PM freezes the
`localization_outcome` envelope shape — same ship → field-test → freeze
cadence the project has now applied four times consecutively.

## Cycle-close artifact — first v2 supersede in the project

This cycle produced the first **v2 supersede** of a decisions/ entry:

- v1: [`2026-05-28-localization-finding-shape.md`](../decisions/2026-05-28-localization-finding-shape.md)
  — pinned 7 schema items at freeze time, but explicitly left §6 (the
  `LocalizationUnavailable.to_dict()` "known gap") and §X (the
  `REASON_MISSING_DERIVED_FACTS` split) as deferred-but-decided.
- v2: [`2026-05-28-localization-finding-shape-v2.md`](../decisions/2026-05-28-localization-finding-shape-v2.md)
  — closes both gaps with binding contracts. All non-superseded
  clauses of v1 carry forward unchanged.

The mechanic: **v1 retains a forward-pointer callout at the top
("SUPERSEDED 2026-05-28 by v2 — ..."), the bottom "Supersedes" section
stays accurate ("None. First decision on the Localization Finding
shape."), and v2's "Supersedes" section is the canonical pointer
backward.** Future v2 supersedes in this codebase should follow this
pattern.

## Load-bearing learnings

### 1. New cycle pattern — ship → field-test → freeze v1 (with open §X) → implement §X → freeze v2

The ship → field-test → freeze cadence applied 3 times prior to this
cycle (Coverage 2026-05-16; Regression facts 2026-05-26; Regression
envelope + Localization v1 both 2026-05-28). All three landed as
single-decision freezes — no follow-up supersede needed.

Localization is the first engine where a freeze decision explicitly
deferred items to a follow-up implementation slice + v2 supersede:

```
Phase 4 entry (bbb0356) → Manual Test field → v1 freeze (with §X / §6 open) → engine completion (8ec124a) → v2 freeze
```

The pattern works cleanly and is reusable. Future engines may want it
when the freeze decision needs to ship before the full engine surface
is finalized (e.g. Phase 5 Replay's derived-SQLite + Memory join could
benefit from this).

**When to use it:** if Manual Test fields the engine and freezing
prevents schema drift downstream BUT engine semantics will refine in
1–2 follow-up slices, freeze v1 with explicit `§X. Open refinement`
sections naming each deferred item. Land the refinements as engine
slices. Close with a v2 supersede that pins the final shape.

**When NOT to use it:** if the freeze can wait until the engine
surface is 100% — then a single v1 is cheaper.

### 2. `status: record-only` is now a stable 3-application convention

Three consecutive engine-only slices have used
`status: record-only` to waive Manual Test:

- `2026-05-26-phase3-regression-engine-and-memory-probe.md`
- `2026-05-27-phase3-regression-engine-complete.md`
- `2026-05-28-localization-engine-completion.md` (this cycle)

The pattern is durable enough that a formal `decisions/` entry could
codify it, but the three-history-doc precedent is sufficient for
pattern matching. Main Branch picked up the convention cleanly this
cycle — handoff explicitly stated "no Manual Test action requested",
Main Branch's verification mirrored with `status: record-only`. No
charter edit needed.

### 3. Main Branch push-omission watch — recovery streak holds

Per the escalation log from
`2026-05-27-phase3-regression-engine-complete.md` §2: Main Branch's
push omission was observed in 2 consecutive cycles (2026-05-26 +
2026-05-27), then negative-confirmed in 2026-05-28's parallel cycle
(`8e013d0`). **This cycle is the second consecutive recovery** —
Main Branch pushed both `8ec124a` and `5731f5d` at the natural close
point.

Status: 2 observations, 2 consecutive recoveries. The pattern is no
longer a structural watch. PM pre-flight step-0 continues to backstop
either way.

**Minor charter drift observed this cycle (separate from the push
issue):** Main Branch's verification body text reads "Push status:
Awaiting CEO authorization" but the commit IS already on origin/main.
Template stale text — Main Branch wrote the verification before the
push happened, then pushed without updating the boilerplate. Not a
structural defect; flagging here so the next agent picking up Main
Branch knows to update the "Push status" section AFTER the push, not
before. If it appears again, consider a `GOTCHAS.md` entry.

## Pinned PM-decisions in v2 (deviations resolution)

Two minor deviations from the brief surfaced in the handoff; both
resolved in v2 as "pinned as-is, no code change":

1. **`derive_latest_localization` kwargs ordering** — v2 §D pins
   both functions' current declarations. Both `formula` and `top_n`
   are keyword-only post-`*`, so Python keyword binding makes the
   order functionally irrelevant. CLI exposure via `--formula` /
   `--top-n` makes it invisible to users. No reconcile.
2. **`resolve_latest_analyzable_run` N count includes tombstoned
   entries** — v2 §C pins this as the binding semantic. User-facing
   meaning is "I tried N times and none worked", which is what the
   semantic delivers correctly. Filtering tombstoned runs lives
   inside `check_localization_availability` and is correctly opaque
   to the resolver.

## Worktree / branch hygiene

The `novetest-localization-engine-completion` worktree + branch were
cleanly merged via fast-forward (verification §"Conflict-resolution
notes during merge": "None. The merge was a clean fast-forward — base
commit `0c76a21` matched main's tip exactly"). No preservation needed
per `2026-05-25-duplicate-merge-cycle.md` §3's "no loss" framing.

## What the next cycle is

**Orchestration team CLI verb cycle** — closes Phase 4 DoD bullets §4
#1, #2, #4 in one sweep (mirroring the Phase 3 Regression CLI cycle
pattern at `c074226`).

Surface to ship:
- `novetest localization <run_id>` (CLI verb, projects
  `derive_localization_findings` + `get_localization_findings` onto an
  envelope).
- `novetest localization latest` (projects
  `derive_latest_localization`).
- `inspect` Localization section (reuses the same envelope projection
  for the aggregated view).
- `--formula <name>` CLI flag (selects the primary scoring formula
  presented in `score_raw` / `rank`; `alternate_scores` carries the
  others per v1 §2 unchanged).
- `--top-n <int>` CLI flag (overrides the default `top_n=10`).
- `localization_outcome` envelope block, discriminated by `kind:
  "fact-set" | "unavailable"`, mirroring Coverage and Regression.

After Manual Test fields it, PM writes the
`localization_outcome` envelope shape freeze decision — same pattern as
the four prior freezes.

Phase 4 DoD #3 (NFR-LOC-002 perf — 500 failed tests + 50k covered
locations within 8s) closes in a separate perf cycle, not tied to the
CLI sweep. Phase 4 totals: 1 CLI sweep + 1 perf cycle = 2 cycles to
close all 4 Phase 4 DoD bullets, assuming no surprises.

## Other deferred items (informational, unchanged from prior history)

- **Phase 3 adapter completion** (cargo + JUnit + dotnet) — blocked
  on Open Questions #3/#4/#5 per delivery-phasing.md. PM should raise
  these to CEO before queueing the slice.
- **Memory `delete` CLI workflow polish** — small-surface follow-up
  flagged by Manual Test on the prior Regression cycle.
- **`go-test` row in supported-engine-matrix** — bundle with Phase 3
  adapter completion.
- **Q4 `engine-engine-missing` polish** — bundle with Phase 3 adapter
  completion.

## Velocity snapshot

Last 7 closed cycles (chronological):
- Phase 3 Regression engine entry (`9c7979244`)
- Phase 3 Regression engine + Memory probe (`b32084d` ×2)
- Phase 3 Regression baseline resolution (`b32084d`)
- Phase 3 Regression CLI sweep (`c074226`) — closed Phase 3 DoD 3/3
- gotest adapter + Localization Phase 4 entry parallel (`adf7bac` +
  `bbb0356`)
- Localization engine completion (this cycle)

Phase 4 entry to engine-complete in 1 same-day cycle. Phase 4 closure
projected within 2 cycles. Project velocity is high; the operating
discipline (freeze cadence, record-only convention, parallel dispatch,
PM pre-flight step-0) is mature enough to sustain.
