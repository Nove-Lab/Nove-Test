# Advanced verbs (Agent)

Every non-happy-path verb with its envelope shape. The happy path
(`--version`, `--help`, `init`, `test`, `status`, `inspect`) is
documented in [quick-start.md](./quick-start.md) and
[after-test.md](./after-test.md); this page covers the other verbs.

Pin `NOVETEST_OUTPUT=json` for every call. Every envelope has the same
six top-level keys, **sorted alphabetically**: `command`, `data`,
`errors`, `ok`, `schema`, `warnings`. `schema` is always
`"novetest/v1"`. There is no top-level `version`, `verb`, or
`exit_code` field — versioning lives at `schema`, and the exit code is
the process exit. `errors`/`warnings` are arrays of
`{code, message, details}`.

All JSON below is quoted from real captured runs of the canonical
`calc` project (or trimmed from it, marked with `…`). Long arrays are
elided; no key is invented.

### Exit codes (every verb on this page)

| exit | meaning |
|---|---|
| 0 | ok |
| 1 | generic failure |
| 2 | usage / validation (uninitialized, not-found run_id, invalid-flag, confirm-required) |
| 3 | user tests failed (still `ok: true` — failing tests are data) |
| 4 | engine missing / adapter error (and replay `engine-not-ready` / `target-missing`) |
| 5 | storage (store corrupt, wipe failed) |

Routing rule: branch on `ok` + exit first; treat `data.*_outcome.kind`
(`"fact-set"` / `"delta"` / `"replay-result"` vs `"unavailable"`) as
the data-level discriminator. An `unavailable` outcome is `ok: true`,
exit `0` — it is **data, not an error** (replay's `engine-not-ready` /
`target-missing` are the only `unavailable` reasons that map to a
non-zero exit, 4).

---

## `novetest run` — Run engine, raw

```bash
NOVETEST_OUTPUT=json novetest run [<target>] [--coverage] [-c]
```

Persists a Run Record without orchestration (no auto-regression, no
auto-localization, no recommendation synthesis). Useful for CI
pipelines that split "run tests" from "analyze results".

| Flag | Effect |
|---|---|
| `<target>` | Test target expression. Same shape as `novetest test`. Forwarded verbatim to the native engine. |
| `--coverage` / `-c` | Also derive + persist Coverage Facts. Without it, only the Run Record lands. |

### Envelope (real, `run` without coverage; `test_results` trimmed)

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
        "artifact_paths": {
          "pytest_json_report": "run/artifacts/run_01KVYRJK97SSR5DR840PH26VQK/native/pytest-report.json",
          "stderr": "run/artifacts/run_01KVYRJK97SSR5DR840PH26VQK/native/stderr.log",
          "stdout": "run/artifacts/run_01KVYRJK97SSR5DR840PH26VQK/native/stdout.log"
        },
        "completed_at": 1782370094545,
        "ecosystem": "python",
        "engine_name": "pytest",
        "engine_version": "9.0.3",
        "metadata": { "native_exit_code": 0 },
        "run_reference": {
          "created_at": 1782370094375,
          "run_id": "01KVYRJK97SSR5DR840PH26VQK",
          "schema_version": 1
        },
        "schema_version": 1,
        "started_at": 1782370094455,
        "status": "passed",
        "summary_counts": { "collected": 3, "passed": 3, "total": 3 },
        "target_expression": "",
        "target_type": "workspace",
        "test_results": [ "… per-test entries (node_id, outcome, duration_ms, failure_reference) …" ]
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

Notes:
- The four `has_*` flags are live filesystem probes; they read `false`
  immediately after a bare `run` and flip `true` once the peer engine
  (coverage/regression/localization/replay) writes its artifact.
- `summary_counts` is an open `dict[str,int]`; a failing run adds
  `failed`, etc. `engine_version` may be `null`.
- With `--coverage`, `data` gains a `coverage_outcome` block (same
  shape as `coverage show` below); without the flag it is **omitted
  entirely**.
- Exit: 0 passed · 3 tests failed (still `ok: true`) · 4 engine missing
  · 2 uninitialized / bad flag · 5 store corrupt.

