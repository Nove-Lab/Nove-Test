# Quick Start — the canonical happy path

This is the 4-step canonical workflow for an AI agent driving
`novetest`. We walk through every step with the exact command
and the literal envelope shape it returns. We use the working
example introduced in [README.md](./README.md#the-working-example-used-throughout-this-document)
(a tiny Python + pytest project with 3 green tests).

The four steps:

1. `novetest init` — create the per-project Project Store.
2. `novetest test` — run tests, derive coverage / regression /
   localization, synthesize a recommendation.
3. Read the envelope — `stage_eligibility` + `recommendations`.
4. (Optional) `novetest inspect <run_id>` if you want to drill
   into a single run.

For everything beyond step 2 (status, inspect, replay, etc.), see
[after-test.md](./after-test.md). For language-specific
toolchain notes, see [languages.md](./languages.md).

---

## Step 1 — `novetest init`

Run from the project root (the directory that contains
`pyproject.toml` in our example):

```bash
cd my-project
novetest init
```

`init` does two things:

1. **Creates a Project Store** under `.novetest/` in the current
   workspace. The store is a directory tree of JSON files (no
   sidecar database at MVP); every Run Record, Coverage Facts
   set, Regression Facts set, Localization Findings set, and
   Replay Result lives under here. The store is per-project;
   you commit `.novetest/` to git only if you want to share
   run history between collaborators (most users do not).
2. **Probes engine readiness** — auto-detects which native test
   engine matches your workspace and reports whether it is ready
   to invoke. Engine probing **never fails the init**; the store
   is still created even if the engine is not yet installed.

### Envelope

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

Key fields:

| Field | Meaning |
|---|---|
| `data.store_path` | Absolute path of the new `.novetest/` directory. |
| `data.store_state` | `"ready"` on success. Other values exist for diagnostic states but are not encountered on the happy path. |
| `data.initialized_at` | Unix-milliseconds at init time. |
| `data.engine_readiness.state` | `"ready"` — your engine is fully installed. Other states: `"engine-missing"` (no native runner found), `"engine-misconfigured"` (runner found but unusable). See `data.engine_readiness.issues[]` for human-readable diagnostics. |
| `data.engine_readiness.engine` | The chosen native runner, e.g. `"pytest"`, `"jest"`, `"gotest"`, `"cargo-nextest"`, `"junit"`, `"xunit"`. |
| `data.engine_readiness.ecosystem` | Higher-level language family: `"python"`, `"javascript-typescript"`, `"go"`, `"rust"`, `"java"`, `"dotnet"`. |
| `data.engine_readiness.evidence[]` | Workspace markers the probe used to identify the engine (e.g. `pyproject.toml detected`). |
| `data.engine_readiness.issues[]` | Empty on the happy path; carries actionable hints (e.g. `"jest is declared in package.json but not installed; run 'npm install --save-dev jest'"`) when state is not `"ready"`. |

Exit code: **0** for the happy path. **2** if you ran `init`
inside a directory that already has a corrupt store (very rare);
fix or remove `.novetest/` and re-run.

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

`init` is fully idempotent: re-running it on an already-
initialized project does nothing destructive.

---

## Step 2 — `novetest test`

This is the single command that does everything.

```bash
novetest test
```

Or, equivalently:

```bash
novetest test tests/
```

Or, using the bare default-verb alias (when the first argument
is not a reserved verb name, `novetest <target>` is sugar for
`novetest test <target>`):

```bash
novetest tests/
```

All three are the same command in the happy case. We recommend
the explicit `novetest test` form in scripts and AI-agent
contexts, because it never collides with a reserved verb.

### What `novetest test` does internally

1. **Run** — invokes the native engine (`pytest` in our example),
   captures structured per-test results, persists a Run Record
   under `.novetest/memory/runs/...`.
2. **Coverage** — drives the engine in coverage mode, parses
   the engine-specific coverage report, persists Coverage Facts
   under `.novetest/coverage/facts/...`.
3. **Regression** — resolves the latest comparable baseline (the
   immediately preceding successful run on the same target), if
   any, and persists Regression Facts under
   `.novetest/regression/pairs/...`. On the very first run there
   is no baseline, so this stage reports `"unavailable"` — that is
   expected, not an error.
4. **Localization** — derives SBFL fault-localization findings
   (Ochiai formula by default) and persists them under
   `.novetest/localization/findings/...`. On an all-green run
   there is nothing to localize, so findings may be empty or
   degraded to `"failure_proximity"` mode — also expected.
5. **Synthesize recommendations** — picks deterministic
   recommendations from the facts derived above and surfaces them
   in `data.recommendations[]`. Recommendations are kept
   **in-memory** during the call and **not persisted**; re-running
   `novetest test` always re-synthesizes from the latest derived
   facts.

The five stages run in order. If a stage fails its readiness
check (e.g. coverage tool not installed), `novetest test` does
not abort — it records the stage as `"unavailable"` and proceeds
to the next stage. The only hard failures are: engine missing
(exit 4), bad usage (exit 2), or a corrupt Project Store (exit 5).

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

Exit code: **0** because the tests passed. If the user's tests
had failed (a normal, non-error outcome), `ok` would still be
`true` but the exit code would be **3** (`EXIT_USER_TESTS_FAILED`).
See [after-test.md §"Exit codes"](./after-test.md#exit-codes).

### What just happened, in plain language

- Three tests passed. The Run Record's ULID (`01ARZ3NDEKTSV4RRFFQ69G5FAV`)
  is the durable identifier you use for any follow-up query.
- Coverage facts were derived (`stage_eligibility.coverage = "available"`)
  because `pytest-cov` was present.
- Regression is `"unavailable"` because there is no prior run on
  this target — first-run baseline gap. The next time you run
  `novetest test`, regression will resolve.
- Localization is `"available"` in degenerate mode (no failures to
  localize), so the findings set is structurally present but
  effectively empty.
- Replay is `"not_run"` — the integrated workflow never auto-runs
  replay (it would multiply wall time by `--reruns`). To probe
  flakiness, invoke `novetest replay <run_id>` directly (see
  `advanced-cli-memo.md`).
- One recommendation was synthesized: `all_green`. Its `summary`
  is meant to be readable both by a human and by an AI agent.

---

## Step 3 — read the envelope, decide next action

This is the entire point of the JSON envelope: an AI agent can
parse it deterministically and decide what (if anything) to do
next. The decision tree is small.

### Decision: did the run succeed at the transport level?

```python
ok = envelope["ok"]
```

`ok: true` means the CLI itself ran cleanly. `ok: false` only
fires on structural failures (engine missing, store corrupt,
parse error, bad usage). Test failures are NOT `ok: false` —
they are real product data and are surfaced via exit code 3
and via the recommendation set.

### Decision: did the user's tests pass?

```python
import sys
exit_code = ...  # whatever your subprocess wrapper returns
if exit_code == 0:
    # Tests passed.
elif exit_code == 3:
    # Tests failed normally — read recommendations, fix tests.
elif exit_code in (2, 4, 5):
    # Real error (usage / engine-missing / store-corrupt).
```

See [after-test.md "Exit codes"](./after-test.md#exit-codes)
for the full table.

### Decision: which derived stages are usable?

```python
stages = envelope["data"]["stage_eligibility"]
# stages["coverage"], stages["regression"], stages["localization"], stages["replay"]
# each is one of: "available", "unavailable", "not_run"
```

`"available"` means the facts are persisted and queryable via the
per-stage verbs (`coverage show`, `regression latest`,
`localization`). `"unavailable"` means a structural reason
prevented derivation (no baseline yet, no failing tests for SBFL,
etc.) — not an error. `"not_run"` only applies to `replay` and
means the integrated workflow never invokes it.

### Decision: what to act on

```python
for rec in envelope["data"]["recommendations"]:
    # Read rec["category"], rec["priority"] (higher = more urgent),
    # rec["summary"] (human/agent-readable text),
    # rec["slots"] (machine-friendly named values),
    # rec["evidence_citations"] (pointers back to runs / files / tests).
```

The recommendation catalog at MVP includes categories like
`all_green`, `tests_failed`, `coverage_regressed`,
`new_test_failure`, `flaky_suspect`, etc. The full catalog is
documented in `design/implementation-plan/recommendation-synthesis.md`;
you do not need to memorize it. Each recommendation is
**self-describing** via its `category`, `summary`, and `slots`.

For the all-green happy case, the recommendation tells you
exactly what you would expect: nothing to do. In failure cases,
the recommendation's `evidence_citations` point you to the runs,
test IDs, or coverage files that justify the recommendation.

---

## Step 4 — (optional) drill into the run with `inspect`

If you want to see everything for a single run in one envelope:

```bash
novetest inspect 01ARZ3NDEKTSV4RRFFQ69G5FAV
```

This aggregates the Run Record, Coverage Facts, Regression Facts,
Localization Findings, and Replay Results (each as an "outcome"
discriminated union of `"fact-set"` vs `"unavailable"`).
The full envelope shape and field-by-field interpretation are in
[after-test.md](./after-test.md#novetest-inspect-run_id).

You do not need `inspect` in the simple happy case — the
recommendations from `novetest test` are usually enough. Reach
for `inspect` when you want a raw audit trail or are debugging a
recommendation.

---

## Two patterns to internalize

1. **One canonical command.** `novetest test` is the single
   call. Do not stitch together `run` + `coverage show` +
   `regression compare` + `localization` by hand for the happy
   path; `test` does it in the right order with the right
   defaults.
2. **Envelope is the contract.** Do not parse stdout, do not
   grep human-readable output. Always set `--output json`
   (or `NOVETEST_OUTPUT=json` once at session start) and parse
   the structured envelope. Every shape on this page is what
   the CLI guarantees.

---

## What to read next

- If your project is not Python: [languages.md](./languages.md)
  for engine-specific prerequisites and quirks.
- If you want to interpret a `tests_failed` recommendation, dig
  into a specific run, or audit cache state:
  [after-test.md](./after-test.md).
- If you suspect you need a deeper verb than the happy path
  covers: [advanced-cli-memo.md](./advanced-cli-memo.md).
