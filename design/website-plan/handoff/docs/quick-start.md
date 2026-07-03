# Quick Start

This page covers the four-step canonical workflow, end to end:

1. `novetest init` — create the per-project store under `.novetest/`.
2. `novetest test` — run tests, derive coverage / regression /
   localization, synthesize a recommendation.
3. Read (human) or route on (agent) the recommendation.
4. (Optional) `novetest inspect <run_id>` — drill into one run.

Throughout, the running example is **`calc`**, a tiny Python + pytest
package with three green tests:

```
calc-demo/
├── pyproject.toml          # [tool.pytest.ini_options] testpaths=["tests"] pythonpath=["."]
├── calc/
│   ├── __init__.py
│   └── arithmetic.py       # def add(a,b): return a+b   /   def subtract(a,b): return a-b
└── tests/
    └── test_arithmetic.py  # test_add_positive, test_add_zero, test_subtract
```

You need `python >= 3.11` and `pytest` on PATH (the native engine Nove
Test shells out to). The `novetest` binary bundles its own Python — see
[Installation](./installation.md).

---

## Step 1 — `novetest init`

Run once from the project root.

::: tabs
@tab For human

```bash
cd calc-demo
novetest init
```

```
✓ Initialized .novetest/ at /home/you/calc-demo/.novetest
  engine readiness: ready — python/pytest 9.0.3
```

Nove Test detected `pytest` from `pyproject.toml` and **pinned** it —
every later verb runs the pinned engine; nothing is re-detected at run
time. `ready` means the engine resolved; the `9.0.3` is **your**
pytest version. If you see `engine-missing` / `engine-misconfigured`,
the next `issue:` line says what to fix
([Troubleshooting](./troubleshooting.md)).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest init
```

```json
{
  "command": "init",
  "data": {
    "engine_readiness": {
      "ecosystem": "python", "engine": "pytest", "engine_version": "9.0.3",
      "evidence": ["pyproject.toml"], "issues": [], "state": "ready"
    },
    "initialized_at": 1782370092699,
    "pinned_engine": {"ecosystem": "python", "engine_name": "pytest"},
    "store_path": "/home/you/calc-demo/.novetest",
    "store_state": "ready"
  },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": []
}
```

Gate "can I run tests?" on `data.engine_readiness.state == "ready"`. The
three real states are `ready` / `engine-missing` / `engine-misconfigured`
(there is no `engine-not-ready`). `init` exits **0** even when an engine
is missing — the store is still created.

:::

`init` creates the `.novetest/` Project Store:

```
.novetest/
├── store.json          # schema_version, initialized_at, store_state
├── blobs/
├── memory/{runs,tombstones}/
├── run/                # run/artifacts/ created on first run
├── coverage/           # coverage/facts/ on first coverage derive
├── regression/         # regression/pairs/ on first comparison
├── localization/       # localization/findings/ on first SBFL run
├── replay/             # replay/results/ on first replay
└── orchestration/      # reserved; recommendations are computed live, not stored
```

Each engine creates its leaf subdirectory lazily on first write, so right
after `init` only the parent directories above exist. Nove Test finds the
store by walking up from your current directory (like
`git` finds `.git/`). Run a verb with no `.novetest/` in any ancestor and
you get `uninitialized` (exit 2).

---

## Step 2 — `novetest test`

The headline verb: it runs the tests, stores a Run Record, derives
coverage / regression / localization where it can, and synthesizes a
recommendation. It **always** collects coverage (there is no `--coverage`
flag on `test`; only the lower-level `novetest run` has `--coverage` /
`-c`).

::: tabs
@tab For human

```bash
novetest test
```

```
1 recommendation · 1 category · run_id=01KVYRJJJ75ZRHC05GNKYRK99S

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJJ75ZRHC05GNKYRK99S
```

Exit code **0**. The header gives the count + `run_id`; the block is a
glyph + `[category]` + summary + `↳` citation. `[all_green]` is one of a
closed set of **seven** categories, each with an integer `priority`
(1 = most urgent … 7 = all green).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest test
```

```json
{
  "command": "test",
  "data": {
    "recommendation_schema_version": 1,
    "recommendations": [
      { "category": "all_green", "priority": 7,
        "recommendation_id": "rec_01KVYRJJJ75ZRHC05GNKYRK99S_908389d6",
        "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
        "slots": { "passed": 3, "skipped": 0, "total_tests": 3,
                   "run_reference": "01KVYRJJJ75ZRHC05GNKYRK99S" },
        "evidence_citations": [ { "kind": "run_reference", "selector": {},
          "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S",
                             "created_at": 1782370093639, "schema_version": 1 } } ] }
    ],
    "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S",
                       "created_at": 1782370093639, "schema_version": 1 },
    "stage_eligibility": { "coverage": "available", "localization": "unavailable",
                           "regression": "available", "replay": "not_run" }
  },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": []
}
```

