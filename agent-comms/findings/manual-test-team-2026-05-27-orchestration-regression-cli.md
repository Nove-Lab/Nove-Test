---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-27
slug: orchestration-regression-cli
related:
  - agent-comms/verifications/2026-05-27-orchestration-regression-cli.md
  - agent-comms/handoffs/orchestration-team-2026-05-27-regression-cli.md
  - agent-comms/decisions/2026-05-26-regression-facts-json-layout.md
verdict: passed
---

# Findings: Phase 3 Regression CLI surface + `inspect` Regression section

## Verdict — **passed**

All 10 verification scenarios + all 5 critical edge cases were exercised
against the merged binary (`c074226`) on this dev host. Every observed
envelope matched the working-draft shape documented in the verification
request, including all three "pinned gotchas". Zero regressions found.
Zero open issues. The slice is shippable as-is and the envelope shape
is, in my read, ready to freeze.

The test gate published in the verification doc was reproduced exactly:
**471 passed + 3 skipped** (the 3 skips are the pre-existing
Node-dependent jest integration tests on this Node-less dev host —
documented in prior cycles).

## What this slice gives the CEO

In plain language: before this slice, Nove Test could *compute* run-to-run
regression facts but had no CLI surface to ask for them. This slice wires
**three new verbs** and **one new section in `inspect`** — pure UI on
top of an already-complete engine — so an AI agent (or a human) can now:

1. **Ask for a regression report between two specific runs** —
   `novetest regression compare <baseline_id> <target_id>` —
   "what changed between these two runs of the same test target?"
2. **Ask for the latest available regression report on the current target** —
   `novetest regression latest` —
   "compare the two most recent runs on what I'm working on right now."
3. **Ask for a composed view** — `novetest compare <baseline_id> <target_id>` —
   regression facts AND coverage delta in one envelope; the AI-facing
   shape that an agent diagnosing "what broke between yesterday and now"
   would naturally want in a single call.
4. **Inspect a single run with full regression context** —
   `novetest inspect <run_id>` now includes a `regression_outcome` block
   automatically baselining against the immediate prior run on the same
   target. Before today this section was hardcoded to `"unavailable"`.

All four behave as documented; the AI envelope shapes are clean,
consistent with prior conventions (Coverage outcome / delta shapes), and
the help text already disambiguates the easy-to-conflate `compare` vs
`regression compare` distinction.

## What was tested (commands + observations)

Each scenario below maps 1:1 to the verification request. Setup used
`/home/yjshin/dev/Nove-Test/tests/manual-test-workspace/regression-cli`
as the scratch Project Store, seeded via the public `store_run_evidence`
seam (same seam the new integration tests use — sidesteps any native
engine dependency on this host).

### Scenario 1 — `regression compare` happy path → ✅

```
novetest regression compare 01MTBASELINE0000000000000A 01MTTARGET000000000000000B
EXIT=0
```

- `envelope.command == "regression.compare"`, `ok == true`
- `regression_outcome.kind == "fact-set"`
- `summary.fixed == 1`, `summary.still_passing == 1`
- All **11 summary keys** present: `regressed`, `fixed`, `still_failing`,
  `still_passing`, `still_skipped`, `newly_skipped`, `newly_active`,
  `added`, `removed`, `total_baseline_tests`, `total_target_tests`
- `test_transitions` length 2, sorted by `node_id`:
  - `tests/x.py::test_a` → `still_passing`
  - `tests/x.py::test_b` → `fixed` (was failed, now passed)
- **Gotcha #1 confirmed:** no top-level `schema_version` on
  `regression_outcome`; inner blocks (`baseline_run_reference`,
  `target_run_reference`, each `test_transitions[*]`) DO carry their
  own `schema_version: 1`.
- **Gotcha #2 confirmed:** only `baseline_engine_name` /
  `baseline_engine_version` / `target_engine_name` /
  `target_engine_version` at top level — no `engine_name`, no
  `ecosystem`, no `target_type`, no `target_expression`.
- `coverage_change == null`, `output_diff == null`, `warnings == []`,
  `metadata == {}` — all as documented.

