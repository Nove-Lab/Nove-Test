# After `novetest test` — interpret + follow up (Agent)

After `novetest test` returns, you have a `novetest/v1` envelope. This
page is the reference for routing on it:

1. Exit-code table (all 6).
2. The full `errors[].code` catalog.
3. Reading `data.stage_eligibility`.
4. Reading `data.recommendations[]` and its closed taxonomy.
5. The `status` and `inspect` follow-up envelopes.
6. The `envelope.warnings[]` shape and codes.

Deeper verbs (`coverage`, `regression`, `localization`, `replay`,
`compare`, `memory`, `licenses`) → [advanced.md](./advanced.md).

---

## Exit codes

| Code | Constant | Pairs with | Meaning |
|---|---|---|---|
| `0` | `EXIT_OK` | `ok: true` | CLI succeeded. For `test`/`run`: user's tests passed. |
| `1` | `EXIT_GENERIC` | `ok: false` | Unexpected CLI exception. Report as bug. |
| `2` | `EXIT_USAGE` | `ok: false` | Bad input (invalid flag, missing Project Store, missing required arg, bad `--formula` value, unknown `run_id`). |
| `3` | `EXIT_USER_TESTS_FAILED` | `ok: true` | CLI succeeded; user's tests failed. This is product data, not a tooling error. |
| `4` | `EXIT_ENGINE_MISSING` | `ok: false` | Native engine not ready (missing on PATH, misconfigured, missing dep). |
| `5` | `EXIT_STORAGE` | `ok: false` | Project Store corrupt or unreadable. |

Routing rules:

```python
if exit_code == 0:
    # ok: true, tests passed (or non-test verb succeeded)
    handle_success(envelope)
elif exit_code == 3:
    # ok: true, tests failed — read recommendations, fix tests, retry
    handle_test_failures(envelope)
elif exit_code == 2:
    # ok: false, fix the invocation
    handle_usage_error(envelope)
elif exit_code == 4:
    # ok: false, install / configure missing engine
    handle_engine_missing(envelope)
elif exit_code == 5:
    # ok: false, Project Store damaged
    handle_storage_error(envelope)
elif exit_code == 1:
    # ok: false, unexpected CLI exception — report as bug
    handle_generic_error(envelope)
```

Crucial invariants:

- **`ok: true` does NOT imply exit 0.** Exit 3 (tests failed) is
  perfectly normal — `ok: true` because the CLI did its job; the
  product information is "your tests failed". Always read both.
- **`ok: false` always implies exit ≠ 0.** When the CLI itself could
  not do its job, `ok: false` and a non-zero exit are paired.
- The exit code AND `errors[0].code` together identify the failure
  class. Route on exit code FIRST, then on `errors[0].code` for
  per-case granularity.

---

## `errors[].code` catalog

When `ok: false`, the `errors[]` array carries at least one error
with this shape:

```json
{
  "code":    "machine-friendly-slug",
  "message": "Human-readable explanation or hint.",
  "details": { /* optional structured context */ }
}
```

Pin against `code` for routing. `message` is for surfacing to humans.
`details` is open-ended structured context whose schema varies per
`code`.

The codes you will encounter:

| `errors[].code` | Typical exit | Triggered when | Recovery |
|---|---|---|---|
| `uninitialized` | 2 | Non-`init` verb run from a directory with no `.novetest/` in any ancestor. | `cd` into a `.novetest/`-containing tree, or run `novetest init`. |
| `store-corrupt` | 5 | `.novetest/store.json` unreadable or malformed. | Inspect / fix the file. Worst case: `rm -rf .novetest && novetest init` (loses history). |
| `not-found` | 2 | A `run_id` you passed (to `inspect`, `coverage show`, `replay`, `memory show`, …) does not match any Memory Entry. | List available IDs with `novetest memory list`. |
| `engine-missing` | 4 | Native engine binary not on PATH. | Install per [languages.md](./languages.md). `details.install_hint` is the one-liner. |
| `engine-misconfigured` | 4 | Engine found but unusable (missing plugin, wrong version). | `details.install_hint`. |
| `engine-not-ready` | 4 | Higher-level readiness probe failed. | `details` carries the specific issue list. |
| `invalid-flag` | 2 | Flag value outside the allowed set (e.g. `--formula somethingelse`). | `errors[0].message` lists allowed values. |
| `adapter-<kind>` | 4 (usually) | Native adapter invocation failed (`adapter-pytest`, `adapter-jest`, `adapter-junit`, `adapter-gotest`, `adapter-cargo`, `adapter-xunit`). | `details.install_hint` often carries a one-line fix. |
| `not-implemented` | 2 | A verb stub reserved for a future phase. | Should not occur on the happy path at MVP. |
| `cli-error` | 1 | Unexpected internal exception. | Report as bug with the envelope payload. |

When you get an `ok: false` envelope, the canonical routing is:

```python
err = envelope["errors"][0]
code = err["code"]
message = err["message"]
hint = err.get("details", {}).get("install_hint")
```

For full per-code recovery patterns, see [troubleshooting.md](./troubleshooting.md).

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

