---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-01
slug: phase6-entry-recommendation-synthesis
related:
  - design/implementation-plan/delivery-phasing.md
  - design/implementation-plan/recommendation-synthesis.md
  - design/interace-contract/orchestration.md
  - design/workflows/orchestration.md
  - design/requirements-analysis/requirements-specification/groups/orchestration.md
  - agent-comms/history/2026-06-01-phase4-complete-perf-nfr-loc-002.md
---

# Task: Phase 6 entry — Recommendation Synthesis (closed taxonomy v1, integrated `novetest test`, default-verb alias)

## TL;DR

Implement Phase 6 — `orchestration/recommendation/` rule-based
synthesizer with **closed 7-category taxonomy frozen at v1**, the
**integrated `novetest test [target]` workflow** that chains all engines
into a single user-facing surface emitting cited recommendations, and the
**default-verb alias** so `novetest <target>` resolves to
`novetest test <target>`.

This slice closes **4 Phase 6 DoD bullets** AND the lingering
**Phase 1 line 96 bullet** (the integrated `novetest test` flow returning
`all_green` / `unavailable_analysis` when downstream facts are empty).

After this slice, MVP scope shrinks to: Phase 5 (Replay + SQLite index) +
Phase 7 (MCP transport post-MVP) + small Phase 3 JUnit/.NET adapters
(gated on Open Q #4/#5).

## Product framing

`novetest test [target]` is the **single user-facing surface that
delivers the product's core value promise**: an AI agent (or developer)
runs one command, gets back a structured list of cited, deterministic
recommendations grounded in fact-set evidence. Every other CLI verb is
either onboarding (`init`, `-v`, `-h`), fact-retrieval-only
(`memory show`, `coverage show`, `regression compare`,
`localization latest`, `replay`), or composition (`inspect`, `compare`).

Until Phase 6 ships, `novetest test` is a stub. After Phase 6 ships,
Nove Test's pitch becomes demonstrable end-to-end on real fixtures.

## Phase 6 DoD mapping

Per `delivery-phasing.md` §"Phase 6 - Recommendation Synthesis":

1. `novetest test tests/` against each fixture produces the expected
   category set per fixture, **byte-identical across runs**.
2. Snapshots pinned with `syrupy`.
3. Integration test demonstrates an AI agent can traverse
   `recommendation -> evidence_citations -> retrieve_run_evidence`
   round-trip end-to-end.
4. **Default-verb alias activated.** `novetest <target>` resolves to
   `novetest test <target>` only when `<target>` is NOT in the reserved
   verb set. Bare `novetest` continues to print the help envelope.

**Plus the lingering Phase 1 line 96 bullet** (`delivery-phasing.md:96`):

> `novetest test tests/test_x.py` runs the integrated workflow but with
> empty Coverage / Regression / Localization / Replay; recommendation is
> `all_green` or `unavailable_analysis`.

This bullet is Phase 6-dependent and will close naturally as this slice
lands the integrated workflow.

## Pre-flight reading (mandatory)

1. **`agent-comms/INDEX.md`** — confirm pending list pre-pickup.
2. **`design/implementation-plan/recommendation-synthesis.md`** — design
   already 80% locked; this brief locks the remaining 20% (slot keys per
   category, persistence disposition).
3. **`design/interace-contract/orchestration.md`** §2 — interface
   signatures for `synthesize_recommendation`,
   `cite_recommendation_evidence`, `evaluate_stage_eligibility`.
4. **`design/workflows/orchestration.md`** §2 — the canonical workflow
   chain for `novetest test [target]`:
   ```
   run/execute -> memory/store_run_evidence -> orchestration/evaluate_stage_eligibility ->
     coverage/derive_coverage_facts -> regression/resolve_latest_baseline ->
     regression/compare_runs -> localization/derive_localization_findings ->
     orchestration/synthesize_recommendation -> orchestration/cite_recommendation_evidence
   ```
5. **`design/requirements-analysis/requirements-specification/groups/orchestration.md`**
   — REQ-ORCH-001/002/004/005, NFR-ORCH-001/002 are the gates.
6. Each engine's interface contract you call into (read-only):
   - `design/interace-contract/run.md`
   - `design/interace-contract/coverage.md`
   - `design/interace-contract/regression.md`
   - `design/interace-contract/localization.md`
   - `design/interace-contract/replay.md` (Phase 5 — call into the
     **`check_replay_availability` stub only**; `flaky_suspected`
     trigger code goes in but tests against mock fact bundles only)
7. **`src/novetest/orchestration/recommendation/`** — currently empty
   `__init__.py` placeholder. You are building this module from scratch.
8. **`src/novetest/orchestration/workflows/`** — `init.py`, `run.py`,
   `status.py`, `inspect.py`, `compare.py` already exist. You add
   `test.py` (the integrated workflow).

## §1 — Closed taxonomy v1 freeze (PM decision; binding)

This is the **Open Q #10 closure**. Each category below has frozen slot
keys; bumping `recommendation_schema_version` to v2 is the only way to
change them post-Phase-6.

### Category catalog (priority high→low)

| Priority | Category | Trigger (precondition) | Required slots | Citations (kinds) |
|---|---|---|---|---|
| 1 | `regression_with_localization` | Regression Fact (newly_failing test) AND Localization Finding overlap on file/symbol | `test_id`, `regression_kind`, `symbol`, `file`, `primary_line`, `line_range`, `rank`, `score_normalized`, `formula`, `mode`, `run_reference_from`, `run_reference_to` | `regression_fact` + `localization_finding` + `test_result` |
| 2 | `investigate_location` | Localization Finding with `confidence in {high, medium}` AND `rank <= 3` | `symbol`, `file`, `primary_line`, `line_range`, `rank`, `score_normalized`, `formula`, `mode` | `localization_finding` + `test_result` (≥1 failing test from `related_failed_tests`) |
| 3 | `investigate_regression` | Regression Fact: test newly failing this run (in `regressed_tests`) | `test_id`, `regression_kind` (`newly_failing` for Phase 6 v1), `run_reference_from`, `run_reference_to` | `regression_fact` + `test_result` |
| 4 | `coverage_gap` | Coverage Fact shows uncovered branch/line AND that line falls in the file/range of a Localization Finding | `file`, `lines`, `mode`, `related_finding_id` | `coverage_fact` + `localization_finding` |
| 5 | `flaky_suspected` | Replay Result with `classification == "inconsistent"` (Phase 5 dep — implement logic + unit test against mock fact bundle; no real fixture this slice) | `test_id`, `reruns_total`, `reruns_failed`, `run_reference` | `replay_result` + `test_result` |
| 6 | `unavailable_analysis` | One or more downstream stages returned `unavailable` AND at least one test failed (so we owe the user an explanation) | `unavailable_stages` (list), `reason_per_stage` (dict: stage→reason), `run_reference` | `run_reference` (bare, no fact source) |
| 7 | `all_green` | Run's `summary.failed == 0` AND no regression detected AND no flake (and no investigation surfaces) | `run_reference`, `total_tests`, `passed`, `skipped` | `run_reference` |

### Slot semantics (frozen v1)

- All slot values are JSON-serializable primitives or lists thereof. No
  custom types in the wire shape.
- `file` paths are **always relative to the project store root** (the
  workspace path where `.novetest/` lives), normalized to forward
  slashes. This matches the Localization Finding shape (v2).
- `line_range` is `[start_int, end_int]`, both inclusive; `null` when
  symbol-level resolution is unavailable.
- `score_normalized` is `float` in `[0.0, 1.0]`. Use the formula-primary
  finding's `score_normalized` field.
- `regression_kind` is the closed enum `"newly_failing"` for Phase 6 v1.
  (`"now_passing"` is a v2 addition — DO NOT ship.)
- `unavailable_stages` order is stable: `["coverage", "regression",
  "localization", "replay"]` filtered to those returning unavailable.
- `reason_per_stage` values are the engine's own `unavailable.reason`
  field verbatim (already standardized across engines:
  `no_coverage_data`, `no_baseline_available`, `run_not_analyzable`,
  `replay_not_run`, etc.).

### Compound rule

`regression_with_localization` swallows its constituents — when triggered,
the synthesizer MUST NOT also emit a bare `investigate_location` or
`investigate_regression` for the same `(file, test_id)` pair. This is
enforced in `compound_resolution()`.

If the regression covers test T1 and localization implicates symbol S in
file F, but T1 is NOT in S's `related_failed_tests`, that is two
independent recommendations (`investigate_regression` for T1 +
`investigate_location` for S), NOT a compound. The overlap test is on
`(file, related_failed_tests)`, not just colocation.

### Stable ordering rule

The output `recommendations` list is sorted by
`(priority asc, category asc, primary_slot asc)`:

| Category | `primary_slot` |
|---|---|
| `regression_with_localization` | `f"{file}:{line_range[0]}:{test_id}"` |
| `investigate_location` | `f"{file}:{line_range[0] if line_range else primary_line}"` |
| `investigate_regression` | `test_id` |
| `coverage_gap` | `f"{file}:{lines[0]}"` |
| `flaky_suspected` | `test_id` |
| `unavailable_analysis` | `""` (only one such recommendation per run) |
| `all_green` | `""` (only one such recommendation per run) |

### `recommendation_id` generation (deterministic)

`rec_<run_reference>_<sha1(category|primary_slot)[:8]>` per design doc §4.
Use Python's `hashlib.sha1` over UTF-8-encoded
`f"{category}|{primary_slot}"`.

### Mutual exclusion rules

- `all_green` MUST NOT coexist with any other category. Synthesizer
  checks: if any non-`all_green` category triggers, drop `all_green`.
- `unavailable_analysis` coexists with other categories only when those
  categories triggered on **partially-available** facts. If literally
  zero facts are available AND tests failed, emit ONLY
  `unavailable_analysis`.

## §2 — Persistence disposition (PM decision; binding)

This is the **Open Q #9 closure**.

**Recommendations are NOT persisted by default.** They are re-derived
each time `novetest test` runs or `novetest inspect` is called.

Rationale (per design doc §6):
- Synthesis is a pure function over `FactBundle`. Same facts → same
  recommendations (determinism contract §4).
- Persisted facts already cover provenance; persisting recommendations
  would duplicate state and risk staleness on re-derive.
- Phase 6 measures the cost of re-derivation; if `inspect` perf becomes
  a problem, a cache file under
  `.novetest/orchestration/recommendations/run_<ulid>/recommendations.json`
  may be added as an **optimization** (not correctness). Out of scope
  this slice.

**Implementation gate**: do NOT write a `recommendations.json` file
this slice. The synthesizer's entrypoint must accept a `FactBundle`
and return `list[Recommendation]` purely in-memory.

## §3 — Module layout (PM-pinned; binding)

```
src/novetest/orchestration/
├── recommendation/
│   ├── __init__.py              # public exports: synthesize_recommendation, cite_recommendation_evidence
│   ├── categories.py            # closed taxonomy: priority registry + trigger predicates
│   ├── templates.py             # one summary template per category, slot-driven
│   ├── synthesizer.py           # main rule-based engine; pure function over FactBundle
│   ├── citations.py             # cite_recommendation_evidence; pure projection from facts
│   └── fact_bundle.py           # FactBundle dataclass + builder from engine outputs
└── workflows/
    └── test.py                  # NEW — the integrated `novetest test [target]` workflow
```

**Existing files you touch** (additive):
- `src/novetest/cli/app.py` — register `test_cmd` subcommand + default-verb alias
- `src/novetest/cli/output.py` — extend envelope `data` to carry
  `recommendation_schema_version: 1` + `stage_eligibility` block

**Existing files you DO NOT touch**:
- Any other engine module (`run/`, `coverage/`, `regression/`,
  `localization/`, `replay/`, `memory/`, `models/`)
- Any other workflow module (`init.py`, `run.py`, `status.py`,
  `inspect.py`, `compare.py`) **except** `inspect.py` may receive an
  additive call to `synthesize_recommendation` to populate the inspect
  view's `recommendations` field (per workflow design)

## §4 — `FactBundle` shape (PM-proposed; refine in implementation)

```python
@dataclass(slots=True, frozen=True)
class FactBundle:
    run_reference: str
    run_record: RunRecord              # always available
    stage_eligibility: StageEligibility  # which downstream stages produced facts
    coverage_facts: CoverageFactSet | None       # None when unavailable
    regression_facts: RegressionFactSet | None
    localization_findings: LocalizationFindingSet | None
    replay_result: ReplayResult | None           # always None in Phase 6 entry (Phase 5 dep)
```

The synthesizer must handle `None` gracefully — that's the
`unavailable_analysis` trigger surface. Each engine's `get_*` /
`derive_*` interfaces already return either the fact-set object or the
engine's `unavailable` shape; the bundle builder unwraps and maps both.

## §5 — `novetest test [target]` workflow (binding sequence)

Per `workflows/orchestration.md` §2:

```
1. orchestration/initialize_or_resolve_store           (if uninitialized → uninitialized envelope)
2. run/execute(target)                                  (Run engine)
3. memory/store_run_evidence(run_record)                (Memory)
4. orchestration/evaluate_stage_eligibility(run_ref)    (this module)
5. coverage/derive_coverage_facts(run_ref)              (only if Run produced coverage; otherwise None)
6. regression/resolve_latest_baseline(target)           (Regression)
7. regression/compare_runs(baseline, current)           (Regression)
8. localization/derive_localization_findings(run_ref)   (Localization)
9. orchestration/build_fact_bundle(run_ref, *facts)     (this module)
10. orchestration/synthesize_recommendation(bundle)     (this module)
11. orchestration/cite_recommendation_evidence(...)     (chained inside synth)
12. emit envelope                                       (CLI)
```

**Error policy** (binding):
- Steps 5-8 are **best-effort**: any single-engine failure surfaces as
  `stage_eligibility.<stage> = "unavailable"` with the engine's
  `unavailable.reason`; the workflow continues. NEVER abort the whole
  `test` flow because one downstream engine failed.
- Step 2 (`run/execute`) **is fatal** — if Run fails, the integrated
  workflow returns the Run's error envelope unchanged (preserve exit
  code). No Recommendation synthesis for a failed run-execute (no Run
  Record → no FactBundle).
