# Quick Start — the canonical happy path (Agent)

The four-step workflow, as an agent consumes it. It uses the working
example from
[README.md](./README.md#the-working-example-used-throughout-this-manual)
— the tiny **`calc`** project (Python + pytest, three green tests). Every
example is the literal `novetest/v1` JSON envelope; pin
`NOVETEST_OUTPUT=json` once at session start so you never depend on TTY
detection.

The four steps:

1. `novetest init` — create the per-project store.
2. `novetest test` — run tests, derive facts, synthesize recommendations.
3. Route on **exit code** + `data.recommendations[].category`.
4. (Optional) `novetest inspect <run_id>` for a single-run aggregate.

For the full exit-code/error-code catalog, recommendation taxonomy, and
discriminated-union shapes, see [after-test.md](./after-test.md).

---

## Envelope frame (every command)

```json
{ "schema": "novetest/v1", "command": "...", "ok": true,
  "data": { }, "errors": [], "warnings": [] }
```

Top-level keys are exactly `schema, command, ok, data, errors, warnings`,
emitted sorted alphabetically. `schema` is always `"novetest/v1"`. There
is **no** top-level `version`, `verb`, or `exit_code` field — the exit
code is the process exit status, not an envelope key. `errors` and
`warnings` are arrays of `{code, message, details}`.

---

## Step 1 — `novetest init`

```bash
NOVETEST_OUTPUT=json novetest init
```

```json
{
  "command": "init",
  "data": {
    "engine_readiness": {
      "ecosystem": "python",
      "engine": "pytest",
      "engine_version": "9.0.3",
      "evidence": ["pyproject.toml"],
      "issues": [],
      "state": "ready"
    },
    "initialized_at": 1782370092699,
    "pinned_engine": {
      "ecosystem": "python",
      "engine_name": "pytest"
    },
    "store_path": "/home/you/calc-demo/.novetest",
    "store_state": "ready"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `data.pinned_engine` | The `(ecosystem, engine_name)` pair `init` **pinned** — every later verb runs this engine; nothing is re-detected at run time. Also on the `status` envelope. |
| `data.engine_readiness.state` | `"ready"` / `"engine-missing"` / `"engine-misconfigured"` — the three real states. Route on this. (`"engine-not-ready"` is **not** a state.) |
| `data.engine_readiness.engine` | Detected `engine_name`, e.g. `"pytest"`. `null` when no engine. |
| `data.engine_readiness.evidence` | Detected marker files, e.g. `["pyproject.toml"]`. |
| `data.engine_readiness.issues` | Human-readable blockers (empty when `ready`). |
| `data.store_state` | `"ready"` on success. |
| `data.initialized_at` | epoch-ms int. |

`init` exits **0** even when `state` is `engine-missing` (the store is
created regardless). Gate "can I run tests?" on
`engine_readiness.state == "ready"`, not on the exit code.

Two `init` outcomes create **nothing** and require routing: exit 4 +
`errors[0].code = "no-engine-detected"` (markerless directory —
`data.candidates[]` lists sub-projects to `cd` into and init) and
exit 2 + `errors[0].code = "engine-ambiguous"` (several viable engines
— re-run `novetest init --engine <name>`). Details:
[languages.md](./languages.md#engine-selection-the-anchored-pin--no-run-time-detection).

### Where to run subsequent verbs from

Any subdirectory of the workspace: every verb walks **up** from cwd to
the nearest `.novetest/` (like git) and anchors there. A bare
`novetest test` is always workspace-scoped regardless of cwd; explicit
relative targets are interpreted **anchor-relative**, so the same
target string from different subdirectories lands in the same baseline
series. No `.novetest/` on the walk → exit 2, `uninitialized`.

---

## Step 2 — `novetest test`

```bash
NOVETEST_OUTPUT=json novetest test
```

All-green envelope:

```json
{
  "command": "test",
  "data": {
    "recommendation_schema_version": 1,
    "recommendations": [
      {
        "category": "all_green",
        "priority": 7,
        "recommendation_id": "rec_01KVYRJJJ75ZRHC05GNKYRK99S_908389d6",
        "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
        "slots": { "passed": 3, "skipped": 0, "total_tests": 3,
                   "run_reference": "01KVYRJJJ75ZRHC05GNKYRK99S" },
        "evidence_citations": [
          { "kind": "run_reference",
            "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S",
                               "created_at": 1782370093639, "schema_version": 1 },
            "selector": {} }
        ]
      }
    ],
    "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S",
                       "created_at": 1782370093639, "schema_version": 1 },
    "stage_eligibility": {
      "coverage": "available", "localization": "unavailable",
      "regression": "available", "replay": "not_run"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Key `data` keys: `recommendations[]`, `run_reference`,
`stage_eligibility`, `recommendation_schema_version`. Each recommendation
has exactly `recommendation_id, category, priority, summary, slots,
evidence_citations` — there is **no `severity` field**; rank on the
integer `priority` (1 = most urgent … 7 = `all_green`).

### Exit-code routing (the contract you build on)

| exit | `ok` | meaning | agent action |
|---|---|---|---|
| 0 | true | tests passed | proceed |
| 3 | true | tests **failed** or **errored** (data, not a tool error) | read `recommendations[]` / `run_record.status`, act on the bug |
| 2 | false | usage / validation (bad flag, unknown run_id, `uninitialized`) | fix the call |
| 4 | false | engine missing / adapter error | check `data.engine_readiness` / `errors[].code` |
| 5 | false | storage error | inspect `.novetest/` |
| 1 | false | generic failure | read `errors[]` |

CRUCIAL: a failing **or errored** test run exits **3 with `ok: true`** —
failing tests (and a suite that errored before producing results,
`run_record.status == "errored"`) are expected results, not transport
errors. Do not treat exit 3 as a crash.

### `stage_eligibility` vocabulary

`coverage` / `regression` ∈ `{available, unavailable, not_applicable}`.
`localization` is the **SBFL mode string** when available
(`sbfl_per_test` / `sbfl_aggregate` / `failure_proximity`), else
`unavailable`. `replay` is **always `not_run`** — `test` never replays.

---

## Step 3 — route on category

```python
import json, os, subprocess
r = subprocess.run(["novetest", "test"],
                   capture_output=True, text=True,
                   env={**os.environ, "NOVETEST_OUTPUT": "json"})
env = json.loads(r.stdout)
recs = env["data"]["recommendations"]
warn = {w["code"] for w in env["warnings"]}
top = min(recs, key=lambda x: x["priority"]) if recs else None   # lowest int = most urgent

if r.returncode == 0 and top and top["category"] == "all_green":
    pass                                       # nothing to do
elif "suite-did-not-execute" in warn:
    # Exit 3, but NOT a test failure: the suite never ran. A collection-time
    # error (a syntax error, a failing module-scope import) stopped the engine
    # before any test executed, so nothing has been learned about the code.
    # There is nothing to localize — read the native engine output, fix the
    # parse/import error, re-run. Check this BEFORE routing on category:
    # the categories below all assume tests actually ran.
    pass
elif r.returncode == 3 and top:
    # top["category"] is one of: investigate_location, investigate_regression,
    # regression_with_localization, coverage_gap, flaky_suspected,
    # unavailable_analysis. (`all_green` never pairs with exit 3.)
    # Only the first three carry a `rank` slot — coverage_gap,
    # flaky_suspected and unavailable_analysis have none, so `locs` is
    # legitimately empty for them and must be guarded before `min()`.
    # Within one category the array is ordered by slots.rank (asc) then
    # score_normalized (desc). Suspects that tie on BOTH are ordered by file
    # path, which carries no evidence, so take the whole leading rank rather
    # than position 0 alone:
    locs = [x for x in recs if x["category"] == top["category"] and "rank" in x["slots"]]
    if locs:
        top_rank = min(x["slots"]["rank"] for x in locs)
        fix_targets = [x["slots"] for x in locs if x["slots"]["rank"] == top_rank]
        # each -> ["file"], ["primary_line"], ["symbol"]
    else:
        fix_targets = [x["slots"] for x in recs if x["category"] == top["category"]]
        # rank-less categories: read the category's own slots
        # (see after-test.md for the per-category slot keys)
```

Three guards, each closing a real crash: `recs` can be empty (nothing to
take a `min` of), `rank` is **not** a universal slot (only
`investigate_location`, `investigate_regression` and
`regression_with_localization` carry one), and exit 3 does not imply a
test failed — a suite that fails to *collect* also exits 3, with the
`suite-did-not-execute` warning as the only positive signal that no test
ever ran.

The seven categories (closed taxonomy) and the full routing tree are in
[after-test.md](./after-test.md#closed-taxonomy-7-categories).

---

## Step 4 — `novetest inspect <run_id>`

A pure read (executes nothing) that aggregates the four derived
sub-reports for one run. Each sub-report is a discriminated union — switch
on `kind`:

```bash
NOVETEST_OUTPUT=json novetest inspect 01KVYRJJJ75ZRHC05GNKYRK99S
```

```json
{
  "command": "inspect",
  "data": {
    "coverage_outcome":   { "kind": "fact-set", "mapping_granularity": "per-test",
                            "summary": { "percent_covered": 100.0, "num_statements": 13,
                                         "covered_statements": 13, "missing_statements": 0, "...": "..." },
                            "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S", "...": "..." } },
    "regression_outcome": { "kind": "fact-set",
                            "summary": { "regressed": 0, "fixed": 0, "still_passing": 3,
                                         "still_failing": 0, "total_target_tests": 3, "...": "..." },
                            "test_transitions": [ { "node_id": "...", "category": "still_passing", "...": "..." } ],
                            "...": "..." },
    "localization_outcome": { "kind": "unavailable", "reason": "missing-derived-facts",
                              "detail": "findings not yet derived", "run_reference": { "...": "..." } },
    "replay_outcome":     { "kind": "unavailable", "reason": "missing-derived-facts",
                            "detail": "no replay attempt has been made for this run", "...": "..." },
    "run_summary": { "ecosystem": "python", "engine_name": "pytest", "status": "passed",
                     "summary_counts": { "collected": 3, "passed": 3, "total": 3 },
                     "target_expression": "", "target_type": "workspace", "tombstoned": false },
    "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S", "...": "..." },
    "sub_reports": { "coverage": "available", "localization": "unavailable",
                     "regression": "available", "replay": "unavailable" }
  },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": []
}
```

- `kind == "fact-set"` → the data is present (coverage/regression here).
- `kind == "unavailable"` → carries `reason` + `detail`. Reason spelling
  is **hyphenated** across all engines — `missing-derived-facts` is the
  literal same token from coverage, regression, replay, AND
  localization, so one matcher covers every sub-report.
- `data.sub_reports` is the quick availability map (mirrors
  `stage_eligibility`, minus the SBFL-mode detail).
- A stale/unknown `run_id` → `errors[].code == "not-found"`, exit **2**.

The full per-block field reference (coverage summary keys, regression
`test_transitions[].category` taxonomy, localization `entries[]`) lives in
[after-test.md](./after-test.md) and [advanced.md](./advanced.md).

---

## What to read next

- **[languages.md](./languages.md)** — engine detection, the
  `engine_readiness` envelope per ecosystem, and which engines produce
  coverage facts.
- **[after-test.md](./after-test.md)** — exit codes, `errors[].code`
  catalog, the 7-category routing tree, and the failing-run envelope.
- **[advanced.md](./advanced.md)** — `coverage diff`, `regression
  compare` / `latest` / `compare`, `localization` formulas, `replay`,
  `memory` lifecycle.
