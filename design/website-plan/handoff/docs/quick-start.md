# Quick Start

The 4-step canonical workflow — from a freshly installed binary to
"I ran tests and read the recommendation". We use the [working
example](./introduction.md#the-working-example-used-throughout-these-docs)
from the Introduction: a tiny Python + pytest project with three
green tests.

The four steps:

1. `novetest init` — create the per-project store under `.novetest/`.
2. `novetest test` — run tests, derive coverage / regression /
   localization, synthesize a recommendation.
3. Read the recommendation.
4. (Optional) `novetest inspect <run_id>` to dig deeper.

For everything beyond step 2 (`status`, `inspect` with all
sub-reports, `replay`), see
[Understanding Results](./understanding-results.md). For
language-specific toolchain notes, see
[Supported Languages](./supported-languages.md).

---

## Step 1 — `novetest init`

Run from the project root (the directory that contains
`pyproject.toml` in our example).

::: tabs
@tab For human

```bash
cd my-project
novetest init
```

You should see:

```
✓ Initialized .novetest/ at /home/you/my-project/.novetest
  engine readiness: ready — python/pytest 8.0.0
```

What just happened:

- A `.novetest/` directory was created. It holds every Run Record,
  Coverage Facts set, Regression Facts set, Localization Findings
  set, and Replay Result for this project — as plain JSON files.
- novetest auto-detected your engine (`pytest`) from
  `pyproject.toml`. The `engine readiness: ready` line means the
  native engine is fully installed and ready to run.

If you see `engine readiness: engine-missing` or
`engine-misconfigured` instead, the next line(s) will be
`issue: ...` explaining what to fix. See
[Troubleshooting -> init issues](./troubleshooting.md#init-issues).

@tab For agent

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
| `data.engine_readiness.state` | string | `"ready"` / `"engine-missing"` / `"engine-misconfigured"` / `"engine-not-ready"`. **Route on this.** |
| `data.engine_readiness.engine` | string | `"pytest"` / `"jest"` / `"gotest"` / `"cargo-nextest"` / `"junit"` / `"xunit"`. |
| `data.engine_readiness.ecosystem` | string | `"python"` / `"javascript-typescript"` / `"go"` / `"rust"` / `"java"` / `"dotnet"`. |
| `data.engine_readiness.evidence[]` | string list | Workspace markers used to identify the engine. |
| `data.engine_readiness.issues[]` | string list | Empty on the happy path; carries actionable hints when state is not `"ready"`. |

Exit code: **0** on the happy path. **2** only if `init` runs against
a directory with a corrupt store (very rare); fix or
`rm -rf .novetest` and re-run.

:::

### Where do I run `novetest test` from?

Anywhere inside `my-project/` (the project root or any
subdirectory). novetest walks up from your current working
directory to find `.novetest/`, just like `git` finds `.git/`.
Running from a directory whose ancestors do not contain
`.novetest/` returns an `uninitialized` error.

Override: `NOVETEST_HOME=/absolute/path/to/.novetest` pins the
active store explicitly and skips the walk-up. Use this only for
hermetic harnesses.

### Directory tree created by `init`

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

You usually do not need to look inside. The CLI manages this for
you.

`init` is fully idempotent — re-running it on an already-initialized
project does nothing destructive.

---

## Step 2 — `novetest test`

This is the single command that does everything.

::: tabs
@tab For human

```bash
novetest test
```

Or, equivalently:

```bash
novetest test tests/
novetest tests/        # bare default-verb alias — same thing as above
```

We recommend the explicit `novetest test` form in scripts. The bare
alias is handy at the prompt.

You should see:

```
1 recommendation · 1 category · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Read top to bottom:

- **Summary line.** "1 recommendation · 1 category · run_id=..." —
  novetest had one thing to tell you, in one category, for a run
  with this ULID.
- **Glyph + category.** `✓` means "good news"; `[all_green]` is the
  category from the closed taxonomy. Other categories you may see:
  `[tests_failed]`, `[coverage_regressed]`, `[new_test_failure]`,
  `[flaky_suspect]`, `[unavailable_analysis]`.
- **Sentence.** A self-contained English sentence summarizing the
  recommendation. You can act on this directly.
- **Citation arrow.** `↳ run_reference 01HX...` points at the Run
  Record this recommendation is based on. Copy that ULID to drill
  in with `novetest inspect`.

Exit code: **0** because the tests passed. If your tests had
failed, the exit code would be **3** (not 1) — that is meaningful
product data, not an error. See
[Understanding Results -> Exit codes](./understanding-results.md#exit-codes)
for the full table.

@tab For agent

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

Envelope (all-green happy case):

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
non-error outcome), `ok` would still be `true` but exit code would
be **3**.

:::

### What `novetest test` did under the hood

1. **Ran** the native engine (`pytest`) and persisted a Run Record
   under `.novetest/memory/runs/`.
2. **Derived coverage** (via `pytest-cov`, if installed) and
   persisted facts under `.novetest/coverage/facts/`.
3. **Resolved a regression baseline** — the immediately preceding
   run on the same target. On the very first run there is no
   baseline, so this stage simply reports "unavailable".
4. **Computed SBFL fault localization** (Ochiai by default). With
   zero failing tests there is nothing to localize, so this stage
   may report "unavailable" too — that is expected, not an error.
5. **Synthesized recommendations** — picked deterministic
   recommendations from the facts above and printed them.

The five stages run in order. If a stage fails its readiness check
(e.g. `pytest-cov` not installed), `novetest test` does not abort
— it records the stage as "unavailable" and continues. The only
hard failures are: engine missing (exit 4), bad usage (exit 2), or
a corrupt Project Store (exit 5).

### Working with coverage

Coverage is auto-enabled when `pytest-cov` is present. If you do
not have it installed yet:

```bash
pip install pytest-cov
novetest test
```

You should now see a `✓` for coverage in the deeper view (`novetest
inspect <run_id>`, covered in step 4 below).

---

## Step 3 — Read the recommendation (or, for agents, route on it)

For the all-green happy case there is exactly one recommendation
and it tells you everything you need: nothing to do. You are done.

For non-trivial outcomes the same shape applies.

::: tabs
@tab For human

For non-trivial outcomes, read the recommendation block top to
bottom:

```
3 recommendations · 2 categories · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ! [tests_failed] 2 tests failed in tests/test_math_utils.py.
      ↳ test_result tests/test_math_utils.py::test_add_positive (failed)
  ! [tests_failed] (continued — see inspect for full list)
      ↳ test_result tests/test_math_utils.py::test_subtract (failed)
  ✓ [unavailable_analysis] Localization unavailable — no baseline yet.
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Two cues:

- **`!`** in front of `[tests_failed]` — needs action.
- **`✓`** in front of `[unavailable_analysis]` — informational, no
  action.

A pattern emerges: glyph carries urgency, category carries kind,
sentence carries detail, citation carries the pointer back.

Multiple recommendations are listed in priority order (most urgent
first). You can usually act on the top recommendation, re-run
`novetest test`, and re-read the new output.

For a worked example walking through "green -> fail -> green" with
real failure output, see
[Understanding Results -> A worked example](./understanding-results.md#a-worked-example-green--fail--green).

@tab For agent

This is the entire point of the envelope: deterministic routing.

#### Decision A — did the CLI itself succeed?

```python
ok = envelope["ok"]
```

`ok: true` -> CLI did its job. `ok: false` -> structural failure
(engine missing, store corrupt, parse error, bad usage). Test
failures are NOT `ok: false` — they are real product data surfaced
via exit code 3 and via the recommendation set.

#### Decision B — did the user's tests pass?

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

Full table:
[Understanding Results -> Exit codes](./understanding-results.md#exit-codes).

#### Decision C — which derived stages are usable?

```python
stages = envelope["data"]["stage_eligibility"]
# stages["coverage"] / ["regression"] / ["localization"] / ["replay"]
# each in {"available", "unavailable", "not_run"}
```

- `"available"` — the stage derived facts and persisted them.
  Queryable via per-stage verbs (`coverage show`, `regression
  latest`, `localization`).
- `"unavailable"` — structural reason (no baseline yet, no failing
  tests for SBFL, ...). **NOT an error.**
- `"not_run"` — the integrated workflow deliberately skipped this
  stage. At MVP only `replay` is `"not_run"` by default.

#### Decision D — what to act on

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
[Understanding Results -> `data.recommendations[]`](./understanding-results.md#datarecommendations).

:::

---

## Step 4 — (optional) drill into the run with `inspect`

If you want to see everything for a single run on one screen:

::: tabs
@tab For human

```bash
novetest inspect 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

You should see:

```
✓ 01HX0K4M5N6P7Q8R9STUVWXYZ0 · passed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 10/11 statements (86.7%)
  regression    — unavailable (no-comparable-baseline)
  localization  — unavailable (no_failed_tests)
  replay        ? unavailable (not-run)
```

Read it like this:

- **Header line.** `✓` (passed), the run's ULID, the engine +
  ecosystem, and what target you ran. `target=<workspace>` is the
  explicit token for "the whole project".
- **Four sub-report lines.** One per engine — each gives you the
  kind-discriminated outcome (`✓ <fact-set summary>` if facts were
  derived, `—` or `?` followed by a reason if not).

Reasons you will commonly see in the happy path:

| Reason | Meaning |
|---|---|
| `no-comparable-baseline` | First run on this target. There is nothing to compare against; the next run will populate it. |
| `no_failed_tests` | SBFL had no failures to attribute, so nothing to rank. (Expected on green runs.) |
| `not-run` | `novetest test` deliberately did not auto-invoke replay (it would multiply wall time). Call `novetest replay <run_id>` explicitly if you want it. |

You do **not** need `inspect` for the simple happy case — the
recommendation from `novetest test` is enough. Reach for `inspect`
when you want a raw audit trail or are debugging why a stage
reported "unavailable".

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest inspect 01ARZ3NDEKTSV4RRFFQ69G5FAV
```

Aggregates Run Record + Coverage Facts + Regression Facts +
Localization Findings + Replay Results into one envelope.
Discriminated unions everywhere — switch on `kind` first:

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

- `coverage_outcome.kind`     in `{"fact-set", "unavailable"}`
- `regression_outcome.kind`   in `{"fact-set", "unavailable"}`
- `localization_outcome.kind` in `{"fact-set", "unavailable"}`
- `replay_outcome.kind`       in `{"replay-result", "unavailable"}`

Always switch on `kind` first; never assume a `"fact-set"` shape is
present.

Full field-by-field interpretation:
[Understanding Results -> `novetest inspect <run_id>` envelope](./understanding-results.md#novetest-inspect-run_id-envelope).

When to call `inspect`:

- You need the raw coverage `summary` block.
- You need to walk the SBFL `entries[]` rankings.
- You want to audit a recommendation's citations end-to-end.
- You are debugging why `stage_eligibility` reported
  `"unavailable"` — the per-stage `reason` field is more detailed
  than the summary value.

:::

---

## Two patterns to internalize

1. **One canonical command.** `novetest test` is the single call.
   Do not stitch together `run` + `coverage show` + `regression
   compare` + `localization` by hand for the happy path; `test`
   does it in the right order with the right defaults.
2. **The output is a contract.** For humans: glyph + category +
   sentence + citation, every recommendation, every time. For
   agents: route on the envelope; never parse stdout text.

---

## What to read next

- Your project is not Python → [Supported Languages](./supported-languages.md).
- You want to interpret a `tests_failed`, dig into a failing run,
  or see the exit-code table →
  [Understanding Results](./understanding-results.md).
- You suspect you need a deeper verb than the happy path covers →
  [Advanced Usage](./advanced-usage.md).
- Something went wrong → [Troubleshooting](./troubleshooting.md).
