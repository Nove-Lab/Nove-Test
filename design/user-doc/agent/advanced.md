# Advanced verbs (Agent)

Every non-happy-path verb with its envelope shape. The happy path
(`--version`, `--help`, `init`, `test`, `status`, `inspect`) is
documented in [quick-start.md](./quick-start.md) and
[after-test.md](./after-test.md); this page covers the other 10
verbs.

For every verb below: signature, default JSON envelope shape,
non-obvious behavior an agent needs to know.

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
| `<target>` | Test target expression. Same shape as `novetest test`. |
| `--coverage` / `-c` | Also derive + persist Coverage Facts. Without this, only the Run Record lands. |

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "run",
  "ok": true,
  "data": {
    "memory_entry": {
      "schema_version": 1,
      "entry_id": "...",
      "run_record": {
        "run_reference": { "run_id": "01HX...", "created_at": ... },
        "status": "passed",
        "engine_name": "pytest",
        "ecosystem": "python",
        "target_expression": "",
        "summary_counts": { "passed": 3, "failed": 0, "skipped": 0, "total": 3 },
        "test_results": [ /* per-test entries */ ],
        "started_at": ..., "completed_at": ...,
        "duration_seconds": 0.23
      },
      "stored_at": ...,
      "has_coverage_facts": true,
      "has_regression_facts": false,
      "has_localization_findings": false,
      "has_replay_result": false,
      "tombstoned_at": null
    },
    "coverage_outcome": { "kind": "fact-set", /* ... */ }
  },
  "errors": [],
  "warnings": []
}
```

`coverage_outcome` is present only when `--coverage` was passed.

Exit codes: 0 (passed), 3 (tests failed), 4 (engine missing),
2 (uninitialized / bad flag), 5 (store corrupt).

---

## `novetest coverage show <run_id>`

Read persisted Coverage Facts. Cache-read only; never derives.

```bash
NOVETEST_OUTPUT=json novetest coverage show 01HX...
```

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "coverage.show",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX...", "created_at": ... },
    "coverage_outcome": {
      "kind": "fact-set",
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
      },
      "files": [ /* per-file entries */ ]
    }
  },
  "errors": [],
  "warnings": []
}
```

Error path: `errors[0].code = "not-found"` (exit 2) if `run_id` does
not exist. `coverage_outcome.kind = "unavailable"` (exit 0) if the
run exists but never had coverage facts derived.

---

## `novetest coverage diff <baseline_run_id> <target_run_id>`

Per-file coverage delta between two runs.

```bash
NOVETEST_OUTPUT=json novetest coverage diff 01HX... 01HY...
```

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "coverage.diff",
  "ok": true,
  "data": {
    "baseline_reference": { "run_id": "01HX...", ... },
    "target_reference": { "run_id": "01HY...", ... },
    "coverage_delta": {
      "kind": "delta",
      "summary_before": { "percent_covered": 85.4, ... },
      "summary_after": { "percent_covered": 87.1, ... },
      "files_added": [ "src/new_feature.py" ],
      "files_removed": [],
      "file_deltas": [
        {
          "file": "src/math_utils.py",
          "percent_before": 82.0,
          "percent_after": 89.0,
          "lines_added_covered": 7,
          "lines_added_uncovered": 0
        }
      ]
    }
  },
  "errors": [],
  "warnings": []
}
```

`coverage_delta.kind = "unavailable"` (with `reason`) when either side
lacks coverage facts.

---

## `novetest regression compare <baseline> <target>`

Explicit pair comparison.

```bash
NOVETEST_OUTPUT=json novetest regression compare 01HX... 01HY...
```

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "regression.compare",
  "ok": true,
  "data": {
    "regression_outcome": {
      "kind": "fact-set",
      "baseline_reference": { "run_id": "01HX...", ... },
      "target_reference": { "run_id": "01HY...", ... },
      "summary": {
        "regressed": 2,
        "fixed": 1,
        "still_failing": 0,
        "still_passing": 25
      },
      "entries": [
        {
          "test_id": "tests/test_math_utils.py::test_add_positive",
          "transition": "passed_to_failed",
          "baseline_outcome": "passed",
          "target_outcome": "failed"
        }
      ]
    }
  },
  "errors": [],
  "warnings": []
}
```

