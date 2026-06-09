# After `novetest test` — interpret + follow up

After `novetest test` returns, you have a JSON envelope in front
of you. This page covers:

1. The exit-code → meaning table.
2. How to read `stage_eligibility`.
3. How to read `recommendations`.
4. The two follow-up verbs you may want on the happy path:
   `novetest status` and `novetest inspect <run_id>`.
5. The shape of `envelope.warnings[]`.

Everything beyond this — `compare`, `coverage diff`, `regression
compare`, `localization --formula`, `replay --reruns`,
`memory delete` — is one-line memos in
[advanced-cli-memo.md](./advanced-cli-memo.md).

---

## Exit codes

`novetest` uses **6 well-defined exit codes**. Always check the
exit code in your wrapper, then parse the envelope.

| Code | Constant | Meaning | What to do |
|---|---|---|---|
| `0` | `EXIT_OK` | Transport succeeded; user tests passed. | Read recommendations; if `all_green`, you are done. |
| `1` | `EXIT_GENERIC` | Unexpected error (CLI crash, unhandled exception). | Treat as a bug. Report with the envelope payload if any. |
| `2` | `EXIT_USAGE` | Bad input (invalid flags, missing required arg, missing Project Store, bad `--formula` value). | Fix the invocation. Envelope's `errors[].message` is the human-readable hint. |
| `3` | `EXIT_USER_TESTS_FAILED` | Transport succeeded; **user tests failed**. | Read recommendations. The product is reporting a real test failure, not a tooling error. |
| `4` | `EXIT_ENGINE_MISSING` | Native test engine not ready (missing on PATH, misconfigured, missing dep). | Install the missing tool. Envelope's `data.engine_readiness.issues[]` is the actionable list. |
| `5` | `EXIT_STORAGE` | Project Store corrupt or unreadable. | Inspect `.novetest/store.json`. If lost, `rm -rf .novetest && novetest init` recreates it (you lose history). |

### Common `errors[].code` values

When `ok: false`, the `errors[]` array carries a stable
machine-friendly `code` per error. Route on `errors[0].code`
first, then surface `errors[0].message` to humans. The codes
you will see most often in practice:

| `errors[].code` | Typical exit | When you see it |
|---|---|---|
| `uninitialized` | 2 | A non-`init` verb was run from a directory whose tree contains no `.novetest/` (walk-up from CWD found nothing). Fix: `cd` into the project (or any subdirectory of it), or run `novetest init` if you have not yet. See [quick-start.md §"Where do I run this from?"](./quick-start.md#step-2--novetest-test). |
| `store-corrupt` | 5 | `.novetest/` exists but `store.json` is unreadable. Fix: inspect the file; in the worst case `rm -rf .novetest && novetest init` recreates from scratch (you lose run history). |
| `not-found` | 2 | A `run_id` you passed (e.g. to `inspect`, `coverage show`, `replay`) does not match any Memory Entry. Fix: list available IDs with `novetest memory list`. |
| `engine-missing` / `engine-misconfigured` / `engine-not-ready` | 4 | Native test runner not installed, not on PATH, or missing a required plugin. Fix: `data.engine_readiness.issues[]` carries the actionable hint list. |
| `invalid-flag` | 2 | A flag value is outside the allowed set (e.g. `--formula somethingelse`). Fix: read `errors[0].message` for the allowed values. |
| `adapter-<kind>` | 4 (usually) | A native adapter invocation failed (e.g. `adapter-pytest`, `adapter-cargo`). `details.install_hint` often carries a one-line fix. |
| `not-implemented` | 2 | A verb stub reserved for a future phase. Should not occur on the happy path at MVP. |
| `cli-error` | 1 | Unexpected internal exception. Report with the envelope payload if you can. |

Crucial nuance:

- **`ok: true` does NOT imply exit 0.** Exit 3 (tests failed) is
  perfectly normal — `ok: true` because the CLI did its job; the
  product information is "your tests failed". Always read both.
- **`ok: false` always implies exit ≠ 0.** When the CLI itself
  could not do its job, `ok: false` and a non-zero exit are
  paired.

---

## `data.stage_eligibility`

The `novetest test` envelope reports per-stage availability:

```json
{
  "stage_eligibility": {
    "coverage": "available",
    "regression": "unavailable",
    "localization": "available",
    "replay": "not_run"
  }
}
```

Values:

| Value | Meaning |
|---|---|
| `"available"` | The stage derived facts and persisted them. You can query them via the per-stage verbs (`coverage show`, `regression latest`, `localization`) or via `novetest inspect <run_id>`. |
| `"unavailable"` | The stage could not derive facts for a **structural** reason (e.g. no baseline yet for regression, no failing tests for SBFL). This is **not an error** — it is a true statement about the data. |
| `"not_run"` | The orchestration deliberately did not invoke this stage. At MVP only `replay` is `"not_run"` by default (it would multiply wall time by `--reruns`). |

Per-stage "unavailable" reasons you will see in the happy path:

- `regression: "unavailable"` on the **first** run for a target —
  there is no prior baseline. The second `novetest test` on the
  same target will report `regression: "available"`.
- `localization: "unavailable"` (or available but degenerate)
  when there are zero failing tests — there is nothing to
  localize.

In both cases the recommendation set just won't include
regression-aware or localization-aware items. That is correct
behavior.

---

## `data.recommendations[]`

This is the action-oriented synthesis. Each recommendation has a
fixed structure:

```json
{
  "recommendation_id": "rec_001",
  "category": "all_green",
  "priority": 7,
  "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3).",
  "slots": {
    "passed": 3,
    "skipped": 0,
    "total_tests": 3,
    "run_reference": { "run_id": "...", "created_at": 1717951353000 }
  },
  "evidence_citations": [
    {
      "kind": "run_reference",
      "run_reference": { "run_id": "...", "created_at": 1717951353000 },
      "selector": {}
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `recommendation_id` | Stable per-envelope identifier (`rec_001`, `rec_002`, …). Not persisted across runs. |
| `category` | Canonical machine slug — pin against this for routing. Examples: `all_green`, `tests_failed`, `coverage_regressed`, `new_test_failure`, `flaky_suspect`, `unable_to_derive_baseline`, etc. The full catalog lives in `design/implementation-plan/recommendation-synthesis.md`. |
| `priority` | Integer; higher = more urgent. Used to order multi-recommendation responses. |
| `summary` | Human + AI-readable English sentence summarizing the recommendation. Always present, always non-empty. |
| `slots` | Map of named, structured values referenced in the summary. Lets you produce alternative renderings (e.g., localized strings, structured logs) without re-parsing English. |
| `evidence_citations[]` | List of pointers back into the persisted artifacts. Each citation has `kind` (`run_reference` / `test_result` / `coverage_file` / `localization_finding` / …), the referenced object, and a `selector` (e.g. `{"test_id": "tests/test_x.py::test_y", "outcome": "failed"}`). |

### How to handle a recommendation set in code

```python
recs = envelope["data"]["recommendations"]
recs_sorted = sorted(recs, key=lambda r: -r["priority"])
top = recs_sorted[0] if recs_sorted else None

if top is None:
    # No recommendations — the orchestrator had nothing to say.
    return

if top["category"] == "all_green":
    return  # nothing to do
elif top["category"] in {"tests_failed", "new_test_failure"}:
    # Walk evidence_citations[] to find the failing tests.
    for cite in top["evidence_citations"]:
        if cite["kind"] == "test_result":
            test_id = cite["selector"]["test_id"]
            outcome = cite["selector"]["outcome"]
            # Fetch the run via inspect to get error details.
elif top["category"] == "coverage_regressed":
    # Walk evidence_citations[] for the coverage file deltas.
    ...
```

The key insight: **always route on `category` first**, then walk
`evidence_citations[]` for the structured pointers. Do not
parse `summary`.

---

## `envelope.warnings[]`

Independent of `errors[]`. Warnings are **advisory** — the
command succeeded, but the user (or the AI agent) might want to
know something. Examples:

- `localization-cache-rederived` — the cache was rewritten
  because the requested `--formula` or `--top-n` differed from
  what was cached.
- `localization-formula-noop-in-mode` — `--formula` was
  specified but the chosen SBFL mode (`failure_proximity`) does
  not consume a formula.
- Adapter warnings — e.g. xunit's `coverlet-floor-degraded`
  when the project pins an older Coverlet that cannot do
  per-test coverage.
- `engine-misconfigured` — readiness probe found the engine but
  flagged missing optional pieces (e.g. coverage tool).

Shape (each entry):

```json
{
  "code": "machine-friendly-slug",
  "message": "Human-readable explanation or hint.",
  "details": { /* optional structured context */ }
}
```

Pin against `code` for routing. `message` is for display.
`details` is open-ended structured context (the schema varies
per `code`).

You can safely ignore warnings for the happy path, but
production AI agents should log them.

---

## `novetest status` — what's cached?

```bash
novetest status
```

Returns the latest run reference plus the availability of each
sub-report kind across the whole store. Use this when you want
to know "what is currently queryable in this project" without
having to enumerate runs.

Envelope:

```json
{
  "schema": "novetest/v1",
  "command": "status",
  "ok": true,
  "data": {
    "latest_run_reference": {
      "run_id": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
      "created_at": 1717951353000
    },
    "run_history_size": 12,
    "sub_reports": {
      "coverage": "available",
      "regression": "available",
      "localization": "available",
      "replay": "unavailable"
    }
  },
  "errors": [],
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `data.latest_run_reference` | The most recent Run Record. Use the `run_id` as input to `inspect`. Null when no runs exist (very fresh `init`). |
| `data.run_history_size` | Total non-tombstoned runs in the store. |
| `data.sub_reports.*` | Same `"available" / "unavailable"` semantics as `stage_eligibility`, but aggregated across the whole store. |

`status` is read-only, fast, never derives anything. It is the
right verb for AI agents to run as a periodic "what state is
this project in" probe.

---

## `novetest inspect <run_id>`

```bash
novetest inspect 01ARZ3NDEKTSV4RRFFQ69G5FAV
```

Aggregates **all derived facts** for a single run into one
envelope. The shape mirrors `stage_eligibility` but, instead of
"available/unavailable" strings, embeds the actual outcomes:

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
      "run_record": { /* Run Record */ },
      "stored_at": 1717951367000,
      "has_coverage_facts": true,
      "has_regression_facts": false,
      "has_localization_findings": true,
      "has_replay_result": false,
      "tombstoned_at": null
    },
    "sub_reports": {
      "coverage": {
        "status": "available",
        "coverage_outcome": {
          "kind": "fact-set",
          "run_reference": { /* ... */ },
          "mapping_granularity": "per-test",
          "summary": {
            "num_statements": 287,
            "covered_statements": 245,
            "missing_statements": 42,
            "excluded_statements": 0,
            "num_branches": 68,
            "covered_branches": 59,
            "missing_branches": 9,
            "percent_covered": 85.4
          }
        }
      },
      "regression": {
        "status": "unavailable",
        "reason": "no-comparable-baseline"
      },
      "localization": {
        "status": "available",
        "localization_outcome": {
          "kind": "fact-set",
          "run_reference": { /* ... */ },
          "engine_name": "pytest",
          "ecosystem": "python",
          "mode": "sbfl_per_test",
          "confidence": "high",
          "formula": "ochiai",
          "alternate_scores_available": ["tarantula", "dstar2"],
          "top_n": 10,
          "entries": [ /* ranked SBFL findings */ ],
          "derived_at": 1717951375000
        }
      },
      "replay": { "status": "not_run" }
    }
  },
  "errors": [],
  "warnings": []
}
```

### Discriminated unions to internalize

Every per-stage outcome carries a `kind` discriminator:

- `coverage_outcome.kind`: `"fact-set"` | `"unavailable"`
- `regression_outcome.kind`: `"fact-set"` | `"unavailable"`
- `localization_outcome.kind`: `"fact-set"` | `"unavailable"`
- `replay_outcome.kind`: `"replay-result"` | `"unavailable"`

Always switch on `kind` first; never assume a fact-set shape is
present.

### When `inspect` is useful

- Your AI agent wants the raw coverage `summary` block.
- You want to read the SBFL `entries[]` rankings (each with
  `code_location`, `score_raw`, `score_normalized`, and
  `evidence_citations[]`).
- You want to audit a particular recommendation by walking its
  evidence citations back to the cited run's full state.
- You are debugging why `stage_eligibility` reported
  `"unavailable"` — `inspect`'s per-stage `reason` field is more
  detailed than the summary value.

### When `inspect` is overkill

For a basic green run, the `novetest test` envelope's
recommendations carry everything you need. Reach for `inspect`
only when you specifically need raw derived facts.

---

## A worked example: green → fail → green

1. **First `novetest test` (green)** → exit 0, recommendation
   `all_green`, `regression: "unavailable"` (no baseline).
2. **Edit a test to fail. Re-run `novetest test`** → exit 3,
   recommendation `tests_failed` (high priority), recommendation
   `localization_finding` (the SBFL ranking that suggests
   `my_module/math_utils.py::add` if the failure correlates
   with that function), `regression: "available"` showing the
   transition from passed to failed.
3. **Walk the evidence citations** for the `tests_failed`
   recommendation. The `evidence_citations[]` will include
   `test_result` kind with `selector = {"test_id": "...",
   "outcome": "failed"}`. Use `novetest inspect <run_id>` to
   read the raw run record's per-test stdout/stderr for the
   failure.
4. **Fix the bug, re-run `novetest test`** → exit 0,
   recommendation `recovered_from_failure` (or `all_green`
   again, depending on the recommendation engine's decision —
   the `category` is the source of truth, not the prose).

The AI agent's loop is: parse envelope → route on top-priority
recommendation `category` → act → re-run `novetest test` → loop.

---

## Where to go from here

- If you need a deeper verb (replay flakiness probe, explicit
  baseline comparison, coverage diff): [advanced-cli-memo.md](./advanced-cli-memo.md).
- If the per-language toolchain is not behaving as expected:
  [languages.md](./languages.md) per-engine quirks.
- For the original happy path: [quick-start.md](./quick-start.md).