- Workflow timeout: respect each engine's NFR; do not add an
  orchestration-level wall-time cap.

**Envelope shape** (binding, frozen v1):
```json
{
  "schema": "novetest/v1",
  "command": "test",
  "ok": true,
  "data": {
    "run_reference": "run_<ulid>",
    "stage_eligibility": {
      "coverage": "available" | "unavailable" | "not_applicable",
      "regression": "available" | "unavailable" | "not_applicable",
      "localization": "sbfl_per_test" | "sbfl_aggregate" | "failure_proximity" | "unavailable" | "not_applicable",
      "replay": "available" | "unavailable" | "not_applicable" | "not_run"
    },
    "recommendation_schema_version": 1,
    "recommendations": [ ... ]
  },
  "errors": [],
  "warnings": []
}
```

Note: `localization` slot value follows the same vocabulary as the
Localization engine's `mode` field (per Phase 4 closure); when
Localization is fully unavailable it reverts to `"unavailable"`.

## §6 — Default-verb alias (Phase 6 DoD #4)

`novetest <target>` resolves to `novetest test <target>` ONLY when
`<target>` is NOT in the reserved verb set.

**Reserved verb set** (binding):
```
{"init", "test", "run", "memory", "inspect", "compare", "status",
 "coverage", "regression", "localization", "replay"}
```

