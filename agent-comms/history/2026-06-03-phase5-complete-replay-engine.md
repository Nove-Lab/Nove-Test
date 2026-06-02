---
from: novetest-pm-team
to: all
type: history
created: 2026-06-03
slug: phase5-complete-replay-engine
related:
  - agent-comms/history/2026-06-02-phase1-and-phase6-complete-recommendation-synthesis-lands.md
  - agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md
  - design/implementation-plan/delivery-phasing.md
  - design/interace-contract/replay.md
  - design/workflows/replay.md
---

# History: 2026-06-03 cycle — **Phase 5 lands; v1 recommendation surface fully real-data-activated; MVP scope reduces to two Open-Q-gated adapters + MCP**

Solo Replay-team cycle. Verdict **passed**. This slice closes the
**3 Phase 5 DoD bullets** (`delivery-phasing.md:221-223`) AND completes the
**v1 recommendation surface** by activating the `flaky_suspected` category
against real `ReplayResult` data (was mock-only since Phase 6 entry
2026-06-02).

**Phase 5 → 100% complete.** After this cycle, MVP scope reduces to
**Phase 3 JUnit** (Open Q #5) + **Phase 3 .NET** (Open Q #4) + **Phase 7
MCP** (post-MVP). Both Phase-3 adapter gates require CEO investigation
on Console Launcher vendoring policy + Coverlet PerTestCoverage config
key; once those are resolved + their slices ship, the project is
**release-ready**.

## Slice in scope

| Team | Commit | Verdict |
|---|---|---|
| Replay (Phase 5 entry) | `4e81d53` | passed |

Lineage: PM brief queued (`377a92f` 2026-06-02) → SQLite deferral docs
sweep + decision (`0f69181` 2026-06-02) → Replay team code (`4e81d53`
2026-06-03) → handoff (`904ee0d`) → Main Branch FF-merge → verification
(`0950d60`) → Manual Test findings.

## What shipped

### 1. 5 Replay internal APIs + canonical `ReplayResult` model

`src/novetest/replay/` was an empty module before this slice; now it ships
the 5 binding interfaces per `design/interace-contract/replay.md`:

- `replay_run(store, original_ref, *, reruns, timeout) -> ReplayResult | ReplayUnavailable`
- `reconstruct_replay_context(store, original_ref) -> ReplayContext | ReplayUnavailable`
- `classify_replay_consistency(original_record, replayed_records) -> ReplayResult` (pure)
- `get_replay_result(store, original_ref) -> ReplayResult | ReplayUnavailable` (cache-only)
- `check_replay_availability(store, original_ref) -> bool`

Module layout: `engine.py / context.py / classifier.py / persistence.py
/ retrieval.py / errors.py / __init__.py` mirroring
`coverage/` and `localization/`.

`ReplayResult` model promoted from the fact_bundle.py transient
placeholder (Phase 6 entry §"Replay placeholder") to canonical
`src/novetest/models/replay_result.py`. Wire shape byte-identical;
existing `from ...fact_bundle import ReplayResult` continues working
via re-export. The team shipped all **5 binding minimum fields** plus
**all 5 recommended optional fields** (`replayed_run_reference`,
`per_rerun_outcomes`, `consistency_summary`, `attempted_at`, `reason`).

### 2. `novetest replay <run_id>` CLI verb

Replaces the flat stub at the old `cli/app.py:1182`. Exit code map per
brief §5.3 (with Replay team's judgment on the structured-vs-error split):

| Outcome | Exit |
|---|---|
| `ReplayResult` (any classification incl. `unable_to_replay`) | 0 |
| `ReplayUnavailable(engine-not-ready / target-missing)` | 4 |
| `ReplayUnavailable(original-not-found)` | 2 |
| `ReplayUnavailable(tombstoned-original / context-reconstruction-failed / missing-derived-facts)` | 0 (`kind: unavailable` structured outcome) |

The **load-bearing design clarity**: `unable_to_replay` is a **valid
classification at exit 0** (REQ-REP-003 discipline), NOT an error.
Tombstoned originals and context-reconstruction failures also exit 0
with `kind: unavailable` because they are structured non-error outcomes
— the product is honest about what it cannot reproduce, AI agents can
distinguish "cannot reproduce because X" from "tool failed".

### 3. `flaky_suspected` category activates for real

Phase 6 entry shipped `categories.py::match_flaky_suspected` with
mock-only test coverage (`tests/unit/orchestration/recommendation/test_categories.py::TestFlakySuspected`).
This slice closes the gap via
`tests/integration/replay/test_flaky_suspected_synthesis.py` — a real
`flaky-python` Run → `replay_run(reruns=5)` → `build_fact_bundle(replay_result=<inconsistent>)` →
`synthesize_recommendation` produces a real `flaky_suspected`
recommendation with a `kind: "replay_result"` citation that round-trips
via `get_replay_result(store, original_ref)` byte-identically
(NFR-ORCH-002 evidence).

**The v1 recommendation surface is now fully real-data-activated.** All
7 categories of the closed taxonomy (`regression_with_localization`,
`investigate_location`, `investigate_regression`, `coverage_gap`,
`flaky_suspected`, `unavailable_analysis`, `all_green`) can fire
against real data.

### 4. `status` / `inspect` Replay surface activates

- `status.sub_reports.replay` flips from hard-coded `"unavailable"` to a
  cache-only `isinstance(get_replay_result(...), ReplayResult)` probe.
- `inspect.replay_outcome` adds a discriminated `kind: "replay-result" |
  "unavailable"` block carrying the full `ReplayResult.to_dict()`
  projection (identical wire shape to `novetest replay`'s
  `data.replay_outcome`).
- `MemoryEntry.has_replay_result` flag flips true for runs carrying a
  persisted `replay_result.json`.

### 5. `flaky-python/` fixture (deterministic-within-process, divergent-across-processes)

`tests/fixtures/projects/flaky-python/` ships a single flaky test
backed by an on-disk parity counter at `.flaky_invocations`:
- Each subprocess reads the counter once, increments, decides outcome
  based on parity.
- Within a single subprocess: deterministic (so the original run's
  storage is byte-identical to its execution).
- Across subprocesses: divergent (so reruns alternate fail/pass).

This is a **clean reusable pattern** for future flake fixtures —
deterministic-within-process + divergent-across-processes is the
correct shape for any test that needs to capture an original run AND
exhibit divergence on replay.

### 6. Numbers

| Metric | Baseline (`377a92f`) | This slice (`4e81d53`) | Delta |
|---|---|---|---|
| Default-suite pytest | 871 + 5 skipped | 949 + 5 skipped | **+78 net tests** |
| mypy --strict src files | 80 | 87 | +7 |
| Source line delta | — | ~+1100 lines src | — |

## DoD bullets ticked in `delivery-phasing.md`

- **Phase 5 line 221** — `novetest replay <flaky_id> --reruns=5` → `inconsistent`
- **Phase 5 line 222** — `novetest replay <basic_id>` → `reproducible`
- **Phase 5 line 223** — vanished target → `unable_to_replay`

**Phase 5 → 100% complete.**

## Phase progress map after this cycle

| Phase | Status | Notes |
|---|---|---|
| 0 — Foundations + install | ✅ 100% | Closed 2026-05-16 |
| 1 — Onboarding + Run + Memory | ✅ 100% | Closed 2026-06-02 |
| 2 — Coverage | ✅ 100% | Closed 2026-05-21 |
| 3 — Regression | ✅ 100% (core) | JUnit/.NET adapters Open-Q-gated; separate cycles |
| 4 — Localization | ✅ 100% | Closed 2026-06-01 |
| 5 — Replay | ✅ 100% | **Closed 2026-06-03 (this cycle)** |
| 6 — Recommendation synthesis | ✅ 100% | Closed 2026-06-02; v1 surface now fully real-data-activated by this slice |
| 7 — MCP transport | ❌ 0% | post-MVP |

Plus deferred engine adapters:
- Phase 3 JUnit (Open Q #5: vendor vs download Console Launcher)
- Phase 3 .NET (Open Q #4: Coverlet PerTestCoverage config key)

## Product framing — what just shipped

Before this cycle, the Replay engine module was empty; `novetest
replay` was a stub. The `flaky_suspected` recommendation category
existed but only fired against mock `ReplayResult`s in unit tests.

After this cycle, three real-world questions the CLI now answers
cleanly:

1. **"Is this test actually flaky, or did I just imagine it?"** →
   `novetest replay <run_id> --reruns 5` → `inconsistent` + citation
   back to the divergent test's run_reference.
2. **"Was that green run deterministic, or did I get lucky?"** →
   `novetest replay <run_id> --reruns 3` on a clean fixture →
   `reproducible`.
3. **"My test files vanished — can I still replay?"** →
   `unable_to_replay` + `reason: "replay-run-errored"` at exit 0.
   Product is honest about what it cannot reproduce.

Combined with the Phase 6 entry's `novetest test [target]` integrated
workflow, the user-facing surface is now: a single command answers
"what failed, why, and is it real?" with cited evidence.

## §6 Replay team policy decisions (delegated; v2-bumpable)

PM's Q3 default disposition (delegate to Replay team's construction
judgment + record reasoning in handoff) paid off. The team shipped
three principled decisions:

1. **`--reruns` default = 1.** Cheapest single replay; matches the
   `novetest replay <basic>` example with no flag. `--reruns 5` is the
   explicit flake-investigation idiom. Alternatives considered: default
   5 (better UX for flake investigation) — rejected to keep the default
   cheap; the team rejected the assumption that "users invoking replay
   are always investigating flake" because reproducibility checks can be
   single-rerun.
2. **Classifier threshold = strict** (any divergent rerun →
   `inconsistent`). The user's question is binary; one flake answers
   "no". Alternatives considered (majority / per-test /
   all-or-nothing) — rejected for ambiguity.
3. **`flaky-python` non-determinism = on-disk invocation counter**
   (`.flaky_invocations` at project root). Deterministic within a
   process (read once), divergent across subprocesses (counter
   persists). Alternatives considered (`os.getpid() % 2`, unseeded
   `random`) — rejected because they break the original-run capture
   reproducibility (a captured original might fail to re-serialize
   byte-identically) and could introduce CI flakiness in the test
   itself.

## Closed enum vocabulary as shipped

For future cross-references:

- **`ReplayResult.classification`**: `{reproducible, inconsistent, unable_to_replay}` (REQ-REP-003 closed enum, unchanged from spec).
- **`ReplayResult.reason`** (populated only when classification is `unable_to_replay`): `{no-replayed-runs, replay-run-errored}` (2-value enum).
- **`ReplayUnavailable.reason`**: `{original-not-found, tombstoned-original, context-reconstruction-failed, engine-not-ready, target-missing, missing-derived-facts}` (6-value enum).

The clear separation of `ReplayResult.reason` (within-classification
sub-cause) from `ReplayUnavailable.reason` (engine-level inability)
keeps the discriminator boundary clean.

## Sub-observations (all doc-side imprecision; non-defect)

Manual Test surfaced 3 sub-observations, all verification-doc copy-edit
matters with NO slice defect:

### Sub-obs #1 — Edge 7 parity-drift wording imprecision

Verification doc Edge 7 claimed "the second `novetest replay`
invocation against the same workspace will see a different
`per_rerun_outcomes` pattern." Empirically, this is only true when
starting-counter parities differ. With both starting counters odd (1
and 7), the per-rerun patterns matched byte-identically. The important
contract — "still divergent → still `inconsistent`" — held.
**Disposition**: verification-doc copy-edit point; future docs should
say "**will still classify `inconsistent`**, though the
`per_rerun_outcomes` pattern may or may not differ depending on the
parity of the new starting counter."

### Sub-obs #2 — Memory.delete envelope shape note (informational)

The verification doc said "novetest memory delete <run_id> (or
whatever the equivalent tombstone path is)..." with mild uncertainty.
Empirically the verb is exactly `novetest memory delete <run_id>`
and the tombstone is at
`data.memory_entry.run_record.metadata.tombstoned_at` + `status ==
"tombstoned"`. **Disposition**: informational, no code change.

### Sub-obs #3 — `inspect.replay_outcome` carries full projection

Verification doc Scenario G pinned 5 fields under `inspect.replay_outcome`;
actually the block carries the **full** `ReplayResult.to_dict()`
projection (10+ fields), matching the `cli/app.py::_replay_outcome_payload`
docstring's "identical wire shape to novetest replay" claim.
**Disposition**: doc-listed pins are a subset of the actual block;
future verification docs should reference "see Scenario B for the full
field list" rather than enumerating a subset.

## The non-obvious story — `unable_to_replay` is data, not error

The temptation when designing Replay would be to map "cannot
reproduce" to a non-zero exit code or an error envelope. REQ-REP-003
disciplines this: `unable_to_replay` is a **valid classification** of
the Replay Result.

The team's implementation respects this: `unable_to_replay` exits 0
with `ok: true` and a structured `replay_outcome.classification:
"unable_to_replay"` block. Tombstoned originals and
context-reconstruction failures ALSO exit 0 with `kind: "unavailable"`
because they are structured non-error outcomes (the engine has a
definite answer: "this particular original cannot be replayed because
its workspace state is incompatible").

The CLI-level errors (exit 2/4) are reserved for **user errors** (bad
run_id, missing engine in the environment) where the user can act on
the message to fix the invocation.

**Lesson for future engine designs**: the distinction between "the
system has a definite classification of X" (data, exit 0) vs "the user
made a mistake" (error, exit 2/4) is a binding product clarity
decision. REQ-REP-003 made this distinction at the requirements layer;
the implementation honored it. AI agents reading the envelope can
correctly distinguish "this run cannot be reproduced because <reason>"
from "novetest failed". This is the product surface delivering on its
binding promise.

## Forward-looking parking lot (from handoff + findings — non-blocking)

PM disposition for each:

### PL1 — `--threshold majority` flag

The strict classifier (any divergence → inconsistent) may be noisy on
heavy-concurrency hosts where transient environmental flakiness
produces low-rate divergence that isn't actionable flake. A v2 surface
`--threshold majority` (>50% match original → reproducible) would let
users tune sensitivity. **Disposition**: v2 carry-forward, not queued.
Cheap to add when an actual user complaint surfaces. Pinned here so
future PM doesn't re-investigate from scratch.

### PL2 — Integrated `novetest test` auto-Replay

Currently `novetest test` keeps `replay_result=None` — `flaky_suspected`
only fires via explicit `novetest replay` invocation or the Python
synthesizer API. Whether `novetest test` should auto-invoke Replay for
flaky-looking runs is a separate UX scoping question (extra cost vs
extra value; failed-test-only retry vs all-test retry; etc.).
**Disposition**: deferred to a future UX-focused cycle. Not blocking
MVP release. Pinned here.

### PL3 — Cross-run aggregation verb (the original Phase 5 SQLite
trigger)

`decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`
recorded the deferral. If a future scoping cycle introduces a verb
like `novetest memory flakiness <nodeid>` (per-test cross-run history),
that's the moment the SQLite decision re-opens. **Disposition**: no
timeline; deferred until a user need or roadmap addition explicitly
surfaces it.

## Process notes

### Brief's pre-frozen contracts paid off (again)

The Phase 5 entry brief (748 lines, 40 KB) used the same pre-design
discipline as the Phase 6 entry brief: binding contracts in §1
(ReplayResult shape, 5 API signatures, workflow sequence, envelope
shape, exit codes) frozen BEFORE dispatch, delegated decisions in §6
(reruns default, threshold, fixture non-determinism) explicitly marked
as construction judgment. The team translated binding contracts to
code in ~1 day and exercised judgment on the §6 decisions only.

**Pattern validated**: closed pre-design for binding contracts +
explicit delegation of construction judgment items + handoff requirement
to capture reasoning for delegated decisions. This is the project's
mature pattern for substantial slices.

### Replay team's three §6 decisions were principled

The team rejected each obvious alternative with concrete reasoning
(documented in handoff §"Policy decisions"). The rejection reasons
themselves are useful design artifacts — they prevent a future cycle
from re-litigating the same trade-off without surfacing new evidence.

### Manual Test surfaced only doc-side imprecision

Second cycle in a row where Manual Test surfaced only verification-doc
copy-edit matters (no slice defects). This is a healthy sign: the
brief pre-design + the team's translation + Main Branch's verification
doc are well-aligned. The remaining doc imprecision is at the
"natural-language description of an empirical observation" layer
(parity drift, field enumeration subset), not at the contract
boundary.

**Lesson** (already pinned in 2026-06-02 history Process notes; still
applies): Main Branch verification docs should describe contracts ("the
classification will be inconsistent") rather than empirical incidentals
("the per-rerun pattern will be different") whenever possible. Pure
empirical descriptions are correct only modulo the input distribution.

### SQLite deferred — proven correct in retrospect

The 2026-06-02 decision to defer SQLite (Open Q #19 deferred-closed)
was validated by this slice: Replay engine ships without touching
SQLite, NFR-REP-002 met with margin (sub-millisecond classifier +
persist), no scope creep. `grep -rn "sqlite3\|index.db"
src/novetest/replay/` returns empty. The "file-only first; SQLite when
the query pattern actually surfaces" philosophy from `foundations.md`
§4 held under stress.

## What's next

After this cycle, MVP scope is **only** Phase 3 JUnit (Open Q #5) +
Phase 3 .NET (Open Q #4) + Phase 7 MCP (post-MVP).

The two Phase-3 adapter cycles are **Open-Q-gated** — they require CEO
investigation:
- **Open Q #4**: Coverlet PerTestCoverage exact configuration key in
  the version we pin (vendor docs + Coverlet PR history needed).
- **Open Q #5**: JUnit Platform Console Launcher distribution policy
  (vendor jar vs download-on-first-use vs require-on-PATH).

Once those Open Qs are resolved + their slices ship, the project is
**release-ready**. Phase 7 MCP is post-MVP territory.

PM's recommendation for the next cycle:
- **(a)** CEO investigates Open Q #4 + #5; PM scopes JUnit + .NET
  adapter cycles in parallel afterward.
- **(b)** **OR** the project considers an interim release with
  pytest+jest+gotest+cargo as the four supported ecosystems (the
  decision `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  family already accepts this pattern of supporting fewer ecosystems
  with stronger guarantees). JUnit + .NET become post-MVP adds.
- **(c)** OR backlog cleanup — the 12-item list from
  `2026-06-02 history §"Other deferred items"` (Defect 7,
  snapshot expansion, Memory delete polish, peak-RSS smoke, etc.)
  could occupy a parallel polish cycle.

Decision is CEO's. None of (a)/(b)/(c) blocks the others.

## Other deferred items (visible to future PM)

Carry-forward from the 2026-06-02 history (Phase 1 + Phase 6 closure)
that this slice did NOT touch:

1. **Phase 3 JUnit** — Open Q #5 blocks brief
2. **Phase 3 .NET** — Open Q #4 blocks brief
3. **Phase 7 MCP transport** — post-MVP
4. **v2 recommendation_schema** design cycle — Q1 (score floor) + Q2
   (drop redundant unavailable_analysis) + PL1 (--threshold flag)
5. **`handlers/` package migration** — working policy: inline by
   default, extract when ≥80 lines or ≥3 envelope outcomes
6. **`inspect.recommendations` field** — deferred
7. **Defect 7** (`failure_proximity` warning loop) — low priority
8. **Regression engine `fixed_tests` clarification**
9. **UX normalizations** (metadata shape + path absoluteness)
10. **Memory `delete` polish** — long-standing carry-forward
11. **Envelope freeze v2 amendment** for `failure_proximity` deviation
12. **Peak-RSS smoke assertion** for NFR-LOC-002 perf benchmark
13. **Slow-CI host sampling** for NFR-LOC-002
14. **Snapshot coverage expansion** to all fixtures
15. **Replay envelope syrupy snapshot** with ULID scrubber (new — handoff §"Open items")
16. **Dead `_register_flat_stub` / `_register_group_stub` / `_make_stub` helpers in cli/app.py** — now unused; harmless, mypy-clean; remove in a cleanup cycle (new — handoff §"Open items")
17. **Integrated `novetest test` auto-Replay (PL2)** — UX scoping cycle
18. **Cross-run aggregation verb (PL3)** — reopens SQLite decision
