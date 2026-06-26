# Understanding Results

After `novetest test` returns you have a result to interpret — a
scannable text block (human) or a `novetest/v1` JSON envelope (agent).
This page covers:

1. The six exit codes and what they mean.
2. The `errors[].code` catalog (failure paths).
3. Reading the output (glyphs / the envelope frame).
4. `data.stage_eligibility`.
5. `data.recommendations[]` and the closed seven-category taxonomy.
6. The follow-up verbs `status` and `inspect`.
7. The sub-report verbs (`coverage`, `regression`, `localization`, `replay`, `compare`, `memory`).
8. A worked example: green → bug → fix.
9. `warnings[]`.

Every output below is a real capture from the **`calc`** example (see
[Quick Start](./quick-start.md)). Run ids are 26-character ULIDs; yours
will differ.

---

## Exit codes

Nove Test uses six exit codes. Read it with `echo $?` (POSIX) or
`$LASTEXITCODE` (PowerShell).

| Code | Constant | `ok` | Meaning |
|---|---|---|---|
| `0` | `EXIT_OK` | `true` | CLI succeeded; tests passed. Data-level `unavailable` outcomes also land here. |
| `1` | `EXIT_GENERIC` | `false` | Unexpected CLI exception. Report as a bug. |
| `2` | `EXIT_USAGE` | `false` | Bad input (missing Project Store, unknown `run_id`, invalid flag, `reset` without `--confirm`). |
| `3` | `EXIT_USER_TESTS_FAILED` | **`true`** | CLI succeeded; your tests **failed**. Product data, not a tooling error. |
| `4` | `EXIT_ENGINE_MISSING` | `false` | Native engine not ready (missing on PATH) or adapter invocation error. |
| `5` | `EXIT_STORAGE` | `false` | Project Store corrupt or unreadable. |

Two invariants that trip people up:

- **Exit 3 is normal.** Your tests failed; the CLI did its job. `ok` stays
  `true` — failing tests are *data*. (So `ok: true` does **not** imply
  exit 0; always read both.)
- **An `unavailable` outcome is exit 0.** When coverage / regression /
  localization can't produce facts for a structural reason (no baseline,
  no failing tests, ran without `--coverage`), that is reported as data on
  a successful command — never an error.

---

## `errors[].code` catalog

When `ok: false`, `errors[]` carries at least one `{code, message,
details}` object. Pin against `code` (not the message text).

| `errors[].code` | Exit | Triggered when | Recovery |
|---|---|---|---|
| `uninitialized` | 2 | A non-`init` verb run where no `.novetest/` exists in any ancestor. | `novetest init`, or `cd` into a store tree. |
| `not-found` | 2 | A `run_id` matches no Memory Entry. Message: `No Memory Entry for run_id='<id>'`. | List ids with `novetest memory list`. |
| `invalid-flag` | 2 | Flag value outside the allowed set (bad `--formula`, `--top-n < 1`). Message lists allowed values. | Re-issue with a valid flag. |
| `confirm-required` | 2 | `novetest reset` without `--confirm`. | Pass `--confirm`. |
| `engine-engine-missing` | 4 | Readiness state is `engine-missing`. `data.engine_readiness` is present. | Install/configure the engine. |
| `adapter-<kind>` | 4 | A native adapter invocation failed (e.g. `adapter-unparseable-output`). `details.install_hint` may carry a fix. | Apply the hint. |
| `store-corrupt` | 5 | `.novetest/store.json` unreadable/malformed. | Fix the file; worst case `rm -rf .novetest && novetest init` (loses history). |

The doubled-looking `engine-engine-missing` is the `engine-` prefix plus
the readiness state `engine-missing` — it is **not** `engine-not-ready`
(no such code/state exists).

---

## Reading the output

::: tabs
@tab For human

Every `novetest test` invocation prints the same shape:

```
<count> recommendation(s) · <count> category/categories · run_id=<ULID>

  <glyph> [<category>] <human-readable sentence>
      ↳ <citation>
```