Disambiguation rule (per `delivery-phasing.md` §"Phase 6 Risks"): if the
first positional token is in the reserved set, ALWAYS route to the verb
handler — even if a directory with the same name exists. Document this
in the help envelope.

Bare `novetest` (no arguments) → help envelope (REQ-ORCH-006), exit 0.
Bare `novetest` MUST NOT trigger any test execution.

`novetest run` (the explicit raw-evidence path) stays callable and
unchanged.

### Cyclopts implementation hint

Cyclopts supports a positional-args fallback via a top-level handler.
The cleanest path: register `test_cmd` normally, and add a top-level
hook in `app.py` that intercepts argv pre-Cyclopts when `argv[1]` is
not in the reserved set and is not a flag (`-`-prefixed). Inject
`"test"` before `argv[1]` and re-dispatch. See your team charter on
Cyclopts conventions; verify with `code-reviewer` subagent if uncertain.

## §7 — Fixture-to-category mapping (golden snapshot fixtures)

Each fixture below pins a specific category set via `syrupy` snapshot.
Snapshots live under `tests/integration/orchestration/test_test_workflow.py`
(file path matching the pattern `test_<workflow_name>`).

| Fixture | Run state | Expected category set (sorted by priority) | Compound? |
|---|---|---|---|
| `pytest-basic` | clean, 1+ passing | `["all_green"]` | no |
| `pytest-coverage` | clean + per-test coverage | `["all_green"]` | no |
| `localization-branch` | 1 failing test, deliberate `divide` bug at lines 31-34 | `["investigate_location"]` (rank 1, Ochiai 1.0; per-test mode); no compound (no regression baseline on first run) | no |
| `localization-branch` (2nd run, same bug) | 1 failing test, baseline = first run | `["regression_with_localization"]` (compound; `investigate_location` + `investigate_regression` merged) | **yes** |
| `localization-aggregate-only` | 1 failing test, no per-test coverage (cargo) | `["investigate_location"]` (aggregate mode, medium confidence) | no |
| `localization-no-coverage` | 1 failing test, no coverage at all | `["unavailable_analysis"]` (Coverage `unavailable`, Localization in `failure_proximity` mode but no high-confidence finding) | no |
| `pytest-failing` (1st run) | 2 failing tests, no localization-grade bug fixture | `["investigate_location"]` (Phase 4 sbfl_per_test still produces a finding) — verify; if no high-conf finding, then `["unavailable_analysis"]` | no |
| `pytest-failing` (2nd run, same failures) | 2 failing tests, baseline = 1st run | `["regression_with_localization"]` OR `["investigate_regression", "investigate_location"]` depending on overlap | possibly |