### Scenario 2 — cache-hit identity → ✅

Re-running the exact same `regression compare` invocation yielded an
identical `derived_at` timestamp (`1779893857734` → `1779893857734`),
proving the cached `regression_facts.json` was read on the second call,
not re-derived. The on-disk path is exactly where the doc said it
would be:

```
.novetest/regression/pairs/run_01MTBASELINE0000000000000A__run_01MTTARGET000000000000000B/
```

### Scenario 3 — bogus run_id short-circuit → ✅

Tested both `bogus_baseline + real_target` AND `real_baseline + bogus_target`.
Both produced identical structure:

- exit `2`, `ok == false`, `data == {}`
- `errors[0].code == "not-found"`
- `errors[0].message == "No Memory Entry for run_id='<the-bogus-id>'"`

The error names which side was bogus (good UX). And — importantly —
this is a CLI transport error (`code: "not-found"`), NOT a
`regression_outcome.kind == "unavailable" / reason: "run-not-found"`.
The handoff explicitly pinned this short-circuit. Confirmed in the wild.

### Scenario 4 — `regression latest` happy path → ✅

```
novetest regression latest
EXIT=0
```

`command == "regression.latest"`, `kind == "fact-set"`,
`baseline_run_reference.run_id == 01MTBASELINE...`,
`target_run_reference.run_id == 01MTTARGET...`,
`summary.fixed == 1`, `summary.still_passing == 1` — same content as
Scenario 1's `regression compare`, just resolved by orchestration
instead of supplied by the caller.

### Scenario 5 — single-run-on-target → ✅

After tearing down and re-seeding with only one run:

- exit `0`, `kind == "unavailable"`,
  `reason == "no-comparable-baseline"`,
  `detail == "tests/"` (the target expression — **not** `"no-runs"`)
- both `baseline_run_reference` and `target_run_reference` are `null`

### Scenario 6 — empty store → ✅

Empty Project Store (no runs at all):

- exit `0`, `kind == "unavailable"`,
  `reason == "no-comparable-baseline"`,
  `detail == "no-runs"` (the reserved literal for this case)
- both refs `null`

Scenarios 5 + 6 together prove the `detail` semantic distinction: same
`reason`, but `detail` carries the disambiguation.

### Scenario 7 — `compare` composed verb → ✅

```
novetest compare 01MTBASELINE0000000000000A 01MTTARGET000000000000000B
EXIT=0
```

- `command == "compare"`, `ok == true`
- `set(envelope.data.keys()) == {"regression_outcome", "coverage_delta"}`
  — exactly the two top-level keys, nothing else
- `regression_outcome.kind == "fact-set"` (the engines did derive)
- `coverage_delta.kind == "unavailable"`,
  `coverage_delta.reason == "missing-derived-facts"` (no `--coverage`
  on the seeded runs, so coverage facts are absent on both sides)

### Scenario 8 — `inspect` Regression section flips → ✅

`inspect <target_run>`:
- `envelope.data.keys()` (sorted) == `["coverage_outcome", "regression_outcome", "run_reference", "run_summary", "sub_reports"]`
  — exactly the 5 documented keys
- `sub_reports == {coverage: "unavailable", regression: "available",
  localization: "unavailable", replay: "unavailable"}` — exactly 4
  sub-report keys, regression flipped from the pre-slice hardcoded
  `"unavailable"` to `"available"`
- `regression_outcome.kind == "fact-set"`,
  `baseline_run_reference.run_id == 01MTBASELINE...`,
  `target_run_reference.run_id == 01MTTARGET...`

`inspect <oldest_run>` (the baseline run, no prior on same target):
- `sub_reports.regression == "unavailable"`
- `regression_outcome.kind == "unavailable"`,
  `reason == "no-comparable-baseline"`
- `baseline_run_reference == null`,
  `target_run_reference == {run_id: 01MTBASELINE..., created_at: ..., schema_version: 1}`
- **Gotcha #3 confirmed:** the refs are independently nullable — the
  inspected ref is populated, the missing-baseline ref is `null`.
  Richer than Coverage's single-ref Unavailable.