Recommendations carry an integer `priority` (no `severity` field).
`stage_eligibility.localization` is the SBFL **mode** when available;
`replay` is always `not_run`. See the exit-code contract below.

:::

> **Shortcut:** `novetest <path>` ≡ `novetest test <path>` — any first
> argument that is not a known verb is treated as a test target. Bare
> `novetest` prints help; it does not run tests.

### Exit-code contract

| exit | `ok` | meaning |
|---|---|---|
| 0 | true | tests passed |
| 3 | **true** | tests **failed** (a result, not a crash) — read `recommendations[]` |
| 2 | false | usage / validation / `uninitialized` / unknown run_id |
| 4 | false | engine missing / adapter error |
| 5 | false | storage error |
| 1 | false | generic failure |

A failing run is **exit 3 with `ok: true`**. Do not treat it as a tool
error.

---

## Step 3 — read / route on the recommendation

::: tabs
@tab For human

On the happy path there is nothing to do — `[all_green]` means everything
passed. When a test fails, `test` emits one or more
`[investigate_location]` recommendations that pin the most suspicious code
(and exits 3). The full green → bug → fix walkthrough is in
[Understanding Results](./understanding-results.md).

`novetest status` summarizes the latest run's analysis availability:

```
latest run · 01KVYRJK97SSR5DR840PH26VQK · history: 4 runs

  — coverage      unavailable
  — regression    unavailable
  — localization  unavailable
  — replay        unavailable
```

`—` means "unavailable for a structural reason" (no coverage collected,
no failing tests to localize, etc.) — not an error.

@tab For agent

```python
recs = env["data"]["recommendations"]
top = min(recs, key=lambda r: r["priority"])   # lowest priority int = top category
if returncode == 0 and top["category"] == "all_green":
    pass
elif returncode == 3:
    # The array is NOT score-ordered: for a location-bearing category, pick the
    # strongest finding by slots.rank (asc) then score_normalized (desc) —
    # recs[0] here is add@2 (rank 2, score 0.0), but the culprit is subtract@6.
    locs = [r for r in recs if r["category"] == top["category"] and "rank" in r["slots"]]
    best = min(locs, key=lambda r: (r["slots"]["rank"], -r["slots"]["score_normalized"]))
    act_on(best["slots"])   # -> ["file"], ["primary_line"], ["symbol"]
```

Route on the lowest `priority` integer for the top category; within a
location-bearing category, rank by `slots.rank`/`score_normalized` (not
array order). The full decision tree is in
[Understanding Results](./understanding-results.md#routing-decision-tree).

:::

---

## Step 4 — (optional) `novetest inspect <run_id>`

A pure read (executes nothing) that aggregates the four derived
sub-reports for one run.

::: tabs
@tab For human

```bash
novetest inspect 01KVYRJJJ75ZRHC05GNKYRK99S
```

```
✓ 01KVYRJJJ75ZRHC05GNKYRK99S · passed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 13/13 statements (100.0%)
  regression    ✓ clean · regressed=0 fixed=0 still_failing=0
  localization  — unavailable (missing_derived_facts)
  replay        ? unavailable (missing-derived-facts)
```

Coverage is present (`test` always collects it); regression is clean
(compared against the prior run); localization is unavailable (a passing
run has nothing to rank); replay is unavailable until you explicitly run
`novetest replay <run_id>`.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest inspect 01KVYRJJJ75ZRHC05GNKYRK99S
```

Each sub-report under `data` is a discriminated union — switch on `kind`
(`"fact-set"` vs `"unavailable"`):

```json
{ "command": "inspect",
  "data": {
    "coverage_outcome":   { "kind": "fact-set", "mapping_granularity": "per-test",
                            "summary": { "percent_covered": 100.0, "num_statements": 13, "...": "..." } },
    "regression_outcome": { "kind": "fact-set",
                            "summary": { "regressed": 0, "still_passing": 3, "...": "..." }, "...": "..." },
    "localization_outcome": { "kind": "unavailable", "reason": "missing_derived_facts", "...": "..." },
    "replay_outcome":     { "kind": "unavailable", "reason": "missing-derived-facts", "...": "..." },
    "run_summary": { "engine_name": "pytest", "status": "passed", "...": "..." },
    "sub_reports": { "coverage": "available", "localization": "unavailable",
                     "regression": "available", "replay": "unavailable" } },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": [] }
```

A stale/unknown `run_id` → `errors[].code == "not-found"`, exit 2.

:::

---

## What to read next

- **[Supported Languages](./supported-languages.md)** — the one toolchain
  difference your engine needs if `calc` were jest / go-test / cargo-test
  / JUnit / xUnit.
- **[Understanding Results](./understanding-results.md)** — exit codes,
  the seven recommendation categories, and the green → bug → fix
  walkthrough.
- **[Advanced Usage](./advanced-usage.md)** — `coverage diff`,
  `regression compare`, `localization` formulas, `replay`, `memory`
  lifecycle.