Glyph palette (no ANSI color at MVP — meaning is carried by glyphs +
words):

| Glyph | Means |
|---|---|
| `✓` | Good / informational; no action. |
| `✗` | Bad news — look here. |
| `—` | Unavailable for a structural reason; not an error. |
| `!` | An action recommendation needs attention. |
| `?` | "Can't tell" (e.g. replay not yet attempted). |
| `⚠` | Advisory warning. |
| `·` | Separator. |
| `↳` | Citation pointer (the evidence behind a line). |

The all-green block:

```
1 recommendation · 1 category · run_id=01KVYRJJJ75ZRHC05GNKYRK99S

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJJ75ZRHC05GNKYRK99S
```

@tab For agent

Every command emits the same frame, keys sorted alphabetically:

```json
{ "command": "test", "data": { }, "errors": [], "ok": true,
  "schema": "novetest/v1", "warnings": [] }
```

Exactly six top-level keys: `schema` (always `"novetest/v1"`), `command`,
`ok`, `data`, `errors`, `warnings`. There is **no** top-level `version`,
`verb`, or `exit_code` field — the exit code is the process status.
`errors`/`warnings` are arrays of `{code, message, details}`.

Routing skeleton:

```python
if   code == 0: handle_success(env)        # ok: true
elif code == 3: handle_test_failures(env)  # ok: true — read recommendations
elif code == 2: handle_usage_error(env)    # ok: false — fix the call
elif code == 4: handle_engine_missing(env) # ok: false — install/configure engine
elif code == 5: handle_storage_error(env)  # ok: false — store damaged
elif code == 1: handle_generic_error(env)  # ok: false — report as bug
```

:::

---

## `data.stage_eligibility`

The `test` envelope's `data` has exactly four keys: `run_reference`,
`stage_eligibility`, `recommendation_schema_version` (currently `1`), and
`recommendations`. The stage-eligibility block (real `calc` failing-run
capture):

```json
"stage_eligibility": {
  "coverage": "available",
  "localization": "sbfl_per_test",
  "regression": "available",
  "replay": "not_run"
}
```

| Slot | Values | Notes |
|---|---|---|
| `coverage` | `available` ∣ `unavailable` ∣ `not_applicable` | `test` always collects coverage, so usually `available`. |
| `regression` | `available` ∣ `unavailable` ∣ `not_applicable` | `unavailable` on the first run for a target (no baseline). |
| `localization` | **the SBFL mode string** (`sbfl_per_test` ∣ `sbfl_aggregate` ∣ `failure_proximity`) when a finding exists; else `unavailable` | NOT the word "available". A passing run is `unavailable` (no failing tests). |
| `replay` | always `not_run` | `test` never invokes replay. |

A stage that is `unavailable` simply contributes no recommendations — it
is not an error signal.

---

## `data.recommendations[]`

Each recommendation has exactly these keys: `recommendation_id`,
`category`, `priority`, `summary`, `slots`, `evidence_citations`. There is
**no `severity` field** — `priority` (int, **1 = most urgent … 7 = all
green**) is the only ranking.

### Closed taxonomy (seven categories)