---

## `novetest coverage show <run_id>`

Read persisted Coverage Facts. Cache-read only; never derives. Exit 0
even when facts are missing.

```bash
NOVETEST_OUTPUT=json novetest coverage show 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

### Envelope (real; `fact-set`)

```json
{
  "command": "coverage.show",
  "data": {
    "coverage_outcome": {
      "kind": "fact-set",
      "mapping_granularity": "per-test",
      "run_reference": {
        "created_at": 1782370296489,
        "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4",
        "schema_version": 1
      },
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

The `fact-set` block carries only `mapping_granularity` + `summary` —
**no per-file detail** (that lives only in the on-disk
`coverage_facts.json`). `mapping_granularity` is `per-test` only for
pytest-with-contexts; every other engine is `aggregate`.

Unavailable (run exists, ran without coverage) — still exit 0,
`ok: true`:

```json
{
  "command": "coverage.show",
  "data": {
    "coverage_outcome": {
      "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
      "kind": "unavailable",
      "reason": "missing-derived-facts",
      "run_reference": { "…": "…" }
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Coverage reason strings are **hyphenated**: `run-not-found`,
`missing-native-payload`, `missing-derived-facts`,
`native-payload-corrupt`, `engine-mismatch`. A stale/unknown
`run_id` is different — `errors[0].code = "not-found"`, exit 2.

---

## `novetest coverage diff <baseline_run_id> <target_run_id>`

Per-file coverage delta between two runs (order = baseline → target).

```bash
NOVETEST_OUTPUT=json novetest coverage diff 01KVYP0VJH... 01KVYP0WNB...
```

`data.coverage_delta` is `kind`-discriminated:
- `kind: "delta"` keys: `baseline_run_reference`, `target_run_reference`,
  `baseline_granularity`, `target_granularity`, `summary_before`,
  `summary_after`, `files_added`, `files_removed`, `file_deltas`
  (files with no transition are omitted from `file_deltas`).
- `kind: "unavailable"` keys: `run_reference` (nullable), `reason`,
  `detail`.

Real unavailable capture (one side has no coverage facts) — exit 0:

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

---

## `novetest regression compare <baseline> <target>`

Explicit pair comparison. Order is load-bearing — `compare A B` ≠
`compare B A`. Exit 0 (incl. any `unavailable`); a fake/stale run_id is
`not-found`, exit 2.

```bash
NOVETEST_OUTPUT=json novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

### Envelope (real; `fact-set`, the bug regressed `test_subtract`; `output_diff` and most transitions trimmed)

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
      "baseline_engine_version": "9.0.3",
      "target_engine_version": "9.0.3",
      "derived_at": 1782370298563,
      "summary": {
        "added": 0,
        "fixed": 0,
        "newly_active": 0,
        "newly_skipped": 0,
        "regressed": 1,
        "removed": 0,
        "still_failing": 0,
        "still_passing": 2,
        "still_skipped": 0,
        "total_baseline_tests": 3,
        "total_target_tests": 3
      },
      "test_transitions": [
        {
          "node_id": "tests/test_arithmetic.py::test_subtract",
          "category": "regressed",
          "baseline_outcome": "passed",
          "target_outcome": "failed",
          "baseline_failure_reference": null,
          "target_failure_reference": "…/tests/test_arithmetic.py:13: assert 14 == 6\n +  where 14 = subtract(10, 4)",
          "baseline_duration_ms": 0,
          "target_duration_ms": 1,
          "schema_version": 1
        },
        "… still_passing transitions for test_add_positive, test_add_zero …"
      ],
      "output_diff": { "stdout_identical": false, "stderr_identical": true, "…": "sha256 + store-relative paths" },
      "coverage_change": null,
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

Routing facts:
- Each `test_transitions[].category` ∈ the closed 9-value taxonomy:
  `regressed`, `fixed`, `still_failing`, `still_passing`,
  `still_skipped`, `newly_skipped`, `newly_active`, `added`, `removed`.
  (There is **no** `entries[].transition`; the array is
  `test_transitions` and the key is `category`.)
- A newly-failing test is `regressed`; gate CI on `summary.regressed`.
- `coverage_change` is `null` unless **both** runs carried coverage
  facts; a plain `run` (no `--coverage`) leaves it `null`.
- The top-level `schema_version` is stripped from this block, but each
  `test_transitions[]` retains its own. The shape is explicitly **not
  frozen** — pattern-match on `kind` only.
- Unavailable shape: `kind: "unavailable"` with **two** independently
  nullable refs `baseline_run_reference`/`target_run_reference`, plus
  `reason` (hyphenated: `run-not-found`, `run-tombstoned`,
  `no-comparable-baseline`, `missing-derived-facts`, `engine-mismatch`,
  `target-mismatch`) and `detail`.

## `novetest regression latest`

`command: "regression.latest"`, same `regression_outcome` shape. It
auto-resolves the two most recent comparable runs on the active target.
Needs ≥2 comparable runs, else `kind: "unavailable"`,
`reason: "no-comparable-baseline"` (exit 0).

---

## `novetest compare <baseline> <target>` — composed view

Composed regression **and** coverage delta in one envelope. `data` has
**exactly two keys**: `regression_outcome` and `coverage_delta` (this
is what distinguishes it from `regression compare`, which has only
`regression_outcome`). Each sub-block is independently `kind`-
discriminated. Exit 0; fake run_id → `not-found`, exit 2.

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

(In the bug scenario the baseline ran without `--coverage`, so the
coverage side is `unavailable` while regression is a `fact-set`.)

---

## `novetest localization` — SBFL fault localization

```bash
NOVETEST_OUTPUT=json novetest localization <run_id> \
  [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]

NOVETEST_OUTPUT=json novetest localization latest \
  [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
```

| Flag | Default | Allowed |
|---|---|---|
| `--formula` | `ochiai` | `ochiai`, `op2`, `dstar2`, `tarantula` (lowercase; it is `dstar2`, not `dstar`) |
| `--top-n` | `10` | positive integer (hyphen in the name; no short alias) |

`localization <run_id>` is the sub-app default verb; `latest`
(`command: "localization.latest"`) is the only named sub-verb. Bad
`--formula` or `--top-n < 1` → `errors[0].code = "invalid-flag"`,
exit 2:

```json
{
  "command": "localization",
  "data": {},
  "errors": [
    {
      "code": "invalid-flag",
      "details": {},
      "message": "Invalid --formula='dstar'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

### Envelope (real; `fact-set`, the bug; entries trimmed to rank 1)

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
          "code_location": {
            "kind": "symbol",
            "file": "calc/arithmetic.py",
            "symbol": "subtract",
            "primary_line": 6,
            "line_range": [5, 6],
            "evidence_lines": [6]
          },
          "score_raw": 1.0,
          "score_normalized": 1.0,
          "formula": "ochiai",
          "alternate_scores": { "dstar2": 1.0, "op2": 1.0, "tarantula": 1.0 },
          "related_failed_tests": ["tests/test_arithmetic.py::test_subtract"],
          "evidence_citations": [ "… {kind: test_result|coverage_fact, run_reference, selector} …" ]
        },
        "… 1 more entry (test_subtract tied at rank 1; zero-score locations — add / test_add_* here — are filtered out of per-test rankings entirely) …"
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

Routing facts:
- `mode` ∈ `{sbfl_per_test, sbfl_aggregate, failure_proximity}` (auto-
  selected from coverage shape; gate on `mode`, not `formula` — in
  `failure_proximity` the `formula` is a fixed placeholder `"ochiai"`
  and `alternate_scores_available` is `[]`).
- All four formulas are always computed; `--formula` only selects which
  drives `rank`/`score_raw`. Raw/alternate scores are **formula-native
  scales — never compare across formulas**: `op2` is unbounded and can
  be negative; `dstar2` is raw and unbounded above (a location covered
  by every failing test and no passing test scores strictly above every
  finite-denominator location — `subtract`'s `1.0` here); `ochiai`/
  `tarantula` are [0,1].
- `rank` is **dense** (ties share a rank); `tied_with` holds literal
  `"entry_index_<i>"` handles. `score_normalized` is min-max over the
  full ranking before truncation.
- Unavailable block has exactly 3 keys + `kind`: `run_reference`
  (nullable), `reason`, `detail`. Localization reasons are
  **hyphenated**, like every other engine's: `no-failed-tests`,
  `no-coverage`, `no-run-evidence`, `missing-derived-facts`,
  `run-not-analyzable`. (A passing run via the explicit verb →
  `no-failed-tests`; via `latest` → `run-not-analyzable`.) Unavailable
  is `ok: true`, exit 0.

### Cache-rederive warnings

If you re-invoke against a **cached** finding with an **explicit**
`--formula`/`--top-n` that differs from the cache, the CLI invalidates
the cache, re-derives at the requested flags, and emits:

```json
{
  "warnings": [
    {
      "code": "localization-cache-rederived",
      "details": {
        "previous": { "formula": "ochiai", "top_n": 10 },
        "requested": { "formula": "op2", "top_n": 3, "formula_explicit": true, "top_n_explicit": true },
        "cache_path": ".novetest/localization/findings/run_<id>/localization_findings.json"
      }
    }
  ]
}
```

A defaulted flag never re-derives. In `failure_proximity` mode a
formula-only mismatch instead emits `localization-formula-noop-in-mode`
(details: `requested_formula`, `returned_formula`, `mode`) and does
**not** re-derive.

---

## `novetest replay <run_id>` — re-execute and classify

Re-executes a prior run under reconstructed conditions; classifies
reproducibility.

```bash
NOVETEST_OUTPUT=json novetest replay <run_id> \
  [--reruns <int>] [--timeout <seconds>]
```

| Flag | Default | Meaning |
|---|---|---|
| `--reruns` | `1` | Number of re-executions. Bump to 5+ to probe flakiness. |
| `--timeout` | `600.0` | Per-rerun ceiling (seconds). |

### Envelope (real; replaying the failing run → reproducible)

```json
{
  "command": "replay",
  "data": {
    "original_run_reference": {
      "created_at": 1782370296489,
      "run_id": "01KVYRRRN9FWVNQWVHNE1QHAQ4",
      "schema_version": 1
    },
    "replay_outcome": {
      "kind": "replay-result",
      "classification": "reproducible",
      "reruns_total": 1,
      "reruns_failed": 0,
      "test_id": null,
      "reason": null,
      "replayed_run_reference": { "run_id": "01KVYRRVYB6K156ABEDFQTMQCG", "…": "…" },
      "per_rerun_outcomes": ["failed"],
      "consistency_summary": {
        "original_passed": 0,
        "original_failed": 1,
        "replay_passed": 0,
        "replay_failed": 1,
        "replay_errored": 0
      },
      "attempted_at": 1782370299982
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Routing facts:
- `data` has two keys: `original_run_reference` and `replay_outcome`.
- `classification` ∈ `{reproducible, inconsistent, unable_to_replay}`.
  Strict policy: one differing rerun → `inconsistent` (no majority
  vote). `unable_to_replay` is a valid success (exit 0, `ok: true`),
  not an error.
- `per_rerun_outcomes` length == `--reruns`; `consistency_summary`
  counts **runs**, not individual tests.
- Replay **persists each rerun as a new Memory Entry** (it shows up in
  `memory list`). `replayed_run_reference` is the first such rerun.
- `test` never runs replay (`stage_eligibility.replay` is always
  `not_run`); replay is the only producer of replay facts.
- Exit: `ReplayResult` (incl. `unable_to_replay`) → 0; fake run_id →
  `not-found`, 2; `engine-not-ready`/`target-missing` →
  `replay-<reason>`, 4; `tombstoned-original` /
  `context-reconstruction-failed` / `missing-derived-facts` →
  `kind: "unavailable"`, 0.

---

## `novetest memory` — history management

### `novetest memory list`

```bash
NOVETEST_OUTPUT=json novetest memory list
```

`data` has exactly `count` (int) and `entries` (MemoryEntry dicts,
newest-first, tombstones included). There is **no** `total_count` /
`tombstoned_count`. Each entry's run details live under `run_record`
(not at the entry top level).

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

### `novetest memory show <run_id>`

```bash
NOVETEST_OUTPUT=json novetest memory show 01KVYP0WNB8X47ZPN85ZAYBKSN
```

`data = {"memory_entry": <full MemoryEntry>}` — the same entry shape as
`memory list`, including the full `run_record` (`artifact_paths`,
`summary_counts`, `test_results`, …). Works for tombstoned runs.
Unknown run_id → `not-found`, exit 2.

### `novetest memory delete <run_id>`

Tombstones (POSIX-atomic rename) — does **not** hard-delete. Returns the
entry with `tombstoned_at` now a timestamp and `run_record.status`
rewritten to `"tombstoned"`. Re-deleting an already-tombstoned run is a
no-op success (exit 0).

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
      "…": "has_* flags …"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

The entry stays visible to `memory list` / `memory show`. Hard wipe is
only `reset --confirm`.

---

## `novetest reset [--confirm]` — destructive

```bash
NOVETEST_OUTPUT=json novetest reset --confirm
```

Without `--confirm`: `errors[0].code = "confirm-required"`, exit 2,
nothing mutated. With `--confirm`: wipes the entire `.novetest/` tree
and re-inits. `command: "reset"`, exit 0:

```json
{
  "command": "reset",
  "data": {
    "engine_readiness": {
      "ecosystem": null,
      "engine": null,
      "engine_version": null,
      "evidence": [],
      "issues": ["no supported (ecosystem, native engine) pair detected in workspace"],
      "state": "engine-missing"
    },
    "initialized_at": 1782368398311,
    "items_removed": {
      "coverage_facts": 0,
      "localization_findings": 0,
      "regression_pairs": 0,
      "replay_results": 0,
      "runs": 0,
      "tombstones": 0
    },
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

`items_removed` always has exactly these six keys. A corrupt store is
refused with `store-corrupt`, exit 5 (not auto-wiped); an OSError during
wipe → `store-wipe-failed`, exit 5.

---

## `novetest licenses [--full]`

```bash
NOVETEST_OUTPUT=json novetest licenses
NOVETEST_OUTPUT=json novetest licenses --full
```

### Envelope (real summary)

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

`data.licenses[].source` ∈ `{runtime, vendored,
install-time-bootstrap}`. With `--full`, `data.notices_text` is added
(the verbatim `NOTICES.md` body as a single string) — use it for
SBOM / audit. (The keys are `licenses`, `notices_reference`,
`summary`; there is no `schemaVersion` or `attribution_path`.)

---

## Output mode override

```bash
novetest --output {json|text|ndjson} <verb>
NOVETEST_OUTPUT={json|text|ndjson} novetest <verb>
```

| Mode | Byte shape |
|---|---|
| `json` | Pretty-printed envelope (`indent=2`, sorted keys, trailing newline). |
| `ndjson` | Single compact line (no internal newlines, trailing `\n`). |
| `text` | Human-readable projection (different bytes from the envelope). |

Precedence: `--output` > `NOVETEST_OUTPUT` > TTY auto-detect. The
`--output` flag is **global and may appear anywhere in argv** (it is
stripped before the verb is dispatched). There is no `--text` / `--json`
flag (`--text` is parsed as an unknown command).
Default is JSON when stdout is not a TTY, so a piped/CI invocation
already gets JSON.

---

## What this page deliberately does NOT cover

- Engine-side flag pass-through (pytest nodeid filtering, jest regex, cargo nextest filter, …) — those live in the native engine's docs. Nove Test forwards targets verbatim.
- `--workspace <path>` override — rarely needed; `cd` first is the recommended pattern.
- Replay classification internals — `design/workflows/replay.md`.
- SBFL math — `design/implementation-plan/localization-strategy.md`.
- Recommendation synthesis taxonomy — `design/implementation-plan/recommendation-synthesis.md`.

The design docs are the source of truth for those. This page is for
calling the verbs.
