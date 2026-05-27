---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-05-27
slug: orchestration-regression-cli
related:
  - agent-comms/tasks/orchestration-team-2026-05-27-regression-cli.md
  - agent-comms/handoffs/orchestration-team-2026-05-27-regression-cli.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
  - agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - design/interace-contract/orchestration.md
  - design/implementation-plan/delivery-phasing.md
---

# Verification: Phase 3 Regression CLI surface + `inspect` Regression section

## Merged commits

- `c074226 feat(orchestration): wire Phase 3 Regression CLI surface`
- `defc7a2 comms: handoff for Phase 3 Regression CLI slice`
- Merged into `main` via fast-forward from `worktree-regression-cli`.
- Base before merge: `ce1bd44`; new HEAD: `defc7a2`.

## Source handoff consumed

- `agent-comms/handoffs/orchestration-team-2026-05-27-regression-cli.md`

## Test gate (re-run on the merged commit by Main Branch)

- `uv run pytest -q tests/unit tests/integration` → **471 passed + 3 skipped**
  (baseline `ce1bd44`/`82e1775`: 442+3 → +29 net; the 3 skips are the
  pre-existing Node-dependent jest integration tests on this dev host).
- `uv run mypy` → **clean**, 57 source files, `--strict`. Matches the
  handoff's claim exactly.

## What landed

Three new CLI verbs and one new `inspect` section, all pure projection
of the now-100%-complete Regression engine surface. No `regression/**`
or `memory/**` source touched in this slice.

1. `novetest regression compare <baseline_run_id> <target_run_id>`
2. `novetest regression latest`
3. `novetest compare <baseline_run_id> <target_run_id>` (composed
   Regression + Coverage delta — distinct from `regression compare`)
4. `novetest inspect <run_id>` gains a `data.regression_outcome` block
   and `data.sub_reports.regression` flips from hardcoded `"unavailable"`
   to the actual computed outcome.

DoD bullets believed closed (per handoff):
`[156]`, `[157]`, `[158]` from `design/implementation-plan/delivery-phasing.md`.
PM ticks these at cycle-close.

## Envelope shapes — observed on the merged code

These were captured by running the merged binary against a tmp Project
Store seeded with two synthetic `RunRecord`s via `store_run_evidence`
(same seam the new integration tests use). Paths are copy-paste-safe.

### `regression compare` / `regression latest` — `kind: "fact-set"`

Observed top-level data keys on a successful pair:

```
envelope.command                                          == "regression.compare" | "regression.latest"
envelope.ok                                               == true
envelope.data.regression_outcome.kind                     == "fact-set"
envelope.data.regression_outcome.baseline_run_reference.run_id
envelope.data.regression_outcome.baseline_run_reference.created_at
envelope.data.regression_outcome.baseline_run_reference.schema_version  # inner schema retained
envelope.data.regression_outcome.target_run_reference.run_id
envelope.data.regression_outcome.target_run_reference.created_at
envelope.data.regression_outcome.target_run_reference.schema_version
envelope.data.regression_outcome.baseline_engine_name
envelope.data.regression_outcome.baseline_engine_version                # nullable
envelope.data.regression_outcome.target_engine_name
envelope.data.regression_outcome.target_engine_version                  # nullable
envelope.data.regression_outcome.derived_at                             # epoch ms
envelope.data.regression_outcome.summary.regressed
envelope.data.regression_outcome.summary.fixed
envelope.data.regression_outcome.summary.still_failing
envelope.data.regression_outcome.summary.still_passing
envelope.data.regression_outcome.summary.still_skipped
envelope.data.regression_outcome.summary.newly_skipped
envelope.data.regression_outcome.summary.newly_active
envelope.data.regression_outcome.summary.added
envelope.data.regression_outcome.summary.removed
envelope.data.regression_outcome.summary.total_baseline_tests
envelope.data.regression_outcome.summary.total_target_tests
envelope.data.regression_outcome.test_transitions[*].node_id
envelope.data.regression_outcome.test_transitions[*].category           # one of 9 TRANSITION_CATEGORIES
envelope.data.regression_outcome.test_transitions[*].baseline_outcome   # nullable
envelope.data.regression_outcome.test_transitions[*].target_outcome     # nullable
envelope.data.regression_outcome.test_transitions[*].baseline_failure_reference  # nullable
envelope.data.regression_outcome.test_transitions[*].target_failure_reference    # nullable
envelope.data.regression_outcome.test_transitions[*].baseline_duration_ms        # nullable
envelope.data.regression_outcome.test_transitions[*].target_duration_ms          # nullable
envelope.data.regression_outcome.test_transitions[*].schema_version              # 1
envelope.data.regression_outcome.output_diff                            # null | {...}
envelope.data.regression_outcome.coverage_change                        # null | CoverageDelta.to_dict() verbatim
envelope.data.regression_outcome.warnings                               # always [] (write-side), tolerate omission read-side
envelope.data.regression_outcome.metadata                               # always {} at v1
```