| `priority` | `category` | Fires when |
|---|---|---|
| 1 | `regression_with_localization` | A newly-failing test overlaps a top SBFL location — the strongest signal. |
| 2 | `investigate_location` | A localization finding, confidence ∈ {high, medium}, rank ≤ 3. |
| 3 | `investigate_regression` | A `regressed` (newly-failing vs baseline) transition. |
| 4 | `coverage_gap` | Uncovered lines overlap a suspicious location's span. |
| 5 | `flaky_suspected` | A replay classified the suite `inconsistent`. **Never fires from `test`** (replay isn't wired into `test`). |
| 6 | `unavailable_analysis` | Tests failed AND some downstream stage was `unavailable`. Informational. |
| 7 | `all_green` | Zero failures AND zero regressed. Mutually exclusive — never coexists with another category. |

Behavioural notes:

- `regression_with_localization` and `investigate_regression` require a
  **newly-failing** transition (passing in the baseline, failing now).
  Re-running an already-failing suite does not re-emit them.
- `flaky_suspected` never appears in real `test` output.
- `all_green` never coexists with another category.

### Routing decision tree

::: tabs
@tab For human

On the happy path there is nothing to do — `[all_green]`. Otherwise read
the **top** line (lowest priority number); its bracketed `[category]` and
sentence tell you what to look at, and the `↳` citation tells you where
the evidence lives. Then act, and re-run `novetest test`.

@tab For agent

```python
recs = sorted(env["data"]["recommendations"], key=lambda r: r["priority"])
if not recs:
    return
top = recs[0]
cat = top["category"]

if cat == "all_green":
    return                                  # nothing to do
elif cat in {"investigate_location", "regression_with_localization", "coverage_gap"}:
    # location-bearing slots: file, primary_line, line_range, rank, symbol, formula, mode.
    # The array is NOT score-ordered, and ties share a priority — pick the
    # strongest finding by rank (asc) then score_normalized (desc):
    best = min((r for r in recs if r["category"] == cat),
               key=lambda r: (r["slots"]["rank"], -r["slots"]["score_normalized"]))
    target = (best["slots"]["file"], best["slots"]["primary_line"])
elif cat == "investigate_regression":
    test_id = top["slots"]["test_id"]       # newly-failing test
elif cat == "unavailable_analysis":
    stages  = top["slots"]["unavailable_stages"]
    reasons = top["slots"]["reason_per_stage"]   # informational
```

Invariant: **route on `category`, sort by `priority` ascending**; within
a location-bearing category, rank findings by `slots.rank` (then
`score_normalized`) — not by array position. Read `slots` / walk
`evidence_citations[]`; never parse `summary`.

`evidence_citations[].kind` is a closed set: `localization_finding`,
`coverage_fact`, `regression_fact`, `replay_result`, `test_result`,
`run_reference` — each carries a `selector` pointing back into a
persisted artifact you can drill into.

:::

---

## A worked example: green → bug → fix

### 1. Green run

```bash
novetest test
```

::: tabs
@tab For human

```
1 recommendation · 1 category · run_id=01KVYRJJJ75ZRHC05GNKYRK99S

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJJ75ZRHC05GNKYRK99S
```

Exit 0.

@tab For agent

`recommendations[0].category == "all_green"`, `priority 7`, exit 0,
`ok: true`. `stage_eligibility.localization == "unavailable"` (nothing to
localize on a green run).

:::

### 2. Introduce the bug

Change `calc/arithmetic.py` line 6 so `subtract` adds instead of
subtracts (`return a + b`), then `novetest test`:

::: tabs
@tab For human

```
5 recommendations · 1 category · run_id=01KVYRRSF48RMYV84MTB4XQ6P9

  ! [investigate_location] Investigate `add`@2 in `calc/arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).
      ↳ localization_finding calc/arithmetic.py:2 (rank 2)
  ! [investigate_location] Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
      ↳ localization_finding calc/arithmetic.py:6 (rank 1)
  ! [investigate_location] Investigate `test_subtract`@13 in `tests/test_arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
      ↳ localization_finding tests/test_arithmetic.py:13 (rank 1)
  … (two more rank-2 entries: `test_add_positive`@5, `test_add_zero`@9)
```

Exit **3** (`ok: true`). Recommendations are emitted in a stable order
(not sorted by score), so act on the highest-**rank** line: `subtract`@6
at rank 1, `ochiai=1.000` — the line you broke.

@tab For agent

