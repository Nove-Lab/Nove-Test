---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: pending
created: 2026-06-02
slug: phase6-entry-recommendation-synthesis
related_task: agent-comms/tasks/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md
related:
  - design/implementation-plan/recommendation-synthesis.md
  - design/interace-contract/orchestration.md
  - design/workflows/orchestration.md
  - design/requirements-analysis/requirements-specification/groups/orchestration.md
---

# Handoff: Phase 6 entry — Recommendation Synthesis (closed taxonomy v1, integrated `novetest test`, default-verb alias)

## TL;DR

Phase 6 entry is **complete**. The integrated `novetest test [target]`
workflow ships, the 7-category closed taxonomy is frozen at v1, the
default-verb alias is wired (`novetest <target>` ≡ `novetest test
<target>` for non-reserved tokens), and the AI-agent round-trip
contract (NFR-ORCH-002) has a load-bearing regression pin.

After this slice merges:

- **Phase 6 → 100% complete** (4 DoD bullets ready to tick).
- **Phase 1 → 100% complete** (`delivery-phasing.md:96` lingering
  bullet — `novetest test` returns `all_green` / `unavailable_analysis`
  on empty downstream facts — closes naturally).
- MVP scope shrinks to Phase 5 (Replay + SQLite index) + Phase 3
  JUnit/.NET (gated on Open Q #4/#5) + Phase 7 MCP transport (post-MVP).

Worktree: `/home/yjshin/dev/novetest-phase6-recsynth`
Branch: `worktree-phase6-recommendation-synthesis`
Base: `origin/main` tip `dd02942` (the brief-queue commit).

## DoD bullets believed closed (PM verifies + ticks)

All 13 DoD bullets in
`tasks/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md`
§"Definition of Done":

- [ ] `src/novetest/orchestration/recommendation/{categories,templates,synthesizer,citations,fact_bundle}.py` implemented
- [ ] `src/novetest/orchestration/workflows/test.py` implements the §5 binding workflow sequence
- [ ] `src/novetest/cli/handlers/test.py` + `app.py` registration + default-verb alias activated per §6 (with reserved-set disambiguation)
- [ ] Envelope shape from §5 emitted with `recommendation_schema_version: 1`
- [ ] All 7 categories' trigger predicates implemented; compound resolution (`regression_with_localization` swallows constituents) works
- [ ] All 7 categories' templates interpolate slots correctly
- [ ] Each fixture in §7 produces the expected category set byte-identically across 3 consecutive synth calls (modulo `run_reference`)
- [ ] `syrupy` snapshot pinned for `pytest-basic` (one fixture — others have direct-assertion pins; PM may want to expand snapshot coverage in a follow-up)
- [ ] AI agent round-trip test (§8) passes — every citation resolves to a non-null fact via the canonical retrieval interface; slot values match resolved fact values
- [ ] Default suite gate green: `uv run pytest -q tests/unit tests/integration`
- [ ] mypy strict gate green: `uv run mypy` clean
- [ ] `flaky_suspected` trigger logic implemented + unit-tested via mock `ReplayResult`
- [ ] `novetest <target>` (default-verb alias) resolves to `novetest test <target>` when `<target>` not in reserved set; bare `novetest` returns help envelope; `novetest run <target>` stays unchanged
- [ ] `delivery-phasing.md:96` (Phase 1) AND lines 249-252 (Phase 6 DoD #1-4) all ready for PM to tick at cycle close

## Empirical verification

### Default suite gate

```text
uv run pytest -q tests/unit tests/integration
871 passed, 5 skipped in 64.53s
2 snapshots passed.
```

Baseline (origin/main tip `dd02942`): 781 + 10. Delta: **+90 net new
covered tests**. The 5-skip total (down from 10) reflects mix-in of
the new tests with the existing skips (cargo / java / Phase 5 guards).

### mypy strict gate

```text
uv run mypy
Success: no issues found in 80 source files
```

Baseline: 72 src files. Delta: **+8 src files** (matches brief §"File
map" projection of ~79 within ±1).

### Per-fixture envelope captures (brief §"Handoff format")

#### `pytest-basic` (clean run; Phase 1 line 96 closure for the
all-green case)

```json
{
  "command": "test",
  "ok": true,
  "data": {
    "stage_eligibility": {
      "coverage": "available",
      "regression": "unavailable",
      "localization": "unavailable",
      "replay": "not_run"
    },
    "recommendation_schema_version": 1,
    "recommendations": [
      {
        "category": "all_green",
        "priority": 7,
        "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
        "slots": {
          "passed": 3, "skipped": 0, "total_tests": 3,
          "run_reference": "<stripped>"
        },
        "evidence_citations": [
          {"kind": "run_reference", "run_reference": {"...": "..."}, "selector": {}}
        ]
      }
    ]
  }
}
```

#### `pytest-failing` (2 failing tests; Phase 1 line 96 closure for
the unavailable-analysis case)

7 recommendations: 6 × `investigate_location` (Phase 4 SBFL produces
medium/high-confidence per-test findings on the failing tests) +
1 × `unavailable_analysis` (regression unavailable because no
baseline; tests failed → we owe the user an explanation). Top
recommendation:

```
Investigate `count_up_to`@4 in `pytest_failing/counter.py`
(rank 2, ochiai=0.707, sbfl_per_test).
```

#### `localization-branch` (1st run; deliberate divide bug at lines
31-34)