**Pinned gotcha #1:** Top-level `schema_version` is stripped from
`regression_outcome` (envelope versioning lives at `envelope.schema =
"novetest/v1"`), but inner blocks (`*_run_reference`,
`test_transitions[*]`, embedded `coverage_change`) RETAIN their own
`schema_version` — same precedent as `coverage_outcome` / `coverage_delta`.

**Pinned gotcha #2:** There is NO top-level `engine_name` /
`ecosystem` / `target_type` / `target_expression` on `fact-set`. The
brief's idealised draft had those; the actual `RegressionFactSet.to_dict()`
emits per-side `*_engine_name` / `*_engine_version` only. PM has this
pinned in the handoff for the upcoming freeze decision.

### `regression compare` / `regression latest` — `kind: "unavailable"`

```
envelope.data.regression_outcome.kind                     == "unavailable"
envelope.data.regression_outcome.baseline_run_reference   # null | { run_id, created_at, schema_version }
envelope.data.regression_outcome.target_run_reference     # null | { run_id, created_at, schema_version }
envelope.data.regression_outcome.reason                   # one of the 6 REASON_* values
envelope.data.regression_outcome.detail                   # string | null (dataclass default is None)
```

The 6 reasons closed by `decisions/2026-05-26-regression-facts-json-layout.md` §7:
`run-not-found`, `run-tombstoned`, `no-comparable-baseline`,
`missing-derived-facts`, `engine-mismatch`, `target-mismatch`.

**Pinned gotcha #3:** Both refs are INDEPENDENTLY nullable so the
consumer can tell WHICH side failed (richer than Coverage's single-ref
`Unavailable`). The freeze decision should pin this.

### `compare` verb — composed envelope

```
envelope.command                                          == "compare"
envelope.ok                                               == true
set(envelope.data.keys())                                 == {"regression_outcome", "coverage_delta"}
envelope.data.regression_outcome.kind                     == "fact-set" | "unavailable"
envelope.data.coverage_delta.kind                         == "delta" | "unavailable"
```

`coverage_delta` is the existing frozen shape from
`decisions/2026-05-16-coverage-delta-envelope-shape.md` — same projection
as `coverage diff` emits.

### `inspect` envelope — Regression section now wired

```
envelope.command                                          == "inspect"
sorted(envelope.data.keys())                              == ["coverage_outcome", "regression_outcome",
                                                              "run_reference", "run_summary", "sub_reports"]
envelope.data.regression_outcome.kind                     == "fact-set" | "unavailable"
envelope.data.sub_reports.regression                      == "available" | "unavailable"
                                                              # flipped — was hardcoded "unavailable" pre-slice
envelope.data.sub_reports.{coverage,localization,replay}  # unchanged
```

**Pinned behaviour:** `inspect <middle_run_id>` baselines against the
IMMEDIATE prior live run on the same target — NOT the global latest
pair. So if you have three runs A→B→C on the same target,
`inspect <B>` shows the A↔B comparison, not B↔C and not A↔C. The unit
test `test_inspecting_an_old_run_uses_immediate_prior_not_global_latest`
pins this; please sanity-check on a real 3-run target.

### Error paths

- **Bogus run_id** (typo in baseline or target) → exit `2`, envelope
  carries `errors[0].code == "not-found"`,
  `errors[0].message == "No Memory Entry for run_id='...'"`,
  `data == {}`. The `_resolve_run_reference` helper short-circuits
  BEFORE `compare_runs` is invoked — so a typo never reaches the engine
  as `REASON_RUN_NOT_FOUND`.
- **Uninitialized workspace** (no `.novetest/` ancestor) → exit `2`,
  `errors[0].code == "uninitialized"`. Standard `_require_store` path.
- **Unavailable outcome on a valid pair** (tombstoned, engine-mismatch,
  etc.) → exit `0`, `envelope.ok == true`,
  `data.regression_outcome.kind == "unavailable"`. **Unavailable is
  data, not a transport error** — same convention Coverage already
  uses.

## Verification scenarios for Manual Test

Per decision §C.2 cadence, this slice ships with a **working-draft
envelope shape**. Manual Test fields it; PM then freezes via a
`decisions/2026-05-XX-regression-outcome-envelope-shape.md` entry. Treat
the shapes above as the source of truth FOR THIS CYCLE, and report any
UX friction you encounter.