**Golden snapshot enforcement**: each fixture's snapshot must be
**byte-identical across 3 consecutive runs** of the same workflow on the
same machine. Determinism is the Phase 6 DoD bullet #1 contract.

### `flaky_suspected` — Phase 5 dependent (DO NOT add fixture)

Replay engine is Phase 5. For Phase 6 entry, implement the trigger logic
under `categories.py` AND a unit test in
`tests/unit/orchestration/recommendation/test_categories.py` that
constructs a **mock `ReplayResult` with `classification="inconsistent"`**
and asserts `flaky_suspected` triggers correctly.

DO NOT add a `flaky-python/` fixture this slice. DO NOT call
`replay/replay_run` from the `test` workflow this slice; the workflow
chain stops at Localization. Replay integration lands in Phase 5.

This pre-wires the category so Phase 5's Replay engine slice does not
need to touch the synthesizer.

## §8 — AI agent round-trip test (Phase 6 DoD #3)

This is the **NFR-ORCH-002 verification gate**. Add an integration test
under `tests/integration/orchestration/test_recommendation_round_trip.py`
that:

1. Runs `novetest test` against `localization-branch` (sub-process invocation)
2. Parses the returned JSON envelope (`schema: novetest/v1`)
3. Picks the first recommendation; reads its `evidence_citations`
4. For each citation, calls the **canonical retrieval interface**
   matching `kind`:
   - `localization_finding` → `localization/get_localization_findings(run_ref)` and find by `finding_id`
   - `coverage_fact` → `coverage/get_coverage_facts(run_ref)` and select via `selector.file` + `selector.lines`
   - `regression_fact` → `regression/get_regression_facts(baseline_ref, current_ref)` and select via `selector.test_id`
   - `replay_result` → (Phase 5 dep; skip in Phase 6 with comment)
   - `test_result` → `memory/retrieve_run_evidence(run_ref)` and find `TestResult` by `test_id`
   - `run_reference` → `memory/list_run_history()` and verify the run is in history
