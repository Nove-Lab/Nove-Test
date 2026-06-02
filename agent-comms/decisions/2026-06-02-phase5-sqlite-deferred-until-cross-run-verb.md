---
from: novetest-pm-team
to: all
type: decision
created: 2026-06-02
slug: phase5-sqlite-deferred-until-cross-run-verb
related:
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/index.md
  - agent-comms/history/2026-06-02-phase1-and-phase6-complete-recommendation-synthesis-lands.md
supersedes_questions:
  - delivery-phasing.md Open Q #19 (Phase 5 SQLite schema + rebuild trigger)
---

# Decision: Phase 5 SQLite cache is deferred until a cross-run aggregation verb lands

## Context

Three design docs (`foundations.md` §4 "Phase 5 SQLite cache (forward note)",
`delivery-phasing.md` Phase 5 "Persistence" paragraph, `index.md` Decisions
Snapshot Persistence row) all predicted that Phase 5 would be the first
sub-product to introduce a derived SQLite index at `.novetest/memory/index.db`.
The predicted trigger query was **per-test cross-run history** — "for nodeid
X, what was its outcome in the last 50 runs?" — and the design rationale
attached this query to Phase 5's Replay flakiness detection.

`agent-comms/decisions/` carried no binding decision file for the SQLite
introduction itself; all three doc statements were **design intent**, not
frozen contract. Open Q #19 was open against Phase 5 entry and explicitly
asked for schema (`run` + `test_outcome` tables) and rebuild trigger (lazy /
explicit `novetest reindex` / both).

On 2026-06-02 (planning the Phase 5 entry cycle), PM re-examined whether
Phase 5's actual binding requirements truly require this query pattern. The
finding:

- All three Phase 5 DoD bullets (`--reruns=5` → `inconsistent`,
  `pytest-basic` → `reproducible`, missing target → `unable_to_replay`) are
  satisfied by **single-pair comparison + in-session N-rerun classification**.
- NFR-REP-002 ("classification within 3 s after replay execution run record
  becomes available") is dominated by native test cold-start cost; SQLite
  has no bearing on it.
- `classify_replay_consistency(original_run_reference, replayed_run_reference)`
  is a two-record comparison, not a cross-run aggregation.
- The `flaky_suspected` recommendation category trigger reads a single
  `ReplayResult` produced by the in-session classification; it does not
  consume cross-run history.
- No currently-shipped or currently-planned CLI verb requires "for nodeid X,
  outcomes in the last N runs". Such a verb might appear post-MVP (e.g.
  `novetest memory flakiness <nodeid>`, a `flake-rate` field on `inspect`,
  or a "regression trend" verb), but none of those is on the MVP roadmap.

The previously-shipped engines also do not generate this query pattern:

- Regression (`compare_runs`, `resolve_latest_baseline`) is **pair-compare +
  latest-N walk**, served O(1) by the ULID-derived path layout.
- Memory (`retrieve_run_evidence`, `list_run_history`) is **point lookup +
  reverse-chronological walk**, served O(1)/O(N) by the same layout.
- Coverage / Localization / Replay all read at single-run granularity.

Therefore the design-doc prediction was premature: Phase 5 does **not**
surface the cross-run aggregation query pattern that justifies a SQLite
derived index.

## Decision

1. **Phase 5 ships the Replay engine only.** No SQLite index is introduced
   in the Phase 5 entry slice. `.novetest/memory/index.db` is not created.
   No `memory/migrations/` directory is added.

2. **The SQLite forward-note settings stay in `foundations.md` §4 unchanged.**
   When a cross-run aggregation verb is eventually added (post-MVP, no
   binding date), the WAL / `synchronous=NORMAL` / `busy_timeout=5000` /
   `foreign_keys=ON` / `BEGIN IMMEDIATE` / stdlib `sqlite3` / no-ORM /
   `index_schema_version` independent of `record.json` `schema_version` /
   rebuildable-via-`novetest reindex` settings remain the binding design
   intent for that day. They are kept as a forward note, not deleted.

3. **`Phase 5` references in the three design docs are rewritten** to:
   "deferred until a cross-run aggregation verb lands." No specific
   future phase is named.

4. **Open Q #19 is deferred-closed**, not answered. Schema (run +
   test_outcome) and rebuild trigger (lazy / explicit / both) are
   re-opened when the first cross-run aggregation verb scoping cycle
   begins. PM's working preference (recorded for that future cycle, not
   binding): **minimal schema** (run + test_outcome only) + **both
   triggers** (lazy AND explicit `novetest reindex`).

## Consequences

- Phase 5 entry brief scopes to Replay engine only. No SQLite scope creep.
- Phase 5 → 100% complete once Replay engine ships (3 DoD bullets +
  `flaky_suspected` mock-test → real-test transition + `delivery-phasing.md`
  lines 221-223 tick).
- After Phase 5, MVP scope reduces to: Phase 3 JUnit + Phase 3 .NET
  (both Open-Q-gated) + Phase 7 MCP (post-MVP).
- A future cross-run aggregation verb (e.g. `novetest memory flakiness`)
  re-opens this decision and triggers the SQLite introduction cycle. That
  cycle will write a new decision file referencing this one.

## Binding philosophy preserved

This decision keeps `foundations.md` §4's binding philosophy intact:
**"Why file-only first"** is the project's persistence-introduction
discipline. SQLite is introduced when the actual query pattern surfaces,
not when a forecasted query pattern *might* surface. This decision
corrects a design-doc forecast (SQLite at Phase 5) that the actual
Phase 5 binding requirements did not justify.