Values (string enum):

| Value | Meaning |
|---|---|
| `"available"` | The stage derived facts and persisted them. Queryable via the per-stage verbs (`coverage show`, `regression latest`, `localization`) or via `novetest inspect <run_id>`. |
| `"unavailable"` | The stage could not derive facts for a **structural** reason (no baseline yet, no failing tests for SBFL, etc.). NOT an error. |
| `"not_run"` | The orchestration deliberately did not invoke this stage. At MVP only `replay` is `"not_run"` by default. |

Common reasons you will see on the happy path:

- `regression: "unavailable"` on the **first** run for a target — no prior baseline. The second `novetest test` on the same target will report `"available"`.
- `localization: "unavailable"` (or available but degenerate `"failure_proximity"` mode) when there are zero failing tests.

Recommendation routing should treat `"unavailable"` stages as
"recommendations from this stage will simply not appear in
`recommendations[]`" — never as an error.

---

## `data.recommendations[]`

Action-oriented synthesis. Each recommendation has a fixed structure:

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

| Field | Type | Routing? |
|---|---|---|
| `recommendation_id` | string | No. Per-envelope identifier (`rec_001`, …), not persisted across runs. |
| `category` | string | **Yes — pin against this.** Closed taxonomy. |
| `priority` | integer | Sort key. Higher = more urgent. |
| `summary` | string | For humans / LLM display. Do NOT parse. |
| `slots` | object | Named structured values referenced in the summary. Use these for alternative renderings or for slot-driven downstream actions. |
| `evidence_citations[]` | list | Pointers back into persisted artifacts. Walk these for drill-down. |

### Routing decision tree

```python
recs = envelope["data"]["recommendations"]
recs_sorted = sorted(recs, key=lambda r: -r["priority"])

if not recs_sorted:
    return  # no recommendations — synthesizer had nothing to say

top = recs_sorted[0]

if top["category"] == "all_green":
    return  # nothing to do
elif top["category"] in {"tests_failed", "new_test_failure"}:
    for cite in top["evidence_citations"]:
        if cite["kind"] == "test_result":
            test_id = cite["selector"]["test_id"]
            outcome = cite["selector"]["outcome"]
            # Drill into the run for stdout / stderr / error message.
elif top["category"] == "coverage_regressed":
    # Walk evidence_citations for coverage-file deltas.
    ...
elif top["category"] == "flaky_suspect":
    # Often paired with a replay recommendation; consider running
    # `novetest replay <run_id> --reruns 5`.
    ...
elif top["category"] == "unavailable_analysis":
    # Informational; explains a structural unavailability. No action.
    ...
```

The key invariant: **route on `category` first**. Walk
`evidence_citations[]` for structured pointers. Do NOT parse
`summary`.

### Closed taxonomy of categories (v1)

At MVP the synthesizer ships these categories (always lowercase, snake_case):

| Category | Glyph in text mode | Semantic |
|---|---|---|
| `all_green` | `✓` | All tests passed; no action recommended. |
| `tests_failed` | `!` | One or more tests failed in this run. |
| `new_test_failure` | `!` | A specific test transitioned passed → failed since the baseline. |
| `coverage_regressed` | `!` | Coverage percentage dropped relative to baseline. |
| `flaky_suspect` | `!` | Failure pattern looks like flake (different result across runs). |
| `recovered_from_failure` | `✓` | Tests are green now and were red in the baseline. |
| `unavailable_analysis` | `✓` (informational) | Explains a structural `"unavailable"` outcome (e.g. no baseline yet). |

The full catalog (with slot schemas) is documented in
`design/implementation-plan/recommendation-synthesis.md`. The list
above is the load-bearing subset for MVP routing.

### Citation kinds

Each `evidence_citations[]` entry has a `kind` discriminator:

| `kind` | Selector keys | Drill-in |
|---|---|---|
| `run_reference` | `{}` (the run_reference itself is the citation) | `novetest inspect <run_id>` |
| `test_result` | `{"test_id": str, "outcome": str}` | `inspect` and locate the test |
| `coverage_fact` | `{"file": str}` | `novetest coverage show <run_id>` |
| `regression_fact` | `{"test_id": str}` | `novetest regression latest` |
| `localization_finding` | `{"file": str, "primary_line": int, "rank": int}` | `novetest localization <run_id>` |
| `replay_result` | `{"classification": str}` | `novetest replay <run_id>` (or re-read from inspect) |

---

## `envelope.warnings[]`

Independent of `errors[]`. Warnings are **advisory** — the command
succeeded; we wanted you to know something.

Shape (each entry):

```json
{
  "code": "machine-friendly-slug",
  "message": "Human-readable explanation or hint.",
  "details": { /* optional structured context */ }
}
```

Pin against `code` for routing. `message` is for display. `details` is
open-ended structured context whose schema varies per `code`.

Common codes:

| `warnings[].code` | Meaning |
|---|---|
| `localization-cache-rederived` | The cache was rewritten because the requested `--formula` or `--top-n` differed from what was cached. |
| `localization-formula-noop-in-mode` | `--formula` was specified but the chosen SBFL mode (`failure_proximity`) does not consume a formula. |
| `engine-misconfigured` | Readiness probe found the engine but flagged missing optional pieces (e.g. coverage tool). |
| `junit-multiple-build-systems` | Both `pom.xml` and `build.gradle` present; the adapter picked Maven. |
| `coverlet-floor-degraded` | The .NET project pins an older Coverlet that cannot do per-test coverage. |

Production agents should log warnings even when they ignore them.

---

## `novetest status` envelope

```bash
NOVETEST_OUTPUT=json novetest status
```

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
| `data.latest_run_reference` | Most recent Run Record. `null` when no runs exist (fresh `init`). |
| `data.run_history_size` | Count of non-tombstoned runs in the store. |
| `data.sub_reports.*` | Same `"available" / "unavailable"` semantics as `stage_eligibility`, but aggregated across the whole store, not just the latest run. |

`status` is read-only, fast, never derives anything. Right verb for
periodic "what state is this project in" probes.

When `data.latest_run_reference == null`:

```json
{
  "schema": "novetest/v1",
  "command": "status",
  "ok": true,
  "data": {
    "latest_run_reference": null,
    "run_history_size": 0,
    "sub_reports": {}
  },
  "errors": [],
  "warnings": []
}
```

---

## `novetest inspect <run_id>` envelope

```bash
NOVETEST_OUTPUT=json novetest inspect 01ARZ3NDEKTSV4RRFFQ69G5FAV
```

Aggregates all derived facts for one run. Discriminated unions
throughout:

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
    },
    "regression_outcome": {
      "kind": "unavailable",
      "reason": "no-comparable-baseline"
    },
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
    },
    "replay_outcome": {
      "kind": "unavailable",
      "reason": "not-run"
    }
  },
  "errors": [],
  "warnings": []
}
```

### Discriminated unions (switch on `kind`)

| Field | `kind` ∈ |
|---|---|
| `coverage_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `regression_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `localization_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `replay_outcome` | `"replay-result"` ∣ `"unavailable"` |

When `kind == "unavailable"`, always present:
- `reason`: string (e.g. `"no-comparable-baseline"`, `"no_failed_tests"`, `"not-run"`, `"missing-derived-facts"`, …)

Always switch on `kind` first; never assume a fact-set shape is
present.

### When to call `inspect`

- You need the raw coverage `summary` block.
- You want to walk the SBFL `entries[]` rankings.
- You want to audit a recommendation by following its
  `evidence_citations` back to the cited run's full state.
- You're debugging why `stage_eligibility` reported `"unavailable"` —
  the per-stage `reason` field is more detailed than the summary
  value.

### When NOT to call `inspect`

- For green runs the `novetest test` recommendations already carry
  what you need. `inspect` is for drill-down.

---

## A worked example: green → fail → green (envelope flow)

### Run 1 — green

```bash
novetest test
```

`recommendations[0].category == "all_green"`. Exit 0. Done.

### Run 2 — break a test, re-run

After editing `tests/test_math_utils.py::test_add_positive` to fail:

```bash
novetest test
```

Envelope (illustrative):

```json
{
  "schema": "novetest/v1",
  "command": "test",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX1L...", "created_at": ... },
    "stage_eligibility": {
      "coverage": "available",
      "regression": "available",
      "localization": "available",
      "replay": "not_run"
    },
    "recommendations": [
      {
        "category": "tests_failed",
        "priority": 9,
        "summary": "1 test failed in tests/test_math_utils.py.",
        "slots": { "failed_count": 1, "run_reference": { ... } },
        "evidence_citations": [
          {
            "kind": "test_result",
            "selector": {
              "test_id": "tests/test_math_utils.py::test_add_positive",
              "outcome": "failed"
            }
          }
        ]
      },
      {
        "category": "new_test_failure",
        "priority": 8,
        "summary": "test_add_positive went green → failed since the previous run.",
        "evidence_citations": [
          {
            "kind": "regression_fact",
            "selector": {
              "test_id": "tests/test_math_utils.py::test_add_positive"
            }
          }
        ]
      }
    ]
  },
  "errors": [],
  "warnings": []
}
```

Exit code: **3** (tests failed); `ok: true` (CLI did its job).

Agent action:

```python
top = sorted(recs, key=lambda r: -r["priority"])[0]
# top["category"] == "tests_failed"
# top["evidence_citations"][0]["selector"]["test_id"] = "tests/test_math_utils.py::test_add_positive"
# → fetch raw stdout/stderr via `novetest inspect <run_id>` or re-run `novetest run`
```

### Run 3 — fix and re-run

After reverting the edit:

```bash
novetest test
```

Either `category == "all_green"` (typical) or
`category == "recovered_from_failure"` (synthesizer-dependent). Exit
code: 0.

---

## What to read next

- Deeper verbs → [advanced.md](./advanced.md).
- Per-engine quirks → [languages.md](./languages.md).
- Error envelope by code → [troubleshooting.md](./troubleshooting.md).