`entries[].transition` ∈ `{passed_to_failed, failed_to_passed, still_failing, still_passing}`.

## `novetest regression latest`

Same envelope shape, but the verb resolves the latest comparable pair
on the active target automatically.

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
| `--formula` | `ochiai` | `ochiai`, `op2`, `dstar2`, `tarantula` |
| `--top-n` | `10` | positive integer |

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "localization",
  "ok": true,
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "run_reference": { "run_id": "01HX...", ... },
      "engine_name": "pytest",
      "ecosystem": "python",
      "mode": "sbfl_per_test",
      "confidence": "high",
      "formula": "ochiai",
      "alternate_scores_available": ["tarantula", "dstar2"],
      "top_n": 10,
      "entries": [
        {
          "rank": 1,
          "code_location": {
            "file": "my_module/math_utils.py",
            "symbol": "add",
            "primary_line": 7,
            "line_range": [7, 9]
          },
          "score_raw": 1.0,
          "score_normalized": 1.0,
          "evidence_citations": [ /* test_result citations */ ]
        }
      ],
      "derived_at": 1717951375000
    }
  },
  "errors": [],
  "warnings": []
}
```

`localization_outcome.mode` ∈ `{sbfl_per_test, sbfl_aggregate, failure_proximity}`.

Cache invalidation: if you re-invoke with a different `--formula` or
`--top-n` than what was cached, the CLI rewrites the cache and emits a
warning:

```json
{"warnings": [{"code": "localization-cache-rederived", "message": "..."}]}
```

If you pass `--formula` in `failure_proximity` mode (where formula is
irrelevant), the warning is `localization-formula-noop-in-mode`.

---

## `novetest replay <run_id>`

Re-execute a prior run; classify reproducibility.

```bash
NOVETEST_OUTPUT=json novetest replay <run_id> \
  [--reruns <int>] [--timeout <seconds>]
```

| Flag | Default | Meaning |
|---|---|---|
| `--reruns` | `1` | Number of re-executions. |
| `--timeout` | `600.0` | Per-rerun ceiling (seconds). |

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "replay",
  "ok": true,
  "data": {
    "replay_outcome": {
      "kind": "replay-result",
      "run_reference": { "run_id": "01HX...", ... },
      "classification": "reproducible",
      "reruns_total": 5,
      "reruns_failed": 0,
      "per_rerun_outcomes": [ /* per-rerun classifications */ ]
    }
  },
  "errors": [],
  "warnings": []
}
```

`replay_outcome.classification` ∈ `{reproducible, inconsistent, unable_to_replay}`.

When `unable_to_replay`, `replay_outcome.reason` carries the why (e.g.
`engine-unavailable`, `replay-timeout`, `host-mismatch`).

---

## `novetest compare <baseline> <target>`

Composed regression + coverage delta in one envelope. Cheaper than two
separate calls because memory entries are read once.

```bash
NOVETEST_OUTPUT=json novetest compare 01HX... 01HY...
```

### Envelope

```json
{
  "schema": "novetest/v1",
  "command": "compare",
  "ok": true,
  "data": {
    "baseline_reference": { "run_id": "01HX...", ... },
    "target_reference": { "run_id": "01HY...", ... },
    "regression_outcome": { "kind": "fact-set", /* ... */ },
    "coverage_delta": { "kind": "delta", /* ... */ }
  },
  "errors": [],
  "warnings": []
}
```

Either sub-block can be `kind = "unavailable"` independently.

---

## `novetest memory` — history management

### `novetest memory list`

```bash
NOVETEST_OUTPUT=json novetest memory list
```