### Scenario 9 — `inspect <middle>` baselines against immediate prior → ✅ (load-bearing)

Seeded a 3-run target (A → B → C in chronological order, each with
`test_b` flipping passed/failed/failed). Then:

- `inspect B` → `baseline_run_reference.run_id == A` (immediate prior),
  `target_run_reference.run_id == B`, `summary.fixed == 1` (test_b
  went failed→passed across A↔B), `kind == "fact-set"`,
  `sub_reports.regression == "available"`
- `regression latest` → `baseline == B`, `target == C` (the global
  latest-two pair — different composition!)

This is the load-bearing distinction Main Branch flagged: `inspect` is
NOT calling `resolve_latest_baseline` (which would return B↔C — wrong
for "what's the baseline for the run I just inspected"). It is composing
at the orchestration layer with `find_immediate_prior_run`. Confirmed
in the wild: a 3-run target gives B↔A from `inspect B` and B↔C from
`regression latest` — distinct outputs from distinct compositions.

### Scenario 10 — tombstone-after-cache override → ✅ (strongest hard-fail rule)

1. Derived `regression compare A B` → cache lands at
   `.novetest/regression/pairs/run_A__run_B/regression_facts.json`
2. Tombstoned A via direct Memory API call (`delete_run_evidence` — see
   "Workflow friction" below)
3. Re-called `regression compare A B`

Result:
- exit `0`, `ok == true`
- `regression_outcome.kind == "unavailable"`
- `reason == "run-tombstoned"`
- `detail == "baseline"` — a UX bonus: tells the consumer WHICH side
  was tombstoned (not promised by the verification doc, but a useful
  invariant worth pinning in the freeze decision)
- both refs are populated (so the consumer still knows what pair was
  asked for)

The cached `regression_facts.json` was correctly **not** read.
Decision §C.1 (tombstone-overrides-cache) holds.

## Critical edge cases — all probed

### Edge 1 — Cache-hit `derived_at` identity → ✅

Already proven in Scenario 2. Identical epoch_ms across back-to-back calls.

### Edge 2 — `detail` semantics → ✅

Already proven in Scenarios 5 + 6:
- Single-run-on-target → `detail == "tests/"` (the target expression)
- Empty store → `detail == "no-runs"` (the reserved literal)

Same `reason: "no-comparable-baseline"`, the `detail` field disambiguates.

### Edge 3 — `inspect` baseline-resolution composition → ✅

Already proven in Scenario 9. Confirmed `inspect B` returns A↔B even
though `resolve_latest_baseline` would return B↔C. Distinct
compositions in the orchestration layer.

### Edge 4 — `compare` vs `regression compare` UX disambiguation → ✅

Help-text surfaces are already explicitly defensive against the
conflation risk Main Branch flagged:

- `novetest compare --help` says verbatim:
  > "Distinct from `regression compare` (which emits `regression_outcome`
  > only)."
- `novetest --help` (the index) lists them in distinct groups
  (`group: "regression"` vs `group: "orchestration"`) with distinct
  summaries.

Envelope-shape distinction also confirmed in the wild (Scenarios 1 + 7):
`regression compare` emits one top-level key (`regression_outcome`);
`compare` emits two (`{regression_outcome, coverage_delta}`).

### Edge 5 — Engine-mismatch + target-mismatch propagation → ✅

Seeded a `pytest` baseline + `jest` target on the same target_expression:

- exit `0`, `kind == "unavailable"`, `reason == "engine-mismatch"`
- `detail == "baseline engine_name='pytest' != target engine_name='jest'"`
  — verbose, machine-and-human-parseable, explicit about both sides

Seeded two pytest runs on different `target_expression`s:

- exit `0`, `kind == "unavailable"`, `reason == "target-mismatch"`
- `detail == "baseline target_expression='tests/foo/' != target target_expression='tests/bar/'"`

Both `detail` strings follow a consistent `baseline X != target Y`
template — clean. Worth pinning in the freeze decision (the
verification doc only promised the `reason` value, not the `detail`
format).