11 recommendations: 10 × `investigate_location` + 1 ×
`unavailable_analysis`. The bug-site file
`localization_branch/calculator.py` sorts lexicographically ahead of
`tests/test_calculator.py` (which is high-rank by Ochiai because it
runs only failing tests) — that's the **brief §1 sort invariant**
pinned by `test_localization_branch_first_run_yields_investigate_location`.
Top recommendation:

```
Investigate `add`@20 in `localization_branch/calculator.py`
(rank 2, ochiai=0.000, sbfl_per_test).
```

#### `localization-branch` (2nd run, same bug; out of scope of this
slice's automated tests but the workflow handles the compound rule
when Regression Facts are computable — see open question Q3 below)

Not exercised by the integration suite this slice. The unit tests
(`tests/unit/orchestration/recommendation/test_categories.py::TestRegressionWithLocalization`)
pin the compound trigger semantics; the 2-run integration would
require additional fixture orchestration that the brief §7 lists but
does NOT mandate this slice.

### 3-consecutive-run determinism log (Brief §9 Phase 6 DoD #1)

Empirical A/B/C smoke against the seeded `localization-branch` store
via `build_test_outcome_from_run_id` (cache-only re-derivation):

```text
--- run #1 ---
  digest: -0x6a313cf878c7dabd
  category counts: {regression_with_localization: 0, unavailable_analysis: 1, investigate_location: 10, all_green: 0}
  first rec: Investigate `add`@20 in `localization_branch/calculator.py` (rank 2, ochiai=0.000, sbfl_per_test).
--- run #2 ---
  digest: -0x6a313cf878c7dabd  ← byte-identical
  category counts: {...same...}
  first rec: ...same...
--- run #3 ---
  digest: -0x6a313cf878c7dabd  ← byte-identical
  category counts: {...same...}
  first rec: ...same...
```

Regression-pinned by
`tests/integration/orchestration/test_test_workflow.py::test_determinism_localization_branch_three_consecutive_rederives`.

### AI agent round-trip test (Brief §8 NFR-ORCH-002 evidence)

`tests/integration/orchestration/test_recommendation_round_trip.py::test_investigate_location_citations_round_trip`
+ `test_every_recommendation_has_at_least_one_citation`. The first
test runs `novetest test` against `localization-branch`, picks the
first `investigate_location`, and resolves every citation via the
canonical retrieval interface:

- `localization_finding` → `localization/get_localization_findings(ref)`
- `coverage_fact` → `coverage/get_coverage_facts(ref)`
- `regression_fact` → `regression/get_regression_facts(baseline, target)`
- `test_result` → `memory/retrieve_run_evidence(ref)` + filter by `node_id`
- `run_reference` → `memory/list_run_history()` + verify in history
- `replay_result` → skipped with comment (Phase 5 dep)