### Setup (once)

```bash
mkdir /tmp/nove-mt-regression && cd /tmp/nove-mt-regression
uv --project /home/yjshin/dev/Nove-Test run novetest init
```

To seed two real `RunRecord`s without depending on a native engine probe
on this host, use the public Memory seam exactly as the new integration
test does:

```bash
cat > /tmp/seed_mt.py <<'PY'
import sys
sys.path.insert(0, "/home/yjshin/dev/Nove-Test/src")
from pathlib import Path
from novetest.memory.project_store import create_project_store
from novetest.memory.store import store_run_evidence
from novetest.models.run_record import RunRecord
from novetest.models.run_reference import RunReference
from novetest.models.test_result import TestResult

ws = Path("/tmp/nove-mt-regression")
store = create_project_store(ws)
BASE = RunReference(run_id="01MTBASELINE0000000000000A", created_at=1_700_000_000_000)
TGT  = RunReference(run_id="01MTTARGET000000000000000B", created_at=1_700_000_001_000)
baseline = RunRecord(
    run_reference=BASE, target_expression="tests/", target_type="dir",
    engine_name="pytest", engine_version="8.2.0", ecosystem="python",
    status="failed", started_at=BASE.created_at, completed_at=BASE.created_at + 1000,
    test_results=(
        TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=10),
        TestResult(node_id="tests/x.py::test_b", outcome="failed", duration_ms=12),
    ),
)
target = RunRecord(
    run_reference=TGT, target_expression="tests/", target_type="dir",
    engine_name="pytest", engine_version="8.2.0", ecosystem="python",
    status="passed", started_at=TGT.created_at, completed_at=TGT.created_at + 1000,
    test_results=(
        TestResult(node_id="tests/x.py::test_a", outcome="passed", duration_ms=9),
        TestResult(node_id="tests/x.py::test_b", outcome="passed", duration_ms=11),
    ),
)
store_run_evidence(store, baseline)
store_run_evidence(store, target)
print("seeded:", ws)
PY
uv --project /home/yjshin/dev/Nove-Test run python /tmp/seed_mt.py
```

### Scenario 1 — `regression compare` happy path

```bash
cd /tmp/nove-mt-regression
uv --project /home/yjshin/dev/Nove-Test run novetest regression compare \
    01MTBASELINE0000000000000A 01MTTARGET000000000000000B
echo "EXIT=$?"
```

Expect: exit `0`; `envelope.data.regression_outcome.kind == "fact-set"`;
`summary.fixed == 1`; `summary.still_passing == 1`; all 11 summary keys
present; `test_transitions` length 2 sorted by `node_id`.

### Scenario 2 — `regression compare` cache hit

Re-run the exact same command. Compare the `derived_at` timestamps
across the two envelopes — they should be IDENTICAL (proves the cached
`regression_facts.json` was read, not re-derived). On-disk path to peek:
`<store>/regression/pairs/run_<baseline>__run_<target>/regression_facts.json`.

### Scenario 3 — `regression compare` not-found short-circuit

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest regression compare \
    01BOGUSBASELINE0000000000Z 01MTTARGET000000000000000B
echo "EXIT=$?"
```

Expect: exit `2`; `envelope.ok == false`;
`envelope.errors[0].code == "not-found"`; `envelope.data == {}`. The
error does NOT come through `regression_outcome.kind == "unavailable"` —
it short-circuits at `_resolve_run_reference` before `compare_runs` is
called. Same applies to a bogus TARGET id.

### Scenario 4 — `regression latest` happy path

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest regression latest
echo "EXIT=$?"
```

Expect: exit `0`; same `fact-set` shape;
`baseline_run_reference.run_id == 01MTBASELINE...`;
`target_run_reference.run_id == 01MTTARGET...` (the latest-two on the
active target).

### Scenario 5 — `regression latest` single-run on target

Tear down the store (`rm -rf /tmp/nove-mt-regression`), re-init, seed
only ONE run on the target, then:

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest regression latest
```

Expect: exit `0`; `kind == "unavailable"`;
`reason == "no-comparable-baseline"`;
`detail == "tests/"` (the target expression, **NOT** `"no-runs"` —
that detail is reserved for the empty-store case per the prior cycle's
pin).

### Scenario 6 — `regression latest` empty store

Tear down, re-init, run `regression latest` with NO runs seeded:

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest regression latest
```

Expect: exit `0`; `kind == "unavailable"`;
`reason == "no-comparable-baseline"`; `detail == "no-runs"` (the
reserved literal for the empty case).

### Scenario 7 — `compare` verb (composed)