```json
{
  "command": "test",
  "data": {
    "recommendations": [
      { "category": "investigate_location", "priority": 2,
        "summary": "Investigate `add`@2 in `calc/arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).",
        "slots": { "file": "calc/arithmetic.py", "primary_line": 2, "line_range": [1, 2],
                   "rank": 2, "score_normalized": 0.0, "symbol": "add",
                   "formula": "ochiai", "mode": "sbfl_per_test" } },
      { "category": "investigate_location", "priority": 2,
        "summary": "Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).",
        "slots": { "file": "calc/arithmetic.py", "primary_line": 6, "line_range": [5, 6],
                   "rank": 1, "score_normalized": 1.0, "symbol": "subtract",
                   "formula": "ochiai", "mode": "sbfl_per_test" } }
      /* …3 more investigate_location recommendations… */
    ],
    "run_reference": { "run_id": "01KVYRRSF48RMYV84MTB4XQ6P9", "created_at": 1782370297316, "schema_version": 1 },
    "stage_eligibility": { "coverage": "available", "localization": "sbfl_per_test",
                           "regression": "available", "replay": "not_run" }
  },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": []
}
```

Exit **3**, `ok: true`. NOTE the array is **not** score-ordered:
`recommendations[0]` here is `add`@2 (rank 2, `score_normalized: 0.0`). To
find the culprit, pick the `investigate_location` finding with the lowest
`slots.rank` / highest `slots.score_normalized` — `subtract`@6 (rank 1,
score 1.0) — then route on its `slots.file` + `slots.primary_line`.

:::

### 3. Fix and re-run

Restore line 6 to `return a - b`, then `novetest test` → back to the green
block, exit 0. The loop is: read the top recommendation, act, re-run.

---

## Follow-up verbs: `status` and `inspect`

::: tabs
@tab For human

`novetest status` — the project's latest-run availability at a glance
(read-only, derives nothing):

```
latest run · 01KW0PATQMBP2GXMFRX3J5EEX3 · history: 2 runs

  ✓ coverage      available
  ✓ regression    available
  — localization  unavailable
  — replay        unavailable
```

(`—` marks a sub-report that is unavailable for a structural reason — here
the latest run had no failing tests to localize, and replay only runs when
you call `novetest replay`.) `novetest status` reflects the **latest** run.

`novetest inspect <run_id>` — everything known about one run (a pure read;
works on tombstoned runs too):

```
✗ 01KVYRRRN9FWVNQWVHNE1QHAQ4 · failed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 13/13 statements (100.0%)
  regression    ✗ regressions · regressed=1 fixed=0 still_failing=0
  localization  sbfl_per_test · ochiai · 5 entries · confidence=high
  replay        ? unavailable (missing-derived-facts)
```

`target=<workspace>` means the whole project. `replay` stays unavailable
until you run `novetest replay <run_id>`.

@tab For agent

`status` `data`: `latest_run_reference` (null after a fresh `init`),
`run_history_size`, `sub_reports` (`available`/`unavailable` per stage).

`inspect` `data`: `run_reference`, `run_summary`, `sub_reports`, and four
discriminated-union outcome blocks — **switch on `kind`**:

| Field | `kind` ∈ |
|---|---|
| `coverage_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `regression_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `localization_outcome` | `"fact-set"` ∣ `"unavailable"` |
| `replay_outcome` | `"replay-result"` ∣ `"unavailable"` |

```json
"coverage_outcome": { "kind": "fact-set", "mapping_granularity": "per-test",
  "summary": { "percent_covered": 100.0, "num_statements": 13, "covered_statements": 13, "...": "..." } },
"regression_outcome": { "kind": "fact-set",
  "summary": { "regressed": 1, "still_passing": 2, "total_target_tests": 3, "...": "..." }, "...": "..." },
"localization_outcome": { "kind": "fact-set", "mode": "sbfl_per_test", "confidence": "high",
  "formula": "ochiai", "top_n": 10, "entries": [ "...5 ranked entries..." ] },
"replay_outcome": { "kind": "unavailable", "reason": "missing-derived-facts",
  "detail": "no replay attempt has been made for this run" }