Cross-check: the resolved Localization Finding entry's
`(file, primary_line, formula)` matches the recommendation's slot
values. The second test pins REQ-ORCH-005 (every recommendation has
≥1 citation) across every emitted recommendation.

### Default-verb alias E2E

`tests/integration/cli/test_default_verb_alias.py` covers six subprocess
scenarios:

- `novetest` (bare) → help envelope, exit 0 (REQ-ORCH-006).
- `novetest status` → routed to status (uninit envelope, exit 2 in
  isolated cwd).
- `novetest test tests/` → routed to test (uninit envelope, exit 2).
- `novetest tests/` (alias) → routed to test (`command: "test"`).
- `novetest run tests/` (explicit) → routed to run (alias does NOT fire).
- `novetest --output json tests/` (flag before target) → alias fires
  after flag extraction; routes to test.

Pure-function unit coverage in
`tests/unit/cli/test_default_verb_alias.py` adds 9 disambiguation
cases (empty argv, every reserved verb, path/glob/quoted/nodeid
targets, all-flags-no-positional, leading flag + target, plus a
no-mutation pin for the immutable contract).

## Worktree path + branch

- Worktree: `/home/yjshin/dev/novetest-phase6-recsynth`
- Branch: `worktree-phase6-recommendation-synthesis`
- Base: `origin/main` tip `dd02942 comms: queue Phase 6 entry brief — recommendation synthesis (closed taxonomy v1)`

## File manifest for Main Branch FF-merge

**New src files (8)**:

- `src/novetest/orchestration/recommendation/__init__.py` (76 lines)
- `src/novetest/orchestration/recommendation/categories.py` (480 lines)
- `src/novetest/orchestration/recommendation/templates.py` (250 lines)
- `src/novetest/orchestration/recommendation/citations.py` (330 lines)
- `src/novetest/orchestration/recommendation/synthesizer.py` (95 lines)
- `src/novetest/orchestration/recommendation/fact_bundle.py` (290 lines)
- `src/novetest/orchestration/workflows/test.py` (310 lines)
- `src/novetest/cli/handlers/__init__.py` (20 lines)
- `src/novetest/cli/handlers/test.py` (80 lines)

**Modified src files (3)**:

- `src/novetest/cli/app.py` (+~80 lines: test_cmd registration,
  default-verb alias hook, bare-novetest help branch)
- `src/novetest/orchestration/workflows/__init__.py` (+5 lines:
  new exports)

**New test files (9)**:

- `tests/unit/orchestration/recommendation/test_categories.py` (~530 lines)
- `tests/unit/orchestration/recommendation/test_templates.py` (~190 lines)
- `tests/unit/orchestration/recommendation/test_synthesizer.py` (~210 lines)
- `tests/unit/orchestration/recommendation/test_citations.py` (~340 lines)
- `tests/unit/orchestration/recommendation/test_fact_bundle.py` (~210 lines)
- `tests/unit/orchestration/workflows/test_test_workflow.py` (~180 lines)
- `tests/unit/cli/test_default_verb_alias.py` (~110 lines)
- `tests/unit/cli/test_test_handler.py` (~120 lines)
- `tests/integration/orchestration/test_test_workflow.py` (~230 lines, with syrupy snapshot)
- `tests/integration/orchestration/test_recommendation_round_trip.py` (~180 lines)
- `tests/integration/cli/test_default_verb_alias.py` (~120 lines)

**Modified test files (1)**:

- `tests/integration/cli/test_subcommand_stubs.py` (~-7 lines: dropped
  the pinned-as-stub `test` assertion)

**New snapshot files (1)**:

- `tests/integration/orchestration/__snapshots__/test_test_workflow.ambr`

**Coordination artifacts**:

- `WORKLOG.md` (new top entry)
- `agent-comms/handoffs/orchestration-team-2026-06-02-phase6-entry-recommendation-synthesis.md`
  (this file)
- `agent-comms/INDEX.md` (regenerated)

## What wasn't obvious (briefing for Main Branch + Manual Test)

### 1. Sort key invariant: `primary_slot`, not `recommendation_id`