Re-seed the two-run store from §Setup, then:

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest compare \
    01MTBASELINE0000000000000A 01MTTARGET000000000000000B
```

Expect: exit `0`; `set(envelope.data.keys()) == {"regression_outcome",
"coverage_delta"}`; `regression_outcome.kind == "fact-set"`;
`coverage_delta.kind == "unavailable"` with
`reason == "missing-derived-facts"` (neither seed was executed with
`--coverage`, so coverage facts are absent on both sides).

**Distinct from `regression compare`:** the latter emits only
`regression_outcome`; `compare` emits BOTH blocks. Same `regression`
content, but the verb shape differs.

### Scenario 8 — `inspect` Regression section flips

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest inspect \
    01MTTARGET000000000000000B
```

Expect: `envelope.data.sub_reports.regression == "available"` (was
hardcoded `"unavailable"` pre-slice);
`envelope.data.regression_outcome.kind == "fact-set"`;
`baseline_run_reference.run_id == 01MTBASELINE...` (the prior live run
on the same target).

Then `inspect 01MTBASELINE0000000000000A` — the OLDEST run with no
prior on the same target:

Expect: `sub_reports.regression == "unavailable"`;
`regression_outcome.kind == "unavailable"`;
`reason == "no-comparable-baseline"`;
`target_run_reference.run_id == 01MTBASELINE...` (the inspected ref is
populated); `baseline_run_reference == null`.

### Scenario 9 — `inspect <middle_run>` baselines against immediate prior

Construct a 3-run target (A, B, C in chronological order) using a
seeding script that mirrors §Setup with an extra middle run, then run:

```bash
uv --project /home/yjshin/dev/Nove-Test run novetest inspect <B_run_id>
```

Expect: `regression_outcome.baseline_run_reference.run_id == <A>` (the
IMMEDIATE prior — NOT the global latest pair B↔C).
This is the load-bearing inspect-orchestration composition per the
handoff; worth a real-fingers sanity check.

### Scenario 10 — tombstone-after-cache override (decision §C.1)

This one's worth probing because it's the strongest hard-fail rule in
the layout decision: derive a `regression compare` pair (so
`regression_facts.json` lands on disk), then tombstone one of the runs
in Memory, then re-call `regression compare`. Expect:
`regression_outcome.kind == "unavailable"`;
`reason == "run-tombstoned"`; the stale cache file is NOT read.

(Tombstoning a run requires either a future CLI verb that doesn't exist
yet, or a direct Memory API call from a one-off Python script. If
this is awkward to exercise, document the friction in your findings —
it's a UX signal for PM.)

## Critical edge cases worth probing

1. **Cache-hit envelope identity** — `derived_at` MUST be identical
   across two back-to-back calls on the same pair (no fresh epoch_ms).
2. **`detail` semantics** — `derive_latest_regression` pins
   `detail == "no-runs"` for empty stores vs `detail == <target_expression>`
   for single-run stores. The `kind: "unavailable"` `reason ==
   "no-comparable-baseline"` is the same; the `detail` carries the
   distinction. Worth probing both.
3. **`inspect` baseline-resolution composition** is orchestration-layer
   (NOT the engine's `resolve_latest_baseline` — that returns the
   GLOBAL latest pair, wrong fit for "what's the baseline for THIS
   inspected run"). Confirm the immediate-prior semantics on a 3-run
   target.
4. **`compare` verb vs `regression compare`** — easy to conflate.
   `compare` is the COMPOSED view (Regression + Coverage delta in one
   envelope); `regression compare` is regression-only. Report any
   confusion in the help text / docs surfaces.
5. **Engine-mismatch / target-mismatch** propagation — seed two runs
   with different `engine_name` (pytest vs jest) on the same target,
   call `regression compare` → expect `reason == "engine-mismatch"`,
   exit 0.

## Notes for the freeze decision

The handoff already pinned three divergences from the brief's idealized
draft (no top-level engine/ecosystem/target fields; inner
`schema_version` retained on `test_transitions[*]` and `*_run_reference`;
`RegressionUnavailable.detail` is nullable). These will land in PM's
freeze decision verbatim from the handoff's "Envelope shape — working
draft for PM" section, anchored on `RegressionFactSet.to_dict()` /
`RegressionUnavailable` source-of-truth. Manual Test does not need to
re-derive the shape; please report any UX friction in the envelope
itself.

## Conflict-resolution notes during merge

None. The merge was a clean fast-forward — base commit `ce1bd44`
matched main's tip exactly; no conflicts to resolve.

## Push status

Awaiting CEO authorization. Per Main Branch charter, never push without
explicit per-push approval.
