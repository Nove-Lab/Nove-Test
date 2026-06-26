# Advanced Usage

The happy path (`--version`, `--help`, `init`, `test`) plus the two
follow-ups (`status`, `inspect`) cover ~90% of day-to-day novetest use.
This page documents the **other verbs** — when to reach for them, the
signature, and what they return.

Every example uses the canonical `calc` demo (a tiny Python package:
`add`/`subtract` in `calc/arithmetic.py`, three tests). The "with the
bug" examples flip `subtract` to return `a + b`, so `test_subtract`
fails. Human tabs show TEXT-mode output; agent tabs show the
`novetest/v1` JSON envelope (six sorted keys: `command`, `data`,
`errors`, `ok`, `schema`, `warnings`; `schema` is always
`"novetest/v1"`). Agents should pin `NOVETEST_OUTPUT=json`.

Verbs covered here:

- **Run engine raw** — `novetest run`
- **Coverage engine** — `novetest coverage show`, `novetest coverage diff`
- **Regression engine** — `novetest regression compare`,
  `novetest regression latest`
- **Localization engine** — `novetest localization`,
  `novetest localization latest`
- **Replay engine** — `novetest replay`
- **Composed view** — `novetest compare`
- **Memory / history management** — `novetest memory list`,
  `novetest memory show`, `novetest memory delete`
- **Destructive reset** — `novetest reset --confirm`
- **Attribution** — `novetest licenses [--full]`

**Exit codes** (every verb here): `0` ok · `1` generic · `2` usage
(uninitialized, not-found run_id, invalid-flag, confirm-required) · `3`
user tests failed (still `ok: true`) · `4` engine missing / adapter
error · `5` storage. An `unavailable` outcome is **data** — `ok: true`,
exit `0` (replay's `engine-not-ready`/`target-missing` are the only
`unavailable` reasons that exit `4`).

---

## `novetest run` — run tests without orchestration

