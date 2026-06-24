# Advanced Usage

The 4-verb happy path (`--version`, `--help`, `init`, `test`) plus
the two follow-ups (`status`, `inspect`) cover ~90% of day-to-day
novetest use. This page documents the **other ten verbs** — when to
reach for them, the signature, and what they return.

Verbs covered here:

- **Run engine raw** — `novetest run`
- **Coverage engine** — `novetest coverage show`,
  `novetest coverage diff`
- **Regression engine** — `novetest regression compare`,
  `novetest regression latest`
- **Localization engine** — `novetest localization`,
  `novetest localization latest`
- **Replay engine** — `novetest replay`
- **Composed view** — `novetest compare`
- **Memory / history management** — `novetest memory list`,
  `novetest memory show`, `novetest memory delete`
- **Attribution** — `novetest licenses [--full]`

---

## `novetest run` — run tests without orchestration

```bash
novetest run [<target>] [--coverage]
```

What it does: invokes the native engine, persists a Run Record.
That's it. Does **not** auto-derive regression, localization, or
recommendations.

Use when:

- You want fine-grained control over the pipeline (e.g. CI
  splitting "run" from "analyze").
- You're debugging an adapter and want to see the raw run result
  without orchestration around it.
- You want to skip coverage (it's not collected unless you pass
  `--coverage`).

::: tabs
@tab For human

Text-mode output (all-pass with `--coverage`):

```
✓ passed · 3/3 · run_id=01HX...
  coverage: ✓ per-test · 10/11 statements (86.7%)
```

(The `coverage:` line only appears with `--coverage`.)

For a failing run you'll see a failed tests block:

```
✗ failed · 2/3 · run_id=01HX...
  failed tests:
    ✗ tests/test_math_utils.py::test_add_positive
    ✗ tests/test_math_utils.py::test_subtract
  coverage: ✓ per-test · 8/11 statements (72.7%)
```

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest run [<target>] [--coverage] [-c]
```

| Flag | Effect |
|---|---|
| `<target>` | Test target expression. Same shape as `novetest test`. |
| `--coverage` / `-c` | Also derive + persist Coverage Facts. Without this, only the Run Record lands. |

Envelope:

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
        "run_reference": { "run_id": "01HX...", "created_at": 0 },
        "status": "passed",
        "engine_name": "pytest",
        "ecosystem": "python",
        "target_expression": "",
        "summary_counts": { "passed": 3, "failed": 0, "skipped": 0, "total": 3 },
        "test_results": [ /* per-test entries */ ],
        "started_at": 0, "completed_at": 0,
        "duration_seconds": 0.23
      },
      "stored_at": 0,
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

Exit codes: 0 (passed), 3 (tests failed), 4 (engine missing), 2
(uninitialized / bad flag), 5 (store corrupt).

:::

---

## `novetest coverage show <run_id>` — read persisted coverage

Cache-read only; never re-derives.

::: tabs
@tab For human

```bash
novetest coverage show 01HX...
```

Text mode (illustrative):

```
✓ per-test · 245/287 statements (85.4%) · branches 59/68
  files: 5
  + 4 files at 100%
  − 1 file with 42 missing statements
```

Use when you want to re-query a known run without re-running it.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest coverage show 01HX...
```

```json
{
  "schema": "novetest/v1",
  "command": "coverage.show",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX...", "created_at": 0 },
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

Error path: `errors[0].code = "not-found"` (exit 2) if `run_id`
does not exist. `coverage_outcome.kind = "unavailable"` (exit 0)
if the run exists but never had coverage facts derived.

:::

---

## `novetest coverage diff <baseline> <target>` — per-file delta

::: tabs
@tab For human

```bash
novetest coverage diff 01HX... 01HY...
```

Text mode (illustrative):

```
85.4% → 87.1% (Δ +1.7%) · files +1/-0/~2
  + src/new_feature.py (87%)
  ~ src/math_utils.py: 82% → 89% (Δ +7%)
  ~ src/string_utils.py: 90% → 91% (Δ +1%)
```

Use for PR review automation, "did I cover the new code?" probes.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest coverage diff 01HX... 01HY...
```