5. Assert each citation resolves to a non-null fact, AND that the slot
   values in the recommendation match the resolved fact (e.g.
   `slots.primary_line == localization_finding.entries[*].code_location.primary_line`)

This test is the canonical NFR-ORCH-002 evidence. Pin it as a
regression-gate; future changes that break citation traceability fail
the gate loudly.

## §9 — Performance + Determinism gates

### NFR-ORCH-003 (status perf — already met, regression-pin)

Status generation < 2s for 1000-run history. Phase 1 / Phase 3 closure
already satisfies this; do not regress. Add a smoke check in
`tests/unit/orchestration/test_synthesis_determinism.py`:

```python
# Smoke: synthesize against a small mock FactBundle 3 times,
# assert identical output (byte-equality on JSON-serialized form).
```

### NFR-ORCH-004 (-v / -h perf — already met)

`novetest -v` and `novetest -h` < 1s. Default-verb alias activation
MUST NOT regress this. Smoke check: re-run the existing onboarding
snapshot tests post-implementation.

### Determinism (Phase 6 DoD #1 contract)

`syrupy` snapshots over each fixture's output, 3 consecutive
invocations per fixture must produce byte-identical envelopes (modulo
the `run_reference` field, which carries a ULID and is timestamp-derived
— isolate or omit during snapshot comparison).

