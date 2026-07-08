# After `novetest test` — interpret + follow up (Agent)

After `novetest test` returns, you have a `novetest/v1` envelope. This
page is the reference for routing on it:

1. The envelope frame and exit-code table (all 6).
2. The `errors[].code` catalog.
3. Reading `data.stage_eligibility`.
4. Reading `data.recommendations[]` and its closed 7-category taxonomy.
5. The `status` and `inspect` follow-up envelopes.
6. The sub-report verbs (`coverage`, `regression`, `localization`,
   `replay`, `compare`, `memory`).
7. `warnings[]`.

Pin `NOVETEST_OUTPUT=json` (or pipe to a non-TTY) so you always get
JSON. All envelopes below are real captures from the `calc` example.

---

## Envelope frame

Every command emits the same top-level shape, keys emitted **sorted
alphabetically**:

```json
{
  "command": "test",
  "data": { },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

There are exactly six top-level keys: `schema` (always `"novetest/v1"`),
`command`, `ok`, `data`, `errors`, `warnings`. There is **no** top-level
`version`, `verb`, or `exit_code` field. `errors`/`warnings` are arrays
of `{code, message, details}` objects.

---

## Exit codes

| Code | Constant | Pairs with | Meaning |
|---|---|---|---|
| `0` | `EXIT_OK` | `ok: true` | CLI succeeded. For `test`/`run`: tests passed. Data-level `unavailable` outcomes also land here. |
| `1` | `EXIT_GENERIC` | `ok: false` | Unexpected CLI exception. Report as bug. |
| `2` | `EXIT_USAGE` | `ok: false` | Bad input (missing Project Store, unknown `run_id`, invalid flag, `reset` without `--confirm`). |
| `3` | `EXIT_USER_TESTS_FAILED` | `ok: true` | CLI succeeded; tests failed or errored. Product data, not a tooling error. |
| `4` | `EXIT_ENGINE_MISSING` | `ok: false` | Native engine not ready (missing on PATH) or adapter invocation error. |
| `5` | `EXIT_STORAGE` | `ok: false` | Project Store corrupt or unreadable. |

Routing skeleton:

```python
if exit_code == 0:
    handle_success(envelope)            # ok: true
elif exit_code == 3:
    handle_test_failures(envelope)      # ok: true — read recommendations
elif exit_code == 2:
    handle_usage_error(envelope)        # ok: false — fix the invocation
elif exit_code == 4:
    handle_engine_missing(envelope)     # ok: false — install/configure engine
elif exit_code == 5:
    handle_storage_error(envelope)      # ok: false — Project Store damaged
elif exit_code == 1:
    handle_generic_error(envelope)      # ok: false — report as bug