```json
{
  "schema": "novetest/v1",
  "command": "coverage.diff",
  "ok": true,
  "data": {
    "baseline_reference": { "run_id": "01HX...", "created_at": 0 },
    "target_reference": { "run_id": "01HY...", "created_at": 0 },
    "coverage_delta": {
      "kind": "delta",
      "summary_before": { "percent_covered": 85.4 },
      "summary_after": { "percent_covered": 87.1 },
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

`coverage_delta.kind = "unavailable"` (with `reason`) when either
side lacks coverage facts.

:::

---

## `novetest regression compare <baseline> <target>`

Explicit pair comparison. Use when you want a specific baseline
(overriding the auto-latest heuristic).

::: tabs
@tab For human

```bash
novetest regression compare 01HX... 01HY...
```

Text mode (clean):

```
✓ clean · regressed=0 fixed=0 still_failing=0
```

Text mode (regressions present):

```
✗ regressions · regressed=2 fixed=1 still_failing=0
  regressed:
    ✗ tests/test_math_utils.py::test_add_positive
    ✗ tests/test_math_utils.py::test_subtract
  fixed:
    ✓ tests/test_string.py::test_strip
```

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest regression compare 01HX... 01HY...
```

```json
{
  "schema": "novetest/v1",
  "command": "regression.compare",
  "ok": true,
  "data": {
    "regression_outcome": {
      "kind": "fact-set",
      "baseline_reference": { "run_id": "01HX...", "created_at": 0 },
      "target_reference": { "run_id": "01HY...", "created_at": 0 },
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

`entries[].transition` ∈ `{passed_to_failed, failed_to_passed,
still_failing, still_passing}`.

:::

## `novetest regression latest`

Re-derive (or read from cache) the regression facts for the latest
comparable pair on the active target.

```bash
novetest regression latest
```

Same shape as `regression compare`. `novetest test` already runs
this for you; the standalone verb is mainly for diagnostic
re-querying.

---

## `novetest localization` — SBFL fault localization

```bash
novetest localization <run_id> [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
novetest localization latest
```

| Flag | Default | Allowed |
|---|---|---|
| `--formula` | `ochiai` | `ochiai`, `op2`, `dstar2`, `tarantula` |
| `--top-n` | `10` | positive integer |

Re-rank suspicious code locations for one run via SBFL.

::: tabs
@tab For human

Text-mode output:

```
sbfl_per_test · ochiai · 6 entries · confidence=high · run_id=01HX...
  1. add@7 in my_module/math_utils.py (1.000)
  2. _validate_input@15 in my_module/math_utils.py (0.667)
  3. subtract@11 in my_module/math_utils.py (0.408)
  ...
```

Each line: `<rank>. <symbol>@<line> in <file> (<normalized
score>)`. Top entries are most suspicious. With no failing tests,
the entries list is empty and you'll see:

```
— unavailable (no_failed_tests)
```

`localization latest` is the same verb applied to the latest
analyzable run on the active target.

**Tip on switching formulas.** If you re-invoke `localization`
with a different `--formula` than what was cached, novetest
rewrites the cache and emits a `⚠ localization-cache-rederived`
warning. This is deliberate; ignore it unless you need to know.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest localization <run_id> \
  [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]

NOVETEST_OUTPUT=json novetest localization latest \
  [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
```

Envelope:

```json
{
  "schema": "novetest/v1",
  "command": "localization",
  "ok": true,
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "run_reference": { "run_id": "01HX...", "created_at": 0 },
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

`localization_outcome.mode` ∈ `{sbfl_per_test, sbfl_aggregate,
failure_proximity}`.

Cache invalidation: if you re-invoke with a different `--formula`
or `--top-n` than what was cached, the CLI rewrites the cache and
emits a warning:

```json
{"warnings": [{"code": "localization-cache-rederived", "message": "..."}]}
```

If you pass `--formula` in `failure_proximity` mode (where formula
is irrelevant), the warning is `localization-formula-noop-in-mode`.

:::

---

## `novetest replay <run_id>` — re-execute and classify

```bash
novetest replay <run_id> [--reruns <int>] [--timeout <seconds>]
```

| Flag | Default | Meaning |
|---|---|---|
| `--reruns` | `1` | How many times to re-execute. Bump to 5 or 10 to probe flakiness. |
| `--timeout` | `600.0` | Per-rerun ceiling in seconds. |

Re-executes a prior run under reconstructed conditions; classifies
reproducibility as `reproducible` / `inconsistent` /
`unable_to_replay`.

::: tabs
@tab For human

Text-mode output:

```
✓ reproducible · 5/5         # all reruns matched the original
```

```
✗ inconsistent · 2/5 failed  # the test result is flaky
```

```
? unable_to_replay (engine-unavailable)  # the host couldn't replay
```

Use for flakiness investigation. `novetest test` deliberately does
NOT auto-invoke replay (it would multiply wall-clock time by
`--reruns`).

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest replay <run_id> \
  [--reruns <int>] [--timeout <seconds>]
```

```json
{
  "schema": "novetest/v1",
  "command": "replay",
  "ok": true,
  "data": {
    "replay_outcome": {
      "kind": "replay-result",
      "run_reference": { "run_id": "01HX...", "created_at": 0 },
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

`replay_outcome.classification` ∈ `{reproducible, inconsistent,
unable_to_replay}`.

When `unable_to_replay`, `replay_outcome.reason` carries the why
(e.g. `engine-unavailable`, `replay-timeout`, `host-mismatch`).

:::

---

## `novetest compare <baseline> <target>` — composed view

Composed regression + coverage delta in a single envelope. Cheaper
than two separate calls because memory entries are read once.

::: tabs
@tab For human

```bash
novetest compare 01HX... 01HY...
```

Text mode (illustrative):

```
✓ 01HX... → 01HY...

  regression  ✓ clean · regressed=0 fixed=0 still_failing=0
  coverage    85.4% → 87.1% (Δ +1.7%) · files +1/-0/~2
```

Useful when reviewing one specific pair end-to-end.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest compare 01HX... 01HY...
```

```json
{
  "schema": "novetest/v1",
  "command": "compare",
  "ok": true,
  "data": {
    "baseline_reference": { "run_id": "01HX...", "created_at": 0 },
    "target_reference": { "run_id": "01HY...", "created_at": 0 },
    "regression_outcome": { "kind": "fact-set", /* ... */ },
    "coverage_delta": { "kind": "delta", /* ... */ }
  },
  "errors": [],
  "warnings": []
}
```

Either sub-block can be `kind = "unavailable"` independently.

:::

---

## `novetest memory` — history management

### `novetest memory list`

List Run History newest-first (tombstones included with their
tombstoned-at marker).

::: tabs
@tab For human

```bash
novetest memory list
```

Text mode (illustrative):

```
12 runs (1 tombstoned)

  01HZ... · passed · 2026-06-23T10:21:14Z · pytest (python)
  01HY... · failed · 2026-06-22T14:11:02Z · pytest (python)
  ...
  01HX... · passed · 2026-06-09T08:33:55Z · pytest (python) [tombstoned 2026-06-22]
```

@tab For agent

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
        "run_reference": { "run_id": "01HZ...", "created_at": 0 },
        "status": "passed",
        "engine_name": "pytest",
        "ecosystem": "python",
        "tombstoned_at": null
      },
      {
        "run_reference": { "run_id": "01HX...", "created_at": 0 },
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

:::

### `novetest memory show <run_id>`

Show the raw Memory Entry for one run (live or tombstoned).

```bash
novetest memory show 01HX...
```

::: tabs
@tab For human

Text-mode is a verbose pretty-print of the Memory Entry's fields
(run_id, stored_at, status flags, tombstone marker if present).

@tab For agent

Returns the raw Memory Entry envelope. Useful for audit.

:::

### `novetest memory delete <run_id>`

Tombstone a Memory Entry (atomic POSIX rename; recoverable until
garbage collection).

::: tabs
@tab For human

```bash
novetest memory delete 01HX...
```

Text-mode output:

```
✓ tombstoned 01HX... at 2026-06-23T10:30:00Z
```

This does NOT delete the underlying JSON files; it marks them as
tombstoned. Subsequent `memory list` calls show the tombstone
marker; `inspect` on a tombstoned ID returns the entry with
`tombstoned_at` set. Garbage collection of tombstones is post-MVP.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest memory delete 01HX...
```

```json
{
  "schema": "novetest/v1",
  "command": "memory.delete",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX...", "created_at": 0 },
    "tombstoned_at": 1717952000000
  },
  "errors": [],
  "warnings": []
}
```

Atomic POSIX rename; recoverable until garbage collection
(post-MVP).

:::

---

## `novetest licenses [--full]`

Lists every third-party component novetest redistributes or links
to, with SPDX license tag. Required for legal / audit / SBOM
workflows.

::: tabs
@tab For human

```bash
novetest licenses          # summary list
novetest licenses --full   # summary + verbatim NOTICES.md text
```

Text-mode output (without `--full`):

```
licenses (5 third-party components)

  runtime dependencies
    cyclopts (3.5.0)                            MIT
    numpy (2.0.0)                               BSD-3-Clause

  vendored binary
    junit-platform-console-standalone (1.11.4)  EPL-2.0

  install-time bootstrap
    PyApp (0.22.0)                              MIT
    python-build-standalone (20240814)          MIT-CMU

  full verbatim license texts: novetest licenses --full
  attribution file (in wheel): *.dist-info/licenses/NOTICES.md