Invokes the native engine and persists a Run Record. That's it — it
does **not** auto-derive regression, localization, or recommendations
(that's `novetest test`). `run` is the **only** verb with
`--coverage`/`-c`; `novetest test` always collects coverage and has no
such flag. Go (`go-test`) runs execute but `--coverage` yields no
coverage facts for Go; the other five engines do.

::: tabs
@tab For human

```bash
novetest run [<target>] [--coverage]   # or -c
```

All-pass, no coverage:

```
✓ passed · 3/3 · run_id=01KVYRJJYJTS2NRCB2QZ57SSPJ
```

With the bug and `--coverage` (the `coverage:` line appears only with
the flag):

```
✗ failed · 2/3 · run_id=01KVYRRSWDPWGGGV3GX5QXXJK6
  failed tests:
    ✗ tests/test_arithmetic.py::test_subtract
  coverage: ✓ per-test · 13/13 statements (100.0%)
```

A run with failing tests exits **3** (data, not an error); a clean run
exits **0**.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest run [<target>] [--coverage] [-c]
```

Real envelope (`run` without coverage; `test_results` trimmed):

```json
{
  "command": "run",
  "data": {
    "memory_entry": {
      "entry_id": "01KVYRJK97SSR5DR840PH26VQK",
      "has_coverage_facts": false,
      "has_localization_findings": false,
      "has_regression_facts": false,
      "has_replay_result": false,
      "run_record": {
        "artifact_paths": { "…": "stdout/stderr/pytest_json_report (store-relative)" },
        "completed_at": 1782370094545,
        "ecosystem": "python",
        "engine_name": "pytest",
        "engine_version": "9.0.3",
        "metadata": { "native_exit_code": 0 },
        "run_reference": { "created_at": 1782370094375, "run_id": "01KVYRJK97SSR5DR840PH26VQK", "schema_version": 1 },
        "schema_version": 1,
        "started_at": 1782370094455,
        "status": "passed",
        "summary_counts": { "collected": 3, "passed": 3, "total": 3 },
        "target_expression": "",
        "target_type": "workspace",
        "test_results": [ "… per-test entries …" ]
      },
      "schema_version": 1,
      "stored_at": 1782370094578,
      "tombstoned_at": null
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

With `--coverage`, `data` also carries a `coverage_outcome` block;
without the flag it is omitted. The four `has_*` flags are live probes
that flip `true` once a peer engine writes its artifact. Exit: 0 passed
· 3 tests failed · 4 engine missing · 2 uninitialized / bad flag · 5
store corrupt.

:::

---

## `novetest coverage show <run_id>` — read persisted coverage

Cache-read only; never re-derives. Exit 0 even when facts are missing
(unavailability is data). The `coverage` sub-app has only `show` and
`diff` — no `coverage latest`.

::: tabs
@tab For human

```bash
novetest coverage show 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✓ per-test · 13/13 statements (100.0%) · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

A branch-coverage suite appends `· branches C/N`. A run executed without
coverage shows `— unavailable (missing-derived-facts)`.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest coverage show 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```json
{
  "command": "coverage.show",
  "data": {
    "coverage_outcome": {
      "kind": "fact-set",
      "mapping_granularity": "per-test",
      "run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "…": "…" },
      "summary": {
        "covered_branches": 0,
        "covered_statements": 13,
        "excluded_statements": 0,
        "missing_branches": 0,
        "missing_statements": 0,
        "num_branches": 0,
        "num_statements": 13,
        "percent_covered": 100.0
      }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

The `fact-set` block carries only `mapping_granularity` + `summary` (no
per-file detail). `kind: "unavailable"` (run ran without coverage) →
`reason: "missing-derived-facts"`, exit 0. A stale/unknown run_id is
different: `errors[0].code = "not-found"`, exit 2.

:::

---

## `novetest coverage diff <baseline> <target>` — per-file delta

Order is `baseline → target`; both sides must have coverage facts.

::: tabs
@tab For human

```bash
novetest coverage diff 01KVYRRSF4... 01KVYRRSWD...
```

Two coverage-bearing runs of the `calc` project (both 13/13 statements):

```
coverage diff · 01KVYRRSF48RMYV84MTB4XQ6P9 → 01KVYRRSWDPWGGGV3GX5QXXJK6
  100.0% → 100.0% (Δ +0.0%) · files +0/-0/~0
```

(Here both runs cover the whole module, so the delta is zero; a nonzero
`Δ` and per-file changes appear when coverage actually shifts between the
two runs.) If either side lacks coverage facts, the diff is `— unavailable
(missing-derived-facts)` (still exit 0).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest coverage diff 01KVYP0VJH... 01KVYP0WNB...
```

`data.coverage_delta` is `kind`-discriminated. `kind: "delta"` keys:
`baseline_run_reference`, `target_run_reference`, `baseline_granularity`,
`target_granularity`, `summary_before`, `summary_after`, `files_added`,
`files_removed`, `file_deltas` (files with no transition are omitted).
Real unavailable capture (one side has no coverage):

```json
{
  "command": "coverage.diff",
  "data": {
    "coverage_delta": {
      "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
      "kind": "unavailable",
      "reason": "missing-derived-facts",
      "run_reference": { "run_id": "01KVYP0VJHMQRNCW69KJPJDN52", "…": "…" }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

:::

---

## `novetest regression compare <baseline> <target>`

Explicit pair comparison; order is load-bearing (`compare A B` ≠
`compare B A`). Always exits 0 (even on `unavailable`); only a
stale/unknown run_id is `not-found`, exit 2. The `regression` sub-app
has only `compare` and `latest`.

::: tabs
@tab For human

```bash
novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

The bug regressed `test_subtract`:

```
✗ regressions · regressed=1 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Clean:

```
✓ clean · regressed=0 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Real `fact-set` (`output_diff` and the still_passing transitions
trimmed):

```json
{
  "command": "regression.compare",
  "data": {
    "regression_outcome": {
      "kind": "fact-set",
      "baseline_run_reference": { "run_id": "01KVYRRR9ZNAM1PBA9JTR4QXC6", "…": "…" },
      "target_run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "…": "…" },
      "baseline_engine_name": "pytest",
      "target_engine_name": "pytest",
      "summary": {
        "added": 0, "fixed": 0, "newly_active": 0, "newly_skipped": 0,
        "regressed": 1, "removed": 0, "still_failing": 0, "still_passing": 2,
        "still_skipped": 0, "total_baseline_tests": 3, "total_target_tests": 3
      },
      "test_transitions": [
        {
          "node_id": "tests/test_arithmetic.py::test_subtract",
          "category": "regressed",
          "baseline_outcome": "passed",
          "target_outcome": "failed",
          "target_failure_reference": "…/test_arithmetic.py:13: assert 14 == 6\n +  where 14 = subtract(10, 4)",
          "schema_version": 1,
          "…": "durations, failure refs"
        },
        "… still_passing transitions …"
      ],
      "coverage_change": null,
      "derived_at": 1782370298563,
      "output_diff": { "stdout_identical": false, "stderr_identical": true, "…": "sha256 + paths" },
      "metadata": {},
      "warnings": []
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Each `test_transitions[].category` ∈ the closed 9-value taxonomy:
`regressed`, `fixed`, `still_failing`, `still_passing`, `still_skipped`,
`newly_skipped`, `newly_active`, `added`, `removed`. (The array is
`test_transitions`; the key is `category` — there is no
`entries[].transition`.) Gate CI on `summary.regressed`.
`coverage_change` is `null` unless both runs carried coverage. Shape is
explicitly not frozen — pattern-match on `kind`. An `unavailable` block
carries two independently nullable refs plus a hyphenated `reason`
(`run-tombstoned`, `no-comparable-baseline`, `engine-mismatch`, …).

:::

## `novetest regression latest`

```bash
novetest regression latest
```

Same output/envelope shape (`command: "regression.latest"`). Auto-
resolves the two most recent comparable runs on the active target.
`novetest test` already runs this; the standalone verb is for
diagnostic re-querying. Needs ≥2 comparable runs, else `— unavailable
(no-comparable-baseline)` (exit 0).

---

## `novetest compare <baseline> <target>` — composed view

Composed regression **and** coverage delta in one envelope — `data` has
exactly two keys, `regression_outcome` and `coverage_delta` (this
distinguishes it from `regression compare`, which has only
`regression_outcome`). Cheaper than two calls; the memory entries are
read once. Each sub-block can be `unavailable` independently; exit 0.

::: tabs
@tab For human

```bash
novetest compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Bug scenario (baseline ran without coverage, so the coverage side is
unavailable):

```
regression: ✗ regressions · regressed=1 fixed=0 still_failing=0
coverage:   — unavailable (missing-derived-facts)
```

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```json
{
  "command": "compare",
  "data": {
    "regression_outcome": { "kind": "fact-set", "summary": { "regressed": 1, "…": "…" } },
    "coverage_delta": {
      "kind": "unavailable",
      "reason": "missing-derived-facts",
      "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
      "run_reference": { "…": "…" }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

:::

---

## `novetest localization` — SBFL fault localization

Ranks suspicious code locations for one run via Spectrum-Based Fault
Localization. `localization <run_id>` is the sub-app default verb (no
verb word); `latest` is the only named sub-verb.

| Flag | Default | Allowed |
|---|---|---|
| `--formula` | `ochiai` | `ochiai`, `op2`, `dstar2`, `tarantula` (lowercase; it is `dstar2`, not `dstar`) |
| `--top-n` | `10` | positive integer (hyphenated name; no short alias) |

The mode is auto-selected from coverage shape: `sbfl_per_test` (pytest
per-test, confidence high), `sbfl_aggregate` (file-level, medium), or
`failure_proximity` (no coverage — a heuristic, low). There is no
`--mode` flag.

::: tabs
@tab For human

```bash
novetest localization <run_id> [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
novetest localization latest [--formula ...] [--top-n ...]
```

With the bug:

```
sbfl_per_test · ochiai · 5 entries · confidence=high · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
  1. subtract@6 in calc/arithmetic.py (1.000)
  1. test_subtract@13 in tests/test_arithmetic.py (1.000)
  2. add@2 in calc/arithmetic.py (0.000)
  2. test_add_positive@5 in tests/test_arithmetic.py (0.000)
  2. test_add_zero@9 in tests/test_arithmetic.py (0.000)
```

Each line is `<rank>. <symbol>@<line> in <file> (<normalized score>)`.
The buggy `subtract@6` lands rank 1 at 1.000; ranks are dense, so ties
share a rank. `--formula dstar` is rejected (it is `dstar2`) — in text
mode the error renders as a `✗ <command>` header plus an indented
`<code>: <message>` line:

```
✗ localization
  invalid-flag: Invalid --formula='dstar'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']
```

(exit 2, as is `--top-n 0`.) No failing tests → `— unavailable
(no_failed_tests)` (exit 0). Re-invoking with a *different, explicit*
formula/top-n rewrites the cache and emits a
`⚠ localization-cache-rederived` warning.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest localization <run_id> [--formula ...] [--top-n ...]
NOVETEST_OUTPUT=json novetest localization latest [--formula ...] [--top-n ...]
```

Real `fact-set` (entries trimmed to rank 1):

```json
{
  "command": "localization",
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "…": "…" },
      "engine_name": "pytest",
      "ecosystem": "python",
      "mode": "sbfl_per_test",
      "confidence": "high",
      "formula": "ochiai",
      "alternate_scores_available": ["dstar2", "op2", "tarantula"],
      "top_n": 10,
      "entries": [
        {
          "rank": 1,
          "tied_with": ["entry_index_1"],
          "code_location": { "kind": "symbol", "file": "calc/arithmetic.py", "symbol": "subtract", "primary_line": 6, "line_range": [5, 6], "evidence_lines": [6] },
          "score_raw": 1.0,
          "score_normalized": 1.0,
          "formula": "ochiai",
          "alternate_scores": { "dstar2": 0.0, "op2": 1.0, "tarantula": 1.0 },
          "related_failed_tests": ["tests/test_arithmetic.py::test_subtract"],
          "evidence_citations": [ "… test_result / coverage_fact citations …" ]
        },
        "… 4 more entries …"
      ],
      "derived_at": 1782370298123,
      "metadata": { "changed_files_count": null, "regression_reweighted": null }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Gate on `mode`, not `formula` (in `failure_proximity` the `formula` is a
fixed placeholder `"ochiai"`). All four formulas are always computed;
`--formula` only picks which drives `rank`. `rank` is dense; `tied_with`
holds `"entry_index_<i>"` handles. Bad flag → `errors[0].code =
"invalid-flag"`, `data: {}`, exit 2. Unavailable block has 3 keys +
`kind` with **underscored** reasons (`no_failed_tests`,
`run_not_analyzable`, …), `ok: true`, exit 0. Explicit, differing
flags against a cached finding emit a `localization-cache-rederived`
warning (details: `previous`, `requested`, `cache_path`);
`failure_proximity` formula-only mismatch emits
`localization-formula-noop-in-mode` and does not re-derive.

:::

---

## `novetest replay <run_id>` — re-execute and classify

`<run_id>` is the **original** run's id. Replay reconstructs its target
and engine context and re-executes. Strict policy: one differing rerun
→ `inconsistent` (no majority vote). Replay **persists each rerun as a
new Memory Entry**. `novetest test` never auto-invokes replay.

| Flag | Default | Meaning |
|---|---|---|
| `--reruns` | `1` | Number of re-executions; bump to 5+ to probe flakiness. |
| `--timeout` | `600.0` | Per-rerun ceiling in seconds. |

::: tabs
@tab For human

```bash
novetest replay <run_id> [--reruns <int>] [--timeout <seconds>]
```

Replaying the failing run (it fails again → reproducible):

```
✓ reproducible · 1/1 · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

`1/1` is reruns matched / total. Classifications: `reproducible` /
`inconsistent` / `unable_to_replay` (the last is a valid success, exit
0). Some host-level unavailability (`engine-not-ready`,
`target-missing`) exits **4**.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest replay <run_id> [--reruns <int>] [--timeout <seconds>]
```

```json
{
  "command": "replay",
  "data": {
    "original_run_reference": { "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4", "…": "…" },
    "replay_outcome": {
      "kind": "replay-result",
      "classification": "reproducible",
      "reruns_total": 1,
      "reruns_failed": 0,
      "test_id": null,
      "reason": null,
      "replayed_run_reference": { "run_id": "01KVYRRVYB6K156ABEDFQTMQCG", "…": "…" },
      "per_rerun_outcomes": ["failed"],
      "consistency_summary": { "original_passed": 0, "original_failed": 1, "replay_passed": 0, "replay_failed": 1, "replay_errored": 0 },
      "attempted_at": 1782370299982
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

`data` has `original_run_reference` and `replay_outcome`.
`per_rerun_outcomes` length == `--reruns`; `consistency_summary` counts
runs, not tests. `replayed_run_reference` is the first rerun (now in
`memory list`). Exit: `ReplayResult` (incl. `unable_to_replay`) → 0;
fake run_id → `not-found`, 2; `engine-not-ready`/`target-missing` →
`replay-<reason>`, 4.

:::

---

## `novetest memory` — history management

### `novetest memory list`

List Run History newest-first (tombstones included).

::: tabs
@tab For human

```bash
novetest memory list
```

```
4 runs

run_id                      target       status  created_at
01KVYRJK97SSR5DR840PH26VQK  <workspace>  passed  2026-06-25T06:48:14.375000Z
01KVYRJJYJTS2NRCB2QZ57SSPJ  <workspace>  passed  2026-06-25T06:48:14.034000Z
01KVYRJJJ75ZRHC05GNKYRK99S  <workspace>  passed  2026-06-25T06:48:13.639000Z
01KVYRJJ4PN2F6DPKW1FHD1SP6  <workspace>  passed  2026-06-25T06:48:13.206000Z
```

`target` shows `<workspace>` for a whole-project run. A tombstoned row's
`status` cell reads `tombstoned (tombstoned)`.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest memory list
```

`data` has exactly `count` and `entries` (newest-first; tombstones
included). There is **no** `total_count` / `tombstoned_count`. Run
details live under `run_record`:

```json
{
  "command": "memory.list",
  "data": {
    "count": 4,
    "entries": [
      {
        "entry_id": "01KVYP0WNB8X47ZPN85ZAYBKSN",
        "has_coverage_facts": true,
        "has_localization_findings": false,
        "has_regression_facts": true,
        "has_replay_result": false,
        "run_record": { "engine_name": "pytest", "status": "passed", "target_type": "workspace", "…": "…" },
        "schema_version": 1,
        "stored_at": 1782367417274,
        "tombstoned_at": null
      },
      "… 3 more entries …"
    ]
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

A tombstoned entry has a non-null `tombstoned_at` and
`run_record.status == "tombstoned"`.

:::

### `novetest memory show <run_id>`

Show one run's Memory Entry (live or tombstoned).

::: tabs
@tab For human

```bash
novetest memory show 01KVYP0WNB8X47ZPN85ZAYBKSN
```

```
run_id:     01KVYP0WNB8X47ZPN85ZAYBKSN
target:     <workspace>
status:     passed
engine:     pytest 9.0.3 (python)
created:    2026-06-25T06:03:37.003000Z
duration:   150ms
tests:      collected=3 passed=3 total=3
evidence:   coverage=yes regression=yes localization=no replay=no
tombstoned: no
```

The `evidence:` line flips to `yes` as each peer engine derives its
artifact. The pytest version shown is *your* pytest.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest memory show 01KVYP0WNB8X47ZPN85ZAYBKSN
```

`data = {"memory_entry": <full MemoryEntry>}` — same shape as a
`memory list` entry, including the full `run_record` (`artifact_paths`,
`summary_counts`, `test_results`, …). Works for tombstoned runs.
Unknown run_id → `not-found`, exit 2.

:::

### `novetest memory delete <run_id>`

Tombstone a Memory Entry (a **soft delete** — atomic POSIX rename into
`memory/tombstones/`). The record is not erased; its `status` becomes
`tombstoned` and `tombstoned_at` is set, and it still appears in
`memory list` / `memory show`. Re-deleting is a no-op success. Hard wipe
is only `reset --confirm`.

::: tabs
@tab For human

```bash
novetest memory delete 01KVYQ1SA2751X90JDNSG00RFD
```

```
✓ Tombstoned run_id=01KVYQ1SA2751X90JDNSG00RFD
```

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest memory delete 01KVYQ1SA2751X90JDNSG00RFD
```

```json
{
  "command": "memory.delete",
  "data": {
    "memory_entry": {
      "entry_id": "01KVYQ1SA2751X90JDNSG00RFD",
      "run_record": { "status": "tombstoned", "metadata": { "tombstoned_at": 1782368495708, "…": "…" }, "…": "…" },
      "schema_version": 1,
      "stored_at": 1782368495707,
      "tombstoned_at": 1782368495708,
      "…": "has_* flags"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Unknown run_id → `not-found`, exit 2.

:::

---

## `novetest reset --confirm` — hard wipe

Deletes the **entire** `.novetest/` store (live runs, tombstones, and
all derived coverage / regression / localization / replay facts) and
re-initializes an empty store. Nothing survives — the destructive
counterpart to `memory delete`. A corrupt store is refused
(`store-corrupt`, exit 5), not auto-wiped.

::: tabs
@tab For human

```bash
novetest reset            # refuses
```

```
✗ reset
  confirm-required: `novetest reset` is destructive. Pass --confirm to acknowledge.
```

(exit 2, nothing changed.) With `--confirm`:

```bash
novetest reset --confirm
```

```
✓ Reset .novetest/ at /path/to/project/.novetest
  removed: nothing
  engine readiness: engine-missing — no engine detected
  issue: no supported (ecosystem, native engine) pair detected in workspace
```

`removed:` reads `nothing` when the store was already empty. Reset
re-detects your engine and reports its readiness, like `init` (the
example above ran where no engine is detectable).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest reset --confirm
```

Without `--confirm`: `errors[0].code = "confirm-required"`, exit 2,
nothing mutated. With it:

```json
{
  "command": "reset",
  "data": {
    "engine_readiness": { "state": "engine-missing", "ecosystem": null, "engine": null, "issues": ["no supported (ecosystem, native engine) pair detected in workspace"], "…": "…" },
    "initialized_at": 1782368398311,
    "items_removed": { "coverage_facts": 0, "localization_findings": 0, "regression_pairs": 0, "replay_results": 0, "runs": 0, "tombstones": 0 },
    "previous_initialized_at": 1782368397706,
    "store_path": "/abs/path/.novetest",
    "store_state": "ready"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

`items_removed` always has exactly those six keys. An OSError during
wipe → `store-wipe-failed`, exit 5.

:::

---

## `novetest licenses [--full]`

Lists every third-party component novetest redistributes or links to,
with its SPDX license tag. For legal / audit / SBOM workflows.

::: tabs
@tab For human

```bash
novetest licenses          # summary list
novetest licenses --full   # summary + verbatim NOTICES.md text
```

```
licenses (5 third-party components)

  runtime dependencies
    cyclopts (>=3.0)                            Apache-2.0
    numpy (>=1.26)                              BSD-3-Clause

  vendored binary
    junit-platform-console-standalone (1.11.4)  EPL-2.0

  install-time bootstrap
    PyApp (0.22.0)                              Apache-2.0 OR MIT
    python-build-standalone (CPython)           PSF + permissive (OpenSSL, libffi, ncurses, etc.)

  full verbatim license texts: novetest licenses --full
  attribution file (in wheel): *.dist-info/licenses/NOTICES.md
```

With `--full`, the verbatim `NOTICES.md` body is appended.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest licenses
NOVETEST_OUTPUT=json novetest licenses --full
```

```json
{
  "command": "licenses",
  "data": {
    "licenses": [
      { "package": "cyclopts", "version": ">=3.0", "license": "Apache-2.0", "source": "runtime", "project_url": "https://github.com/BrianPugh/cyclopts" },
      { "package": "numpy", "version": ">=1.26", "license": "BSD-3-Clause", "source": "runtime", "project_url": "https://github.com/numpy/numpy" },
      { "package": "junit-platform-console-standalone", "version": "1.11.4", "license": "EPL-2.0", "source": "vendored", "project_url": "https://github.com/junit-team/junit5" },
      { "package": "PyApp", "version": "0.22.0", "license": "Apache-2.0 OR MIT", "source": "install-time-bootstrap", "project_url": "https://github.com/ofek/pyapp" },
      { "package": "python-build-standalone", "version": "CPython", "license": "PSF + permissive (OpenSSL, libffi, ncurses, etc.)", "source": "install-time-bootstrap", "project_url": "https://github.com/indygreg/python-build-standalone" }
    ],
    "notices_reference": "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)",
    "summary": "Nove Test redistributes or links to 5 third-party components."
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

`data.licenses[].source` ∈ `{runtime, vendored, install-time-bootstrap}`.
With `--full`, `data.notices_text` is added (verbatim `NOTICES.md` body).
The data keys are `licenses`, `notices_reference`, `summary`.

:::

---

## Output mode override (any verb)

::: tabs
@tab For human

```bash
novetest --output {text|json|ndjson} <verb>
# or
NOVETEST_OUTPUT={text|json|ndjson} novetest <verb>
```

| Mode | Output |
|---|---|
| `text` | Human-readable summary (default on a TTY). What this manual shows. |
| `json` | Pretty-printed `novetest/v1` envelope (`indent=2`, sorted keys). Default when piped. |
| `ndjson` | The same envelope on one compact line. For log streams. |

Precedence: **explicit `--output` > `NOVETEST_OUTPUT` env > TTY
auto-detect**. The `--output` flag is global and may appear **anywhere**
in the command line (it is stripped before the verb is dispatched). There
is no `--text` / `--json` flag. To preview the agent view:

```bash
NOVETEST_OUTPUT=json novetest test | jq .
```

@tab For agent

```bash
novetest --output {json|text|ndjson} <verb>
NOVETEST_OUTPUT={json|text|ndjson} novetest <verb>
```

| Mode | Byte shape |
|---|---|
| `json` | Pretty-printed envelope (`indent=2`, sorted keys, trailing newline). |
| `ndjson` | Single compact line (no internal newlines, trailing `\n`). |
| `text` | Human-readable projection (different bytes from the envelope). |

Default is JSON when stdout is not a TTY, so a piped/CI call already
emits JSON. Pin `NOVETEST_OUTPUT=json` to be explicit. The `--output`
flag is global and may appear anywhere in argv (stripped before
dispatch); `--text` is parsed as an unknown command.

:::

---

## What this page deliberately does NOT cover

- Engine-side flag pass-through (pytest nodeid filtering, jest regex,
  cargo nextest filter, …) — those live in the native engine's docs.
  novetest forwards targets verbatim.
- `--workspace <path>` override — rarely needed; `cd` first is the
  recommended pattern.
- The full SBFL math behind each formula → public design docs.
- The recommendation synthesis taxonomy beyond
  [Understanding Results](./understanding-results.md) → public design docs.
- Adapter internals (how each engine is invoked, normalization rules) →
  public design docs.
- Replay classification rules (`inconsistent` vs `unable_to_replay`) →
  public design docs.

The design docs are the source of truth for those. This page is for
calling the verbs.

---

## What to read next

- An envelope came back unexpected, or a verb errored →
  [Troubleshooting](./troubleshooting.md).
- Back up one level →
  [Understanding Results](./understanding-results.md).
