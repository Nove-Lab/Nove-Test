# Quick Start — the canonical happy path (Agent)

The 4-step canonical workflow. We use the working example from
[README.md](./README.md#the-working-example-used-throughout-this-manual)
(a tiny Python + pytest project with 3 green tests). Every example
on this page is the literal `novetest/v1` JSON envelope.

The four steps:

1. `novetest init` — create the per-project store.
2. `novetest test` — run tests, derive facts, synthesize recommendations.
3. Parse the envelope; route on exit code + `recommendations[].category`.
4. (Optional) `novetest inspect <run_id>` for a single-run aggregate envelope.

For exit-code semantics, error codes, and the full recommendation
taxonomy, see [after-test.md](./after-test.md).

---

## Step 1 — `novetest init`

```bash
cd my-project
NOVETEST_OUTPUT=json novetest init
```

Envelope:

```json
{
  "schema": "novetest/v1",
  "command": "init",
  "ok": true,
  "data": {
    "store_path": "/home/you/my-project/.novetest",
    "store_state": "ready",
    "initialized_at": 1717939496000,
    "engine_readiness": {
      "state": "ready",
      "engine": "pytest",
      "ecosystem": "python",
      "engine_version": "8.0.0",
      "evidence": [
        "pyproject.toml detected",
        "pytest importable"
      ],
      "issues": []
    }
  },
  "errors": [],
  "warnings": []
}
```

| Field | Type | Meaning |
|---|---|---|
| `data.store_path` | string | Absolute path of the new `.novetest/` directory. |
| `data.store_state` | string | `"ready"` on the happy path. |
| `data.initialized_at` | int (epoch-ms) | Init timestamp. |
| `data.engine_readiness.state` | string | `"ready"` / `"engine-missing"` / `"engine-misconfigured"` / `"engine-not-ready"`. Route on this. |
| `data.engine_readiness.engine` | string | `"pytest"` / `"jest"` / `"gotest"` / `"cargo-nextest"` / `"junit"` / `"xunit"`. |
| `data.engine_readiness.ecosystem` | string | `"python"` / `"javascript-typescript"` / `"go"` / `"rust"` / `"java"` / `"dotnet"`. |
| `data.engine_readiness.evidence[]` | string list | Workspace markers used to identify the engine. |
| `data.engine_readiness.issues[]` | string list | Empty on the happy path; carries actionable hints when state is not `"ready"`. |

Exit code: **0** on the happy path. **2** only if `init` runs against
a directory with a corrupt store (very rare); fix or `rm -rf .novetest`
and re-run.

### Project Store layout `init` creates

```
.novetest/
├── store.json              # schema_version, initialized_at, store_state
├── memory/
│   ├── runs/               # one Run Record per execution
│   └── tombstones/         # soft-deleted entries
├── run/
│   ├── artifacts/          # native engine raw output + logs
│   └── readiness/          # cached readiness probe result
├── coverage/facts/         # per-run Coverage Facts
├── regression/pairs/       # cached Regression Facts per (baseline,target) pair
├── localization/findings/  # SBFL findings per run
├── replay/results/         # Replay Results per replay
└── orchestration/
    ├── recommendations/    # synthesized recommendations
    └── status/             # latest cached status snapshot
```

`init` is fully idempotent.

### Where to run subsequent verbs from

Nove Test locates the active Project Store via parent-directory walk-up
(same algorithm as `git` finding `.git/`). Starting from `cwd` and
walking ancestors, the first directory containing `.novetest/` becomes
the active store.

If no ancestor contains `.novetest/`, every non-`init` verb returns:

```json
{
  "schema": "novetest/v1",
  "command": "test",
  "ok": false,
  "data": {},
  "errors": [
    {
      "code": "uninitialized",
      "message": "No Project Store found in this directory or any ancestor. Run `novetest init` to create one.",
      "details": {}
    }
  ],
  "warnings": []
}
```

Exit code: **2**.

Override: `NOVETEST_HOME=/absolute/path/to/.novetest` pins the active
store explicitly and skips the walk-up. Use this only for hermetic
harnesses; agents driving a single project should not need it.

---

## Step 2 — `novetest test`

```bash
NOVETEST_OUTPUT=json novetest test
```

Equivalent invocations:

```bash
novetest test                  # whole-workspace target
novetest test tests/           # explicit target
novetest tests/                # bare default-verb alias — same as above
```

Use the explicit `novetest test <target>` form in scripts. The bare
alias is a TTY convenience.

### Envelope (all-green happy case)

```json
{
  "schema": "novetest/v1",
  "command": "test",
  "ok": true,
  "data": {
    "run_reference": {
      "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
      "created_at": 1717951353000
    },
    "stage_eligibility": {
      "coverage": "available",
      "regression": "unavailable",
      "localization": "available",
      "replay": "not_run"
    },
    "recommendation_schema_version": 1,
    "recommendations": [
      {
        "recommendation_id": "rec_001",
        "category": "all_green",
        "priority": 7,
        "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
        "slots": {
          "passed": 3,
          "skipped": 0,
          "total_tests": 3,
          "run_reference": {
            "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "created_at": 1717951353000
          }
        },
        "evidence_citations": [
          {
            "kind": "run_reference",
            "run_reference": {
              "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
              "created_at": 1717951353000
            },
            "selector": {}
          }
        ]
      }
    ]
  },
  "errors": [],
  "warnings": []
}
```

Exit code: **0** (tests passed). If your tests had failed (a normal,
non-error outcome), `ok` would still be `true` but exit code would be
**3**.

### What `novetest test` runs, in order

1. **Run** — invokes the native engine, captures structured per-test results, persists a Run Record.
2. **Coverage** — drives the engine in coverage mode, persists Coverage Facts. Reports `stage_eligibility.coverage = "unavailable"` if the coverage tool is not installed; the run does NOT fail.
3. **Regression** — resolves the latest comparable baseline (the immediately preceding successful run on the same target) and persists Regression Facts. On the first run there is no baseline → `"unavailable"`.
4. **Localization** — derives SBFL fault-localization findings (Ochiai by default). With zero failing tests → may report `"unavailable"` or degrade to `"failure_proximity"` mode.
5. **Synthesize recommendations** — picks deterministic recommendations from the facts above. Recommendations are kept **in-memory** during the call and NOT persisted; re-running `novetest test` always re-synthesizes from the latest derived facts.

The only hard failures are: engine missing (exit 4), bad usage
(exit 2), or a corrupt Project Store (exit 5).

---

## Step 3 — parse the envelope and decide

This is the entire point of the envelope: deterministic routing.

### Decision A — did the CLI itself succeed?

```python
ok = envelope["ok"]
```

`ok: true` → CLI did its job. `ok: false` → structural failure (engine
missing, store corrupt, parse error, bad usage). Test failures are NOT
`ok: false` — they are real product data surfaced via exit code 3 and
via the recommendation set.

### Decision B — did the user's tests pass?

```python
if exit_code == 0:
    # ok: true, tests passed
elif exit_code == 3:
    # ok: true, tests failed — read recommendations, fix tests
elif exit_code in (2, 4, 5):
    # ok: false, structural failure — read errors[]
elif exit_code == 1:
    # ok: false, unexpected CLI exception — report as bug
```

Full table: [after-test.md §Exit codes](./after-test.md#exit-codes).

### Decision C — which derived stages are usable?

```python
stages = envelope["data"]["stage_eligibility"]
# stages["coverage"] / ["regression"] / ["localization"] / ["replay"]
# each ∈ {"available", "unavailable", "not_run"}
```

- `"available"` — the stage derived facts and persisted them. Queryable via per-stage verbs (`coverage show`, `regression latest`, `localization`).
- `"unavailable"` — structural reason (no baseline yet, no failing tests for SBFL, …). NOT an error.
- `"not_run"` — the integrated workflow deliberately skipped this stage. At MVP only `replay` is `"not_run"` by default.

### Decision D — what to act on

```python
recs = envelope["data"]["recommendations"]
recs_sorted = sorted(recs, key=lambda r: -r["priority"])
top = recs_sorted[0] if recs_sorted else None

if top is None:
    return  # nothing to do
elif top["category"] == "all_green":
    return  # nothing to do
elif top["category"] in {"tests_failed", "new_test_failure"}:
    for cite in top["evidence_citations"]:
        if cite["kind"] == "test_result":
            test_id = cite["selector"]["test_id"]
            outcome = cite["selector"]["outcome"]
            # Inspect the run to get error details / stdout / stderr.
elif top["category"] == "coverage_regressed":
    # Walk evidence_citations for the coverage-file deltas.
    ...
elif top["category"] == "unavailable_analysis":
    # Informational; usually no agent action needed.
    ...
```

The key invariant: **route on `category` first**; walk
`evidence_citations[]` for structured pointers. Do NOT parse
`summary` — it is for humans.

For the full closed taxonomy of categories and their slots, see
[after-test.md §recommendations\[\]](./after-test.md#datarecommendations).

---

## Step 4 — (optional) drill into the run with `inspect`

```bash
NOVETEST_OUTPUT=json novetest inspect 01ARZ3NDEKTSV4RRFFQ69G5FAV
```

Aggregates Run Record + Coverage Facts + Regression Facts +
Localization Findings + Replay Results into one envelope. Discriminated
unions everywhere — switch on `kind` first:

```json
{
  "schema": "novetest/v1",
  "command": "inspect",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "...", "created_at": 1717951353000 },
    "memory_entry": {
      "schema_version": 1,
      "entry_id": "...",
      "run_record": { /* full Run Record */ },
      "stored_at": 1717951367000,
      "has_coverage_facts": true,
      "has_regression_facts": false,
      "has_localization_findings": true,
      "has_replay_result": false,
      "tombstoned_at": null
    },
    "coverage_outcome":     { "kind": "fact-set",  /* ... */ },
    "regression_outcome":   { "kind": "unavailable", "reason": "no-comparable-baseline" },
    "localization_outcome": { "kind": "fact-set",  /* ... */ },
    "replay_outcome":       { "kind": "unavailable", "reason": "not-run" }
  },
  "errors": [],
  "warnings": []
}
```

Discriminator field:

- `coverage_outcome.kind`     ∈ {`"fact-set"`, `"unavailable"`}
- `regression_outcome.kind`   ∈ {`"fact-set"`, `"unavailable"`}
- `localization_outcome.kind` ∈ {`"fact-set"`, `"unavailable"`}
- `replay_outcome.kind`       ∈ {`"replay-result"`, `"unavailable"`}

Always switch on `kind` first; never assume a `"fact-set"` shape is
present.

Full field-by-field interpretation: [after-test.md §inspect](./after-test.md#novetest-inspect-run_id).

When to call `inspect`:

- You need the raw coverage `summary` block.
- You need to walk the SBFL `entries[]` rankings.
- You want to audit a recommendation's citations end-to-end.
- You are debugging why `stage_eligibility` reported `"unavailable"` —
  the per-stage `reason` field is more detailed than the summary
  value.

---

## Two patterns to internalize

1. **One canonical command.** `novetest test` is the single call.
   Do not stitch together `run` + `coverage show` + `regression
   compare` + `localization` by hand for the happy path.
2. **Envelope is the contract.** Do not parse stdout, do not grep
   human-readable output. Always pin `NOVETEST_OUTPUT=json` and parse
   the envelope. Every shape on this page is what the CLI
   guarantees.

---

## What to read next

- Your project is not Python → [languages.md](./languages.md).
- Want the full exit-code table, `errors[].code` catalog, and
  recommendation taxonomy → [after-test.md](./after-test.md).
- Need a deeper verb → [advanced.md](./advanced.md).
- An envelope came back `ok: false` → [troubleshooting.md](./troubleshooting.md).