**Implementation pattern**: build a snapshot fixture that re-runs
`novetest test <fixture>` 3 times via subprocess, parses each envelope,
strips `run_reference` + timestamp fields, asserts equality. Then pin
one of the (post-strip) envelopes via `syrupy`.

## §10 — Phase 1 line 96 closure (PM verifies at cycle close)

`delivery-phasing.md:96`:

> `novetest test tests/test_x.py` runs the integrated workflow but with
> empty Coverage / Regression / Localization / Replay; recommendation is
> `all_green` or `unavailable_analysis`.

Closure path:
- Empty Coverage + Localization + no failing tests → `all_green`
- Failing tests + no Coverage → `unavailable_analysis`

`pytest-basic` (clean) and `pytest-failing` (no coverage) fixtures
exercise this DoD bullet. Once they pass with the expected categories,
PM ticks `delivery-phasing.md:96` at cycle close.

## Out of scope (binding)

- **Replay engine integration** (Phase 5 dep). Workflow stops at
  Localization; Replay slot is reserved but no Replay call this slice.
- **`flaky-python/` fixture creation** (Phase 5 territory).
- **Phase 5 SQLite index** (Phase 5 dep).
- **`--narrative` prose flag** (design doc §1 — explicitly deferred).
- **Recommendation persistence** (Open Q #9 closed: NOT persisted).
- **`recommendation_summary` count-by-category projection on Status**
  (design doc §6 — explicitly deferred).
- **JUnit / .NET adapters** (Open Q #4/#5 gated).
- **MCP transport** (Phase 7 post-MVP).
- **Public-API changes to other engines.** If an engine's contract
  feels insufficient (e.g. you need a new field on
  `LocalizationFinding`), file an `agent-comms/questions/` instead of
  reaching into the engine.
- **Bumping `schema: novetest/v1`** — this slice ships v1 of
  `recommendation_schema_version` INSIDE the v1 envelope, which is
  backward-compatible. Envelope schema does NOT bump.

## File map (proposed; refine in implementation)

```
src/novetest/orchestration/recommendation/
  __init__.py                         (exports)
  categories.py                       (~250 lines: 7 trigger predicates + priority registry + compound resolution)
  templates.py                        (~100 lines: 7 summary templates with slot interpolation)
  synthesizer.py                      (~200 lines: synthesize_recommendation main + compound rule + stable sort)
  citations.py                        (~150 lines: cite_recommendation_evidence per-kind projections)
  fact_bundle.py                      (~120 lines: FactBundle dataclass + builder from engine outputs)
src/novetest/orchestration/workflows/
  test.py                             (NEW, ~180 lines: integrated novetest test workflow)
src/novetest/cli/
  app.py                              (~30-line edit: register test_cmd + default-verb alias hook)
  output.py                           (~15-line edit: envelope extensions for `stage_eligibility` + `recommendation_schema_version`)
src/novetest/cli/handlers/
  test.py                             (NEW, ~50 lines: thin CLI handler delegating to workflows/test.py)

tests/unit/orchestration/recommendation/
  __init__.py
  test_categories.py                  (trigger predicates per category + mock-based flaky_suspected)
  test_templates.py                   (slot interpolation per category)
  test_synthesizer.py                 (compound resolution + stable sort + determinism)
  test_citations.py                   (per-kind projection invariants)
  test_fact_bundle.py                 (builder from engine outputs + None handling)
tests/unit/orchestration/workflows/
  test_test_workflow.py               (unit tests for orchestration/workflows/test.py)
tests/integration/orchestration/
  test_test_workflow.py               (golden-snapshot fixtures per §7)
  test_recommendation_round_trip.py   (NFR-ORCH-002 verification per §8)
  test_default_verb_alias.py          (Phase 6 DoD #4 alias activation + reserved-set disambiguation)
tests/__snapshots__/                  (syrupy snapshot files)
```

Source-file count target: 72 (current) + 7 (new src files in
recommendation/ + workflows/test.py + cli/handlers/test.py) = **~79
src files**.

## Definition of Done

- [ ] `src/novetest/orchestration/recommendation/{categories,templates,synthesizer,citations,fact_bundle}.py` implemented
- [ ] `src/novetest/orchestration/workflows/test.py` implements the
      §5 binding workflow sequence
- [ ] `src/novetest/cli/handlers/test.py` + `app.py` registration +
      default-verb alias activated per §6 (with reserved-set disambiguation)
- [ ] Envelope shape from §5 emitted with `recommendation_schema_version: 1`
- [ ] All 7 categories' trigger predicates implemented; compound
      resolution (`regression_with_localization` swallows constituents) works
- [ ] All 7 categories' templates interpolate slots correctly
- [ ] Each fixture in §7 produces the expected category set
      byte-identically across 3 consecutive runs (modulo `run_reference`)
- [ ] `syrupy` snapshots pinned for each fixture
- [ ] AI agent round-trip test (§8) passes — every citation resolves to
      a non-null fact via the canonical retrieval interface; slot values
      match resolved fact values
- [ ] Default suite gate green: `uv run pytest -q tests/unit tests/integration`
- [ ] mypy strict gate green: `uv run mypy` clean
- [ ] `flaky_suspected` trigger logic implemented + unit-tested via
      mock `ReplayResult` (per §7 deferral note)
- [ ] `novetest <target>` (default-verb alias) resolves to
      `novetest test <target>` when `<target>` not in reserved set; bare
      `novetest` returns help envelope; `novetest run <target>` stays
      unchanged
- [ ] `delivery-phasing.md:96` (Phase 1) AND lines 249-252 (Phase 6
      DoD #1-4) all ready for PM to tick at cycle close

## Handoff format (per team charter)

`agent-comms/handoffs/orchestration-team-2026-06-01-phase6-entry-recommendation-synthesis.md`:

- TL;DR
- DoD bullets believed closed (list — PM verifies + ticks)
- Empirical verification:
  - Default suite gate output (`pytest -q` count + wall time)
  - mypy strict output (file count + "Success" line)
  - **Per-fixture envelope captures** — verbatim `novetest test <fixture> --output json` output for each of the §7 fixtures (the canonical Phase 6 DoD #1 evidence)
  - **3-consecutive-run determinism log** — for each fixture, run 3x and show the envelopes are byte-identical (modulo `run_reference`)
  - **AI agent round-trip test** — verbatim output of the round-trip test asserting citations resolve
- Worktree path + branch
- File manifest for Main Branch FF-merge
- Anything that wasn't obvious (Cyclopts alias hook, FactBundle
  builder edge cases, etc.)
- Open questions for PM (if any)

## Cross-references

- **Coverage NFR-COV-002 precedent** (`tests/perf/coverage/test_perf_compare.py`,
  commit `5489c7e`) — pattern for self-contained Phase exit slice with
  determinism contract and golden snapshots.
- **Phase 4 §4 #3 perf NFR closure** (commit `36c6b82` +
  `history/2026-06-01-phase4-complete-perf-nfr-loc-002.md`) — most
  recent Phase exit pattern, including 3-host determinism cross-validation.
- **Localization Finding shape v2 decision**
  (`decisions/2026-05-28-localization-finding-shape-v2.md`) — the
  finding shape your synthesizer consumes; do NOT modify.
- **Native result metadata slot decision**
  (`decisions/2026-05-30-native-result-metadata-slot.md`) — useful
  for citation `selector` polymorphism reference.
- **Regression outcome envelope shape decision**
  (`decisions/2026-05-28-regression-outcome-envelope-shape.md`) — your
  citation `kind: regression_fact` consumes this.
- **Localization outcome envelope shape decision**
  (`decisions/2026-05-30-localization-outcome-envelope-shape.md`) — your
  citation `kind: localization_finding` consumes this.
- **Recommendation synthesis design doc**
  (`design/implementation-plan/recommendation-synthesis.md`) — the
  90%-locked design this slice closes. §1-7 are binding; this brief's
  §1 (slot keys) and §2 (persistence) lock the remaining 10%.

## Effort estimate

- **Realistic**: 3 days. The category catalog (§1) is the bulk of design
  work and is pre-frozen in this brief. Code spread:
  - Day 1: `categories.py` + `templates.py` + `synthesizer.py` core
    (mostly translating the brief's §1 table into Python)
  - Day 2: `citations.py` + `fact_bundle.py` + `workflows/test.py` +
    `cli/app.py` alias hook
  - Day 3: integration tests + golden snapshots + round-trip test +
    determinism cross-runs + mypy + worklog + handoff
- **Risk-adjusted**: 4-5 days if the default-verb alias hits Cyclopts
  ergonomic friction (the disambiguation rule for tokens like
  `tests/inspect/` may need a custom positional pre-processor; consult
  the `code-reviewer` or `cli-developer` subagent if blocked).

## Branch outcome anticipation

This is NOT a perf slice with branch-point logic (Coverage NFR-COV-002
+ Localization NFR-LOC-002 patterns). The branches here are simpler:

- **Branch A (expected)**: all 7 categories implement cleanly; golden
  snapshots pin; round-trip test passes; default-verb alias activates
  without Cyclopts friction. Ship as-is.
- **Branch B (Cyclopts alias friction)**: the alias hook needs a custom
  argv pre-processor. Add it in `cli/app.py` with a `pre_argv_hook()`
  pure function + unit test covering 6 disambiguation scenarios
  (target=verb, target=path, target=flag, target=empty, target=quoted,
  target=glob). Otherwise ship same DoD.
- **Branch C (compound resolution edge case)**: if Phase 4's
  Localization Finding's `related_failed_tests` field shape clashes
  with how the synthesizer needs to detect overlap with Regression
  Fact's `regressed_tests`, file an `agent-comms/questions/` to PM
  with a concrete repro. DO NOT silently work around — the overlap
  rule is a binding compound trigger.

Default expectation: Branch A. The design doc is well-locked; this brief
locks the remaining decisions. Implementation is mostly translation +
test scaffolding.

## What this slice does NOT obligate

- Phase 5 entry (Replay + SQLite) — separate cycle
- Phase 3 JUnit/.NET adapters — gated on Open Q #4/#5
- Phase 7 MCP transport — post-MVP
- Slow-CI host sampling for NFR-LOC-002 — carry-forward
- Defect 7 (failure_proximity warning loop) — low priority carry-forward

Those stay on the carry-forward shelf.

## What's next after this slice

Phase 6 → 100% complete + Phase 1 → 100% complete (last bullet). MVP
scope after: Phase 5 (Replay + SQLite) is the only remaining major
milestone. PM's next dispatch likely Phase 5 entry brief — requiring
Open Q #19 (SQLite schema + rebuild trigger) closure first.