```

Crucial invariants:

- **`ok: true` does NOT imply exit 0.** Exit 3 (tests failed *or*
  errored) is normal: `ok: true` because the CLI did its job; the data
  says "your tests failed" (or the suite errored before producing
  results — `data.memory_entry.run_record.status == "errored"`, on
  `run`). Always read both.
- **`ok: false` always implies exit ≠ 0.**
- **`unavailable` outcomes are exit 0 / `ok: true`.** A coverage,
  regression, or localization stage that can't produce facts returns its
  unavailability as *data* inside the outcome block. Only transport
  failures (`uninitialized`, `not-found`, `invalid-flag`, `store-corrupt`)
  are non-zero.

---

## `errors[].code` catalog

When `ok: false`, `errors[]` carries at least one `{code, message,
details}` object. Pin against `code`.

| `errors[].code` | Exit | Triggered when | Recovery |
|---|---|---|---|
| `uninitialized` | 2 | A non-`init` verb run from a tree with no `.novetest/` in any ancestor. | Run `novetest init`, or `cd` into a store tree. |
| `not-found` | 2 | A `run_id` (to `inspect`, `coverage show`, `localization`, `replay`, `memory show`, `compare`, …) matches no Memory Entry. Message: `No Memory Entry for run_id='<id>'`. | List ids with `novetest memory list`. |
| `invalid-flag` | 2 | Flag value outside the allowed set (bad `--formula`, `--top-n < 1`). `message` lists the allowed values. | Re-issue with a valid flag. |
| `confirm-required` | 2 | `novetest reset` without `--confirm`. | Pass `--confirm`. |
| `engine-missing` | 4 | Readiness state is `engine-missing` (no native engine detected). `data.engine_readiness` is present. | Install/configure the engine. |
| `adapter-<kind>` | 4 | A native adapter invocation failed (e.g. `adapter-jest`). `details.install_hint` may carry a fix. | Apply the hint. |
| `store-corrupt` | 5 | `.novetest/store.json` unreadable / malformed. | Fix the file; worst case `rm -rf .novetest && novetest init` (loses history). |

The error `code` is the readiness state **verbatim** — `engine-missing`
or `engine-misconfigured` (the code IS the state; there is no extra
`engine-` prefix and **no** `engine-not-ready` code).

```python
err  = envelope["errors"][0]
code = err["code"]
hint = err.get("details", {}).get("install_hint")
```

---

## `data.stage_eligibility`

The `test` envelope's `data` has exactly four keys: `run_reference`,
`stage_eligibility`, `recommendation_schema_version` (currently `1`),
and `recommendations`. The stage-eligibility block:

```json
"stage_eligibility": {
  "coverage": "available",
  "localization": "sbfl_per_test",
  "regression": "available",
  "replay": "not_run"
}
```

(Real `calc` failing-run capture.) Per-slot vocabulary differs:

| Slot | Values | Notes |
|---|---|---|
| `coverage` | `available` ∣ `unavailable` ∣ `not_applicable` | `test` always collects coverage, so usually `available`. |
| `regression` | `available` ∣ `unavailable` ∣ `not_applicable` | `unavailable` on the first run for a target (no baseline). |
| `localization` | **the SBFL mode string** (`sbfl_per_test` ∣ `sbfl_aggregate` ∣ `failure_proximity`) when a finding exists; else `unavailable` / `not_applicable` | NOT the word "available". For a passing run it is `unavailable` (no failing tests). |
| `replay` | always `not_run` | `test` never invokes replay. |

`stage_eligibility` is informational, not an error signal. A stage that
is `unavailable` simply contributes no recommendations.

---

## `data.recommendations[]`

Each recommendation has exactly these keys: `recommendation_id`,
`category`, `priority`, `summary`, `slots`, `evidence_citations`.

```json
{
  "category": "all_green",
  "evidence_citations": [
    {
      "kind": "run_reference",
      "run_reference": { "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S", "created_at": 1782370093639, "schema_version": 1 },
      "selector": {}
    }
  ],
  "priority": 7,
  "recommendation_id": "rec_01KVYRJJJ75ZRHC05GNKYRK99S_908389d6",
  "slots": { "passed": 3, "run_reference": "01KVYRJJJ75ZRHC05GNKYRK99S", "skipped": 0, "total_tests": 3 },
  "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3)."
}
```

| Field | Type | Routing? |
|---|---|---|
| `recommendation_id` | string | No. `rec_<run_id>_<hash>`; not persisted across runs (recommendations are synthesized in-memory, never stored). |
| `category` | string | **Yes — pin against this.** Closed 7-value taxonomy. |
| `priority` | int (1–7) | Sort key. **Lower = higher priority.** No `severity` field exists. |
| `summary` | string | For display. Do NOT parse. |
| `slots` | object | Category-specific structured payload (the matcher data). |
| `evidence_citations` | list (≥1) | Pointers back into persisted artifacts. Walk these to drill down. |

### Closed taxonomy (7 categories)

| `priority` | `category` | Fires when |
|---|---|---|
| 1 | `regression_with_localization` | A newly-failing test ∩ a localization entry. |
| 2 | `investigate_location` | A localization finding, confidence ∈ {high, medium}, rank ≤ 3. |
| 3 | `investigate_regression` | A `regressed` (newly-failing) transition vs baseline. |
| 4 | `coverage_gap` | Uncovered lines overlap a localization entry's span. |
| 5 | `flaky_suspected` | Replay classified `inconsistent`. Reachable via `novetest test --reruns N` (N ≥ 1, default 0 = never replays): one whole-run replay when the run has failures; `stage_eligibility.replay` flips `not_run` → `available`/`unavailable`. When divergence spreads across several tests, v1 emits ONE hit whose `test_id` is empty — do not assume per-test attribution. |
| 6 | `unavailable_analysis` | Tests failed AND some stage was `unavailable`. |

(Category strings are the authoritative code constants — `design/implementation-plan/recommendation-synthesis.md` §8. Never route on paraphrases.)
| 7 | `all_green` | Zero failures AND zero regressed. Mutually exclusive with all others. |

Behavioural notes:

- `regression_with_localization` and `investigate_regression` require a
  **newly-failing** transition. Re-running an already-failing suite does
  not re-emit them.
- `flaky_suspected` never appears in real `test` output.
- `all_green` never coexists with another category.

### Routing decision tree

```python
recs = envelope["data"]["recommendations"]
recs_sorted = sorted(recs, key=lambda r: r["priority"])   # lower = higher priority
if not recs_sorted:
    return