```json
{
  "schema": "novetest/v1",
  "command": "memory.list",
  "ok": true,
  "data": {
    "entries": [
      {
        "run_reference": { "run_id": "01HZ...", "created_at": ... },
        "status": "passed",
        "engine_name": "pytest",
        "ecosystem": "python",
        "tombstoned_at": null
      },
      {
        "run_reference": { "run_id": "01HX...", "created_at": ... },
        "status": "passed",
        "engine_name": "pytest",
        "ecosystem": "python",
        "tombstoned_at": 1717951400000
      }
    ],
    "total_count": 12,
    "tombstoned_count": 1
  },
  "errors": [],
  "warnings": []
}
```

Newest first. Tombstoned entries are included with a non-null
`tombstoned_at`.

### `novetest memory show <run_id>`

```bash
NOVETEST_OUTPUT=json novetest memory show 01HX...
```

Returns the raw Memory Entry. Useful for audit.

### `novetest memory delete <run_id>`

```bash
NOVETEST_OUTPUT=json novetest memory delete 01HX...
```

```json
{
  "schema": "novetest/v1",
  "command": "memory.delete",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX...", ... },
    "tombstoned_at": 1717952000000
  },
  "errors": [],
  "warnings": []
}
```

Atomic POSIX rename; recoverable until garbage collection (post-MVP).

---

## `novetest licenses [--full]`

```bash
NOVETEST_OUTPUT=json novetest licenses
NOVETEST_OUTPUT=json novetest licenses --full
```

### Envelope (summary)

```json
{
  "schema": "novetest/v1",
  "command": "licenses",
  "ok": true,
  "data": {
    "schemaVersion": 1,
    "summary": "5 third-party components: 2 runtime, 1 vendored, 2 install-time-bootstrap",
    "licenses": [
      {
        "package": "cyclopts",
        "version": "3.5.0",
        "license": "MIT",
        "source": "runtime",
        "project_url": "https://github.com/BrianPugh/cyclopts"
      },
      {
        "package": "numpy",
        "version": "2.0.0",
        "license": "BSD-3-Clause",
        "source": "runtime",
        "project_url": "https://numpy.org/"
      },
      {
        "package": "junit-platform-console-standalone",
        "version": "1.11.4",
        "license": "EPL-2.0",
        "source": "vendored",
        "project_url": "https://junit.org/junit5/"
      },
      {
        "package": "PyApp",
        "version": "0.22.0",
        "license": "MIT",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/ofek/pyapp"
      },
      {
        "package": "python-build-standalone",
        "version": "20240814",
        "license": "MIT-CMU",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/indygreg/python-build-standalone"
      }
    ],
    "attribution_path": "*.dist-info/licenses/NOTICES.md"
  },
  "errors": [],
  "warnings": []
}
```

With `--full`, `data.notices_text` is added (the verbatim
`NOTICES.md` body, as a single string). Use this when you need full
license texts for SBOM / audit.

`data.licenses[].source` ∈ `{runtime, vendored, install-time-bootstrap}`.

---

## Output mode override

```bash
novetest <verb> --output {json|text|ndjson}
NOVETEST_OUTPUT={json|text|ndjson} novetest <verb>
```

| Mode | Byte shape |
|---|---|
| `json` | Pretty-printed envelope (`indent=2`, trailing newline). |
| `ndjson` | Single line (`indent=None`, no internal newlines, trailing `\n`). |
| `text` | Human-readable projection (different bytes from the envelope). |

JSON / NDJSON byte shapes are **CI-snapshot-pinned**. Drift fails the
release pipeline. You can rely on byte-identical output for the same
input — useful for memoization, content-addressed caches, and
contract tests in your agent.

---

## What this page deliberately does NOT cover

- Engine-side flag pass-through (pytest nodeid filtering, jest regex, cargo nextest filter, …) — those live in the native engine's docs. Nove Test forwards targets verbatim.
- `--workspace <path>` override — rarely needed; `cd` first is the recommended pattern.
- Replay classification internals — `design/workflows/replay.md`.
- SBFL math — `design/implementation-plan/localization-strategy.md`.
- Recommendation synthesis taxonomy — `design/implementation-plan/recommendation-synthesis.md`.

The design docs are the source of truth for those. This page is for
calling the verbs.