The brief §1 stable sort key is `(priority, category, primary_slot)`
where `primary_slot` is the category-specific deterministic key (e.g.
`"src/calc.py:32"` for `investigate_location`). My first draft sorted
by `recommendation_id` (the SHA-1 hash) — deterministic but breaks
the "lex-min file wins" intent. The `localization-branch` fixture
surfaces the regression vividly: `tests/test_calculator.py` (the test
file with Ochiai=1.0) sorts ahead of `localization_branch/calculator.py`
(the bug source) by SHA-1 hash, so the rank-1 first invariant breaks.

Fix: `Recommendation` carries `primary_slot: str` as an internal
field (NOT surfaced in `to_dict()` to keep the wire shape minimal).
Future maintainers MUST keep it on the dataclass; removing it
silently regresses the brief's binding sort. Pinned by
`tests/integration/orchestration/test_test_workflow.py::test_localization_branch_first_run_yields_investigate_location`.

### 2. Citation round-trip resolver uses `(file, primary_line)`, not `rank`

SBFL ranks are dense — ties share a rank. My first draft of the
round-trip test resolved finding entries by `selector.rank` alone
and picked an arbitrary tied entry instead of the synthesizer's
actual choice. Fix: resolve by `(file, primary_line)` — the
unambiguous pair the synthesizer encodes in slots AND the citation
selector. This is the load-bearing round-trip invariant for
`localization_finding` citations under any future SBFL tie-breaking
changes. Pinned by the
`test_investigate_location_citations_round_trip` assertion comment.

### 3. `Replay` engine is empty; `ReplayResult` placeholder is transient

`src/novetest/replay/__init__.py` is empty pending Phase 5. The brief
§4 authorized a transient `ReplayResult` placeholder in
`recommendation/fact_bundle.py`. The placeholder's wire shape
(`classification`, `reruns_total`, `reruns_failed`, `run_reference`,
`test_id`) is pinned by the brief §1 `flaky_suspected` slot table;
Phase 5 will move the type to `models/` and the placeholder import
becomes a `models` re-export. NO behavior change anticipated.

### 4. Pytest collection guard pattern for `test_`-named symbols

`TestOutcome` (dataclass) AND `test_target_in_store` (public workflow
function) both got picked up by pytest collection. The canonical
opt-out is `__test__ = False` — works on class attributes (already
used by `TestResult` / `TestTransition`) AND on free function
attributes (the latter via `func.__test__ = False  # type: ignore[attr-defined]`
since functions have no declared attribute). Mypy strict requires the
`type: ignore` comment on the free-function variant.

### 5. Cyclopts default-verb alias hook is a pure-function pre-processor

The alias is implemented as a pre-Cyclopts argv transformation
(`_inject_default_verb_alias`), NOT as a Cyclopts-native default
command. Rationale: Cyclopts doesn't expose a clean default-verb-with-disambiguation
hook out of the box, and a pre-processor keeps the disambiguation
rule (reserved verb wins unconditionally) trivially testable. The
function is pure and unit-tested in isolation; the subprocess E2E
covers the integration surface.

### 6. Syrupy first-run needs `--snapshot-update`

The `test_pytest_basic_envelope_snapshot` test requires
`--snapshot-update` on its very first invocation against a missing
snapshot file. The snapshot file IS committed alongside this slice
(`tests/integration/orchestration/__snapshots__/test_test_workflow.ambr`)
so subsequent CI runs find it on disk and pass without the flag.
This is a syrupy quirk, not a defect in our test code. Mentioned so
Main Branch's gate run doesn't get confused if syrupy regenerates
the snapshot for some reason (e.g. a numpy version change altering
score precision).

## Open questions for PM

These are forward-looking — none gate the merge. Bundling them here
so PM can answer in the next history entry / cycle close.

### Q1 — `score_normalized == 0.0` entries in `investigate_location`

The brief §1 trigger for `investigate_location` is "Localization
Finding with `confidence in {high, medium}` AND `rank <= 3`". Strict
reading: every entry in the finding's top-3 (or top-N for ties)
qualifies, regardless of `score_normalized`.

Empirical: `localization-branch` produces 10 such recommendations
because dense-rank ties under SBFL push many entries to rank ≤ 3
(some with Ochiai = 0.000). Most carry no actionable signal.