### Bonus — uninitialized workspace for all three verbs → ✅

Ran `regression compare`, `regression latest`, AND the composed
`compare` from a directory with no `.novetest/` ancestor. All three
produced identical structure:

- exit `2`, `ok == false`, `data == {}`
- `errors[0].code == "uninitialized"`
- `errors[0].message == "No Project Store found in this directory or
  any ancestor. Run \`novetest init\` to create one."`

Standard `_require_store` path. No traceback leaked. Consistent across
the three new verbs.

## Issues found

**None.** Zero bugs. Zero regressions. Zero envelope-shape divergences.
Zero UX confusion points.

## Workflow friction — for PM (one observation)

Scenario 10 (tombstone-after-cache) is currently exercise-able only by
calling `novetest.memory.store.delete_run_evidence` from a Python
script. There is no CLI verb to tombstone a run (`novetest memory
delete` is queued for a future cycle per prior decisions). This is
fine for engineering — the integration tests cover it — but means
Manual Test cannot exercise the strongest hard-fail invariant
(decision §C.1) through pure CLI commands. **Not a blocker** for this
cycle; flagging as a small UX gap that will close itself when the
Memory CLI surface lands.

A second tiny friction point: my first attempt at Scenario 5 failed
with `[Errno 2] No such file or directory` because the shell's `cwd`
was the directory I had just `rm`'d. The error envelope was
appropriately structured (`command: "cli"`, `errors[0].code:
"cli-error"`), but the message `"[Errno 2] No such file or directory"`
is the raw OS string with no hint of the cause. Could optionally be
upgraded to "current working directory was deleted" or a similar
hint, but this is genuinely a sharp-edge a thoughtful operator would
hit at most once. **Not blocking**.

## Recommendations for PM

1. **Freeze the envelope shape now.** Three back-to-back cycles of
   verification have pinned this shape (engine + facts cycle, baseline
   resolution cycle, this CLI cycle). The three gotchas + the
   independently-nullable refs + the `detail` semantics + the
   `detail` template for mismatch reasons are all behaviorally
   stable. Recommend writing `decisions/2026-05-XX-regression-outcome-envelope-shape.md`
   anchored on `RegressionFactSet.to_dict()` / `RegressionUnavailable`
   as the source of truth, mirroring the existing 2026-05-16 coverage
   shape decisions.

2. **Pin two extras that the verification doc didn't promise but the
   merged code emits consistently:**
   - **`RegressionUnavailable.detail` for tombstoned pairs uses the
     literal `"baseline"` or `"target"`** to tell the consumer which
     side was tombstoned. Worth promising — it's a small, cheap UX
     win that an AI consumer will rely on.
   - **`RegressionUnavailable.detail` for engine-mismatch /
     target-mismatch uses the template
     `"baseline <field>=<value> != target <field>=<value>"`.** Same
     reasoning — predictable templates beat free-form strings for
     agentic consumers.

3. **Tick DoD `[156]`, `[157]`, `[158]`** at cycle-close, per the
   handoff's claim. All three are objectively closed by this
   verification.

4. **Queue a low-priority follow-up for Memory team** to surface a
   `novetest memory delete <run_id>` CLI verb. This will close the
   one Manual-Test-can't-fully-exercise gap (Scenario 10), and is
   also a natural prerequisite for any future cleanup workflow an
   agent might want.

5. **No code changes recommended.** This slice is shippable as-is.

## Test gate (reproduced)

```
uv run pytest -q tests/unit tests/integration
→ 471 passed, 3 skipped in 20.06s
```

Exact match to the verification doc. The 3 skips are the pre-existing
Node-dependent jest integration tests on this Node-less dev host —
documented in prior cycles and explicitly sanctioned.

## Files touched by this verification

- **Wrote:** this file
- **Wrote:** `tests/manual-test-workspace/regression-cli/seed_*.py` (3
  scratch seeding scripts; not committed to source tree — ephemeral
  per `tests/manual-test-workspace/` charter)
- **No source / test / production-fixture modifications.**