top = recs_sorted[0]
cat = top["category"]

if cat == "all_green":
    return                                  # nothing to do
elif cat in {"investigate_location", "regression_with_localization", "coverage_gap"}:
    # location-bearing slots: file, primary_line, line_range, rank, symbol, formula, mode.
    # The array is NOT score-ordered (recs_sorted[0] may be a rank-2 finding);
    # pick the strongest by rank (asc) then score_normalized (desc):
    best = min((r for r in recs if r["category"] == cat),
               key=lambda r: (r["slots"]["rank"], -r["slots"]["score_normalized"]))
    target = (best["slots"]["file"], best["slots"]["primary_line"])
    # walk best["evidence_citations"] for kind == "localization_finding" / "test_result"
elif cat == "investigate_regression":
    test_id = top["slots"]["test_id"]       # newly-failing test
elif cat == "unavailable_analysis":
    stages  = top["slots"]["unavailable_stages"]
    reasons = top["slots"]["reason_per_stage"]   # informational, no action
```

The key invariant: **route on `category` first, sort by `priority`
ascending**; within a location-bearing category, rank findings by
`slots.rank` (then `score_normalized`) rather than array position. Then
read `slots` / walk `evidence_citations[]`. Do NOT parse `summary`.

### `evidence_citations[]`

Each citation has a `kind` discriminator. The closed `kind` set is
`localization_finding`, `coverage_fact`, `regression_fact`,
`replay_result`, `test_result`, `run_reference`. Real selectors from the
`calc` failing run:

| `kind` | Selector | Drill-in |
|---|---|---|
| `run_reference` | `{}` | `novetest inspect <run_id>` |
| `test_result` | `{"test_id": "...::test_subtract"}` (+ `outcome`) | `novetest inspect <run_id>` |
| `localization_finding` | `{"file": "...", "primary_line": 6, "rank": 1}` | `novetest localization <run_id>` |
| `coverage_fact` | `{"file": "...", "lines": [...]}` | `novetest coverage show <run_id>` |

### Real failing-run envelope (`calc`, the bug)

```json
{
  "command": "test",
  "data": {
    "recommendation_schema_version": 1,
    "recommendations": [
      {
        "category": "investigate_location",
        "priority": 2,
        "recommendation_id": "rec_01KVYRRSF48RMYV84MTB4XQ6P9_9a8e9aae",
        "slots": {
          "file": "calc/arithmetic.py",
          "formula": "ochiai",
          "line_range": [1, 2],
          "mode": "sbfl_per_test",
          "primary_line": 2,
          "rank": 2,
          "score_normalized": 0.0,
          "symbol": "add"
        },
        "summary": "Investigate `add`@2 in `calc/arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).",
        "evidence_citations": [ "…localization_finding, elided…" ]
      },
      {
        "category": "investigate_location",
        "priority": 2,
        "recommendation_id": "rec_01KVYRRSF48RMYV84MTB4XQ6P9_eeff3348",
        "slots": {
          "file": "calc/arithmetic.py",
          "formula": "ochiai",
          "line_range": [5, 6],
          "mode": "sbfl_per_test",
          "primary_line": 6,
          "rank": 1,
          "score_normalized": 1.0,
          "symbol": "subtract"
        },
        "summary": "Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).",
        "evidence_citations": [ "…localization_finding + test_result, elided…" ]
      }
      // …3 more investigate_location recommendations…
    ],
    "run_reference": { "created_at": 1782370297316, "run_id": "01KVYRRSF48RMYV84MTB4XQ6P9", "schema_version": 1 },
    "stage_eligibility": { "coverage": "available", "localization": "sbfl_per_test", "regression": "available", "replay": "not_run" }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit code: **3** (`ok: true`). Five `investigate_location` (priority 2)
recommendations. The array is **not** score-ordered — `recommendations[0]`
is `add`@2 (rank 2, `score_normalized: 0.0`); the culprit `subtract`@6
(rank 1, `score_normalized: 1.0`) is selected by `slots.rank` /
`score_normalized`, per the routing tree above.

---

## `novetest status` envelope

```bash
NOVETEST_OUTPUT=json novetest status
```

```json
{
  "command": "status",
  "data": {
    "latest_run_reference": { "created_at": 1782434851572, "run_id": "01KW0PATQMBP2GXMFRX3J5EEX3", "schema_version": 1 },
    "run_history_size": 2,
    "sub_reports": { "coverage": "available", "localization": "unavailable", "regression": "available", "replay": "unavailable" }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `data.latest_run_reference` | Most recent Run Record (`null` after a fresh `init`). |
| `data.run_history_size` | Count of runs in the store. |
| `data.sub_reports.*` | `available` / `unavailable` per stage, probed against the **latest** run (cache-only read — not a store-wide aggregate). |

`status` is read-only and never derives anything — the right verb for a
periodic "what state is this project in" probe.

---

## `novetest inspect <run_id>` envelope

```bash
NOVETEST_OUTPUT=json novetest inspect 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

A pure read that aggregates every derived fact for one run.
`data` keys: `run_reference`, `run_summary`, `sub_reports`,
`coverage_outcome`, `regression_outcome`, `localization_outcome`,
`replay_outcome`. Each `*_outcome` is **discriminated on `kind`** —
always switch on `kind` first.

```json
{
  "command": "inspect",
  "data": {
    "coverage_outcome": { "kind": "fact-set", "mapping_granularity": "per-test",
      "summary": { "covered_statements": 13, "num_statements": 13, "percent_covered": 100.0, "covered_branches": 0, "num_branches": 0, "missing_statements": 0, "missing_branches": 0, "excluded_statements": 0 },
      "run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "created_at": 1782370296489, "schema_version": 1 } },
    "regression_outcome": { "kind": "fact-set", "summary": { "regressed": 1, "fixed": 0, "still_failing": 0, "still_passing": 2, "total_baseline_tests": 3, "total_target_tests": 3 }, "…": "…" },
    "localization_outcome": { "kind": "fact-set", "mode": "sbfl_per_test", "confidence": "high", "formula": "ochiai", "top_n": 10, "entries": [ "…5 ranked entries…" ], "…": "…" },
    "replay_outcome": { "kind": "unavailable", "reason": "missing-derived-facts", "detail": "no replay attempt has been made for this run", "run_reference": { "…": "…" } },
    "run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "created_at": 1782370296489, "schema_version": 1 },
    "run_summary": { "ecosystem": "python", "engine_name": "pytest", "status": "failed", "summary_counts": { "collected": 3, "failed": 1, "passed": 2, "total": 3 }, "target_expression": "", "target_type": "workspace", "tombstoned": false },
    "sub_reports": { "coverage": "available", "localization": "available", "regression": "available", "replay": "unavailable" }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
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

`inspect` is cache-only — it never runs replay, so `replay_outcome.kind`
is `"unavailable"` (`reason: "missing-derived-facts"`) until you have run
`novetest replay <run_id>` for that id. When `kind == "unavailable"` the
block carries `reason` and `detail`. Coverage/regression reason strings
are **hyphenated** (`missing-derived-facts`); localization reasons are
**underscored** (`no_failed_tests`, `missing_derived_facts`).

Call `inspect` to read the raw coverage `summary`, walk SBFL `entries[]`,
or audit a recommendation by following its citations. For a green run the
`test` recommendations already carry what you need.

---

## Sub-report verbs (routing)

The dedicated verbs return one `data.<outcome>` block, each discriminated
on `kind`. Route on `kind`, never assume a fact-set is present.

| Verb | `data` key | `kind` values |
|---|---|---|
| `coverage show <run_id>` | `coverage_outcome` | `fact-set` ∣ `unavailable` |
| `coverage diff <base> <target>` | `coverage_delta` | `delta` ∣ `unavailable` |
| `regression compare <base> <target>` | `regression_outcome` | `fact-set` ∣ `unavailable` |
| `regression latest` | `regression_outcome` | `fact-set` ∣ `unavailable` |
| `compare <base> <target>` | `regression_outcome` **and** `coverage_delta` | as above |
| `localization <run_id>` / `latest` | `localization_outcome` | `fact-set` ∣ `unavailable` |
| `replay <run_id>` | `replay_outcome` (+ `original_run_reference`) | `replay-result` ∣ `unavailable` |
| `memory list` | `count`, `entries[]` | — |
| `memory show <run_id>` / `delete` | `memory_entry` | — |

Examples (real `calc` captures):

`regression compare` — `regression_outcome.kind == "fact-set"`, exit 0:

```json
"summary": { "added": 0, "fixed": 0, "newly_active": 0, "newly_skipped": 0,
  "regressed": 1, "removed": 0, "still_failing": 0, "still_passing": 2,
  "still_skipped": 0, "total_baseline_tests": 3, "total_target_tests": 3 }
```

The `regressed` test surfaces in `test_transitions[]` with
`category: "regressed"` and a `target_failure_reference` carrying the
assertion text. The top-level `compare` adds a `coverage_delta` block,
here `kind: "unavailable"`, `reason: "missing-derived-facts"`.

`replay` — `replay_outcome.kind == "replay-result"`, exit 0:

```json
"replay_outcome": {
  "attempted_at": 1782370299982,
  "classification": "reproducible",
  "consistency_summary": { "original_failed": 1, "original_passed": 0, "replay_errored": 0, "replay_failed": 1, "replay_passed": 0 },
  "kind": "replay-result",
  "per_rerun_outcomes": ["failed"],
  "reason": null,
  "replayed_run_reference": { "run_id": "01KVYRRVYB6K156ABEDFQTMQCG", "created_at": 1782370299851, "schema_version": 1 },
  "reruns_failed": 0,
  "reruns_total": 1,
  "test_id": null
}
```

`classification` ∈ `reproducible` ∣ `inconsistent` ∣ `unable_to_replay`
(all exit 0, `ok: true`). `--reruns` defaults to `1`, `--timeout` to
`600.0`. Each rerun is persisted as a new Memory Entry; STRICT policy —
a single differing rerun yields `inconsistent`.

`localization` flags: `--formula` (default `ochiai`; valid values
`ochiai`, `op2`, `dstar2`, `tarantula`) and `--top-n` (default `10`). A
bad value is `code: "invalid-flag"`, exit 2. `localization_outcome` is
`fact-set` with `mode`, `confidence`, `formula`, `entries[]`, or
`unavailable` with an underscored `reason`.

---

## `warnings[]`

Independent of `errors[]`. Advisory — the command still succeeded;
warnings never change exit code or `ok`. Same `{code, message, details}`
shape. The two real codes both come from `localization`:

| `code` | `details` keys | Meaning |
|---|---|---|
| `localization-cache-rederived` | `previous`, `requested`, `cache_path` | Explicit `--formula`/`--top-n` differed from the cached finding; it was re-derived at the new flags. |
| `localization-formula-noop-in-mode` | `requested_formula`, `returned_formula`, `mode` | `--formula` mismatched, but the run's mode is `failure_proximity`, which pins `formula` to a placeholder — nothing to re-derive. |

Production agents should log warnings even when ignoring them.

---

## What to read next

- Deeper verbs (`coverage diff`, non-default formulas, `memory delete`)
  → [advanced.md](./advanced.md).
- Per-engine quirks → [languages.md](./languages.md).
- Error envelope by code → [troubleshooting.md](./troubleshooting.md).