```

With `--full`, the verbatim `NOTICES.md` text is appended after a
divider. Use this when you need the actual license text bodies.

@tab For agent

```bash
NOVETEST_OUTPUT=json novetest licenses
NOVETEST_OUTPUT=json novetest licenses --full
```

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

`data.licenses[].source` ∈ `{runtime, vendored,
install-time-bootstrap}`.

:::

---

## Output mode override (any verb)

```bash
novetest <verb> --output {json|text|ndjson}
# or
NOVETEST_OUTPUT={json|text|ndjson} novetest <verb>
```

::: tabs
@tab For human

| Mode | Output |
|---|---|
| `text` | Human-readable summary (the default on a TTY). What this entire manual shows. |
| `json` | Pretty-printed `novetest/v1` envelope (`indent=2`). The default when piped. |
| `ndjson` | Same envelope on one line (no indent, trailing newline). For log streams. |

Precedence (canonical Unix): **explicit `--output` >
`NOVETEST_OUTPUT` env > TTY auto-detect**.

If you want to see what your agent counterpart sees:

```bash
NOVETEST_OUTPUT=json novetest test | jq .
```

@tab For agent

| Mode | Byte shape |
|---|---|
| `json` | Pretty-printed envelope (`indent=2`, trailing newline). |
| `ndjson` | Single line (`indent=None`, no internal newlines, trailing `\n`). |
| `text` | Human-readable projection (different bytes from the envelope). |

JSON / NDJSON byte shapes are **CI-snapshot-pinned**. Drift fails
the release pipeline. You can rely on byte-identical output for the
same input — useful for memoization, content-addressed caches, and
contract tests in your agent.

:::

---

## What this page deliberately does NOT cover

- Engine-side flag pass-through (pytest nodeid filtering, jest
  regex, cargo nextest filter, ...) — those live in the native
  engine's docs. novetest forwards targets verbatim.
- `--workspace <path>` override — rarely needed; `cd` first is the
  recommended pattern.
- The full SBFL math behind each formula → public design docs in
  the repository.
- The recommendation synthesis taxonomy beyond what's in
  [Understanding Results](./understanding-results.md) → public
  design docs.
- Adapter internals (how each engine is invoked, normalization
  rules) → public design docs.
- Replay classification rules (what makes a result `inconsistent`
  vs `unable_to_replay`) → public design docs.

The design docs are the source of truth for those. This page is
for calling the verbs.

---

## What to read next

- An envelope came back unexpected, or a verb errored →
  [Troubleshooting](./troubleshooting.md).
- Back up one level →
  [Understanding Results](./understanding-results.md).