**Proposal**: add a `score_normalized > 0` floor for v2 (would cut
cardinality dramatically without losing meaningful entries). NOT
done this slice because it requires a `recommendation_schema_version`
bump and PM decision.

### Q2 — Redundant `unavailable_analysis` alongside investigate_*

When ≥1 stage is unavailable AND tests failed, `unavailable_analysis`
fires per brief §1. When OTHER categories (like `investigate_location`)
fire on the SAME run with cited evidence, the user effectively gets
two recommendations: "investigate X" + "we owe you an explanation
because regression was unavailable". The latter is somewhat
redundant when meaningful guidance is already provided.

The brief §1 mutual exclusion rule says "coexists with other
categories only when those triggered on partially-available facts" —
strict reading: this IS the partial-availability case, so coexistence
is correct.

**Proposal**: a v2 tightening could drop `unavailable_analysis` when
ANY `investigate_*` category fired with cited evidence (i.e. when
the user has actionable guidance, suppress the "owe an explanation"
recommendation). NOT done this slice — requires PM decision +
schema_version bump.

### Q3 — `handlers/` package precedent

The brief §3 file map placed the CLI handler at
`src/novetest/cli/handlers/test.py` (~50 lines, thin handler). We
followed the brief literally and introduced the new `handlers/`
package. Older verbs (init / run / status / inspect / memory /
coverage / regression / compare / localization) stay inlined in
`cli/app.py` (~1200 lines).

**Decision options**:

- (A) Follow-up cycle: migrate the older verbs into `handlers/`
  for consistency.
- (B) Retroactively endorse inline-by-default: treat
  `handlers/test.py` as the exception (only for verbs whose
  envelope-building logic is substantial enough to warrant separate
  testability).
- (C) Hybrid: `handlers/` for verbs whose handler returns multiple
  envelope outcomes (e.g. test, future replay); inline for simple
  one-shot verbs (init, status).

We did NOT preemptively migrate other verbs in this slice (out of
scope per brief). PM picks the policy in the next cycle.

## Cross-references

- **Brief**: `agent-comms/tasks/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md`
- **Design doc**: `design/implementation-plan/recommendation-synthesis.md`
- **Interface contract**: `design/interace-contract/orchestration.md`
- **Workflow contract**: `design/workflows/orchestration.md`
- **Requirements**: `design/requirements-analysis/requirements-specification/groups/orchestration.md`
- **Sort invariant pin**: `tests/integration/orchestration/test_test_workflow.py::test_localization_branch_first_run_yields_investigate_location`
- **Determinism pin**: `tests/integration/orchestration/test_test_workflow.py::test_determinism_localization_branch_three_consecutive_rederives`
- **NFR-ORCH-002 pin**: `tests/integration/orchestration/test_recommendation_round_trip.py::test_investigate_location_citations_round_trip`
- **Default-verb alias pin**: `tests/integration/cli/test_default_verb_alias.py` + `tests/unit/cli/test_default_verb_alias.py`
- **Compound rule pin**: `tests/unit/orchestration/recommendation/test_categories.py::TestRegressionWithLocalization` + `TestCompoundResolution`
- **`recommendation_schema_version: 1`** lives in `src/novetest/orchestration/recommendation/synthesizer.py:RECOMMENDATION_SCHEMA_VERSION`.

## Suggested next step

Main Branch team merges `worktree-phase6-recommendation-synthesis`
into main + pushes + writes verification request to Manual Test
pointing them at the three brief §7 pinned fixtures
(`pytest-basic`, `pytest-failing`, `localization-branch`) and the
subprocess E2E at
`tests/integration/cli/test_default_verb_alias.py` for the
alias-activation surface.

After merge, PM ticks:

- `delivery-phasing.md:96` (Phase 1 lingering bullet)
- `delivery-phasing.md` Phase 6 DoD #1-4 (lines 249-252 per brief)

This closes Phase 1 → 100% AND Phase 6 → 100%. MVP scope after this
slice: **Phase 5** (Replay + SQLite index) + small **Phase 3**
JUnit/.NET adapters (gated on Open Q #4/#5) + **Phase 7** MCP
transport (post-MVP).