```

`inspect` is cache-only — it never runs replay. A stale/unknown `run_id` →
`errors[].code == "not-found"`, exit 2.

:::

---

## Sub-report verbs

All take a `run_id` (copy from `memory list` / `inspect` / the `run_id=`
header). Each returns one `data.<outcome>` block discriminated on `kind`.

| Verb | `data` key(s) | `kind` values |
|---|---|---|
| `memory list` | `count`, `entries[]` | — |
| `memory show <run_id>` / `delete` | `memory_entry` | — |
| `coverage show <run_id>` | `coverage_outcome` | `fact-set` ∣ `unavailable` |
| `coverage diff <base> <target>` | `coverage_delta` | `delta` ∣ `unavailable` |
| `regression compare <base> <target>` | `regression_outcome` | `fact-set` ∣ `unavailable` |
| `regression latest` | `regression_outcome` | `fact-set` ∣ `unavailable` |
| `compare <base> <target>` | `regression_outcome` **and** `coverage_delta` | as above |
| `localization <run_id>` / `latest` | `localization_outcome` | `fact-set` ∣ `unavailable` |
| `replay <run_id>` | `replay_outcome` (+ `original_run_reference`) | `replay-result` ∣ `unavailable` |

::: tabs
@tab For human

Confirm the regression against the green baseline (baseline first, target
second — order matters):

```bash
novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✗ regressions · regressed=1 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

`novetest compare` shows both signals at once (here coverage is
unavailable because the baseline run was stored without coverage):

```
regression: ✗ regressions · regressed=1 fixed=0 still_failing=0
coverage:   — unavailable (missing-derived-facts)
```

`novetest replay` re-executes and classifies; the reruns become new runs
in `memory list`:

```
✓ reproducible · 1/1 · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

@tab For agent

`regression compare` → `regression_outcome.kind == "fact-set"`, exit 0:

```json
"summary": { "regressed": 1, "fixed": 0, "still_passing": 2, "still_failing": 0,
  "total_baseline_tests": 3, "total_target_tests": 3, "added": 0, "removed": 0,
  "newly_active": 0, "newly_skipped": 0, "still_skipped": 0 }
```

The regressed test surfaces in `test_transitions[]` with
`category: "regressed"` and a `target_failure_reference`. Top-level
`compare` adds a `coverage_delta` block (here `kind: "unavailable"`).

`replay` → `replay_outcome.kind == "replay-result"`, exit 0:

```json
"replay_outcome": {
  "classification": "reproducible",
  "consistency_summary": { "original_passed": 0, "original_failed": 1,
    "replay_passed": 0, "replay_failed": 1, "replay_errored": 0 },
  "per_rerun_outcomes": ["failed"], "reruns_total": 1, "reruns_failed": 0,
  "replayed_run_reference": { "run_id": "01KVYRRVYB6K156ABEDFQTMQCG", "...": "..." },
  "test_id": null, "reason": null, "attempted_at": 1782370299982, "kind": "replay-result"
}
```

`classification` ∈ `reproducible` ∣ `inconsistent` ∣ `unable_to_replay`
(all exit 0). `--reruns` defaults `1`, `--timeout` `600.0`. STRICT policy:
one differing rerun → `inconsistent`. `localization` flags: `--formula`
(default `ochiai`; values `ochiai`/`op2`/`dstar2`/`tarantula`) and
`--top-n` (default `10`); a bad value is `invalid-flag`, exit 2.

:::

---

## `warnings[]`

Independent of `errors[]`. Advisory — the command still succeeded;
warnings never change the exit code or `ok`. Same `{code, message,
details}` shape. The two real codes both come from `localization`:

| `code` | Meaning |
|---|---|
| `localization-cache-rederived` | You passed `--formula`/`--top-n` differing from the cached finding, so it was re-derived at the new flags. |
| `localization-formula-noop-in-mode` | You passed `--formula`, but the run's SBFL mode (`failure_proximity`) does not consume a formula — nothing changed. |

---

## What to read next

- **[Advanced Usage](./advanced-usage.md)** — `coverage diff`, non-default
  `localization` formulas, `replay --reruns`, `memory` lifecycle.
- **[Supported Languages](./supported-languages.md)** — engine-specific
  behaviour (e.g. go-test produces no coverage facts).
- **[Troubleshooting](./troubleshooting.md)** — every error code, its
  cause, and the fix.
