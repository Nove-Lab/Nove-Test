# Advanced verbs (Human)

The 4-verb happy path (`--version`, `--help`, `init`, `test`) plus the
two follow-ups (`status`, `inspect`) cover ~90% of day-to-day Nove
Test use. This page documents the **other ten verbs** — when to reach
for them, what they print in text mode, and the one-line summary of
what they do.

Verbs covered here:

- **Run engine raw** — `novetest run`
- **Coverage engine** — `novetest coverage show`, `novetest coverage diff`
- **Regression engine** — `novetest regression compare`, `novetest regression latest`
- **Localization engine** — `novetest localization`, `novetest localization latest`
- **Replay engine** — `novetest replay`
- **Composed view** — `novetest compare`
- **Memory / history management** — `novetest memory list`, `novetest memory show`, `novetest memory delete`
- **Attribution** — `novetest licenses [--full]`

For the agent set's full envelope shapes, see
[agent/advanced.md](../agent/advanced.md).

---

## `novetest run` — run tests without orchestration

```bash
novetest run [<target>] [--coverage]
```

What it does: invokes the native engine, persists a Run Record. That's
it. Does **not** auto-derive regression, localization, or
recommendations.

Use when:
- You want fine-grained control over the pipeline (e.g. CI splitting "run" from "analyze").
- You're debugging an adapter and want to see the raw run result without orchestration around it.
- You want to skip coverage (it's not collected unless you pass `--coverage`).

Text-mode output:

```
✓ passed · 3/3 · run_id=01HX...
  coverage: ✓ per-test · 10/11 statements (86.7%)
```

(The `coverage:` line only appears with `--coverage`.)

For an all-pass + cover run, the failed-tests list is empty so only
the two header lines print. For a failing run you'll see a failed
tests block:

```
✗ failed · 2/3 · run_id=01HX...
  failed tests:
    ✗ tests/test_math_utils.py::test_add_positive
    ✗ tests/test_math_utils.py::test_subtract
  coverage: ✓ per-test · 8/11 statements (72.7%)
```

---

## `novetest coverage` — coverage engine

### `novetest coverage show <run_id>`

Read persisted Coverage Facts for one run (cache-read only; never
re-derives).

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

### `novetest coverage diff <baseline_run_id> <target_run_id>`

Per-file coverage delta between two runs.

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

---

## `novetest regression` — regression engine

### `novetest regression compare <baseline_run_id> <target_run_id>`

Explicit pair comparison. Use when you want a specific baseline
(overriding the auto-latest heuristic).

```bash
novetest regression compare 01HX... 01HY...
```

Text mode (illustrative — clean):

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

### `novetest regression latest`

Re-derive (or read from cache) the regression facts for the latest
comparable pair on the active target.

```bash
novetest regression latest
```

Same output shape as `compare`. `novetest test` already runs this for
you; the standalone verb is mainly for diagnostic re-querying.

---

## `novetest localization` — SBFL fault localization

```bash
novetest localization <run_id> [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
novetest localization latest
```

Re-rank suspicious code locations for one run via SBFL.

| Flag | Default | Meaning |
|---|---|---|
| `--formula` | `ochiai` | SBFL scoring formula. `ochiai` and `op2` are the strongest defaults. |
| `--top-n` | `10` | Cap the ranked list. Pass a larger number for deeper analysis. |

Text-mode output:

```
sbfl_per_test · ochiai · 6 entries · confidence=high · run_id=01HX...
  1. add@7 in my_module/math_utils.py (1.000)
  2. _validate_input@15 in my_module/math_utils.py (0.667)
  3. subtract@11 in my_module/math_utils.py (0.408)
  ...
```

Each line: `<rank>. <symbol>@<line> in <file> (<normalized score>)`.
Top entries are most suspicious. With no failing tests, the entries
list is empty and you'll see:

```
— unavailable (no_failed_tests)
```

`localization latest` is the same verb applied to the latest
analyzable run on the active target.

**Tip on switching formulas.** If you re-invoke `localization` with a
different `--formula` than what was cached, Nove Test rewrites the
cache and emits a `⚠ localization-cache-rederived` warning. This is
deliberate; ignore it unless you need to know.

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
reproducibility as `reproducible` / `inconsistent` / `unable_to_replay`.

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

---

## `novetest compare <baseline_run_id> <target_run_id>`

Composed regression + coverage delta in a single envelope.

```bash
novetest compare 01HX... 01HY...
```

Useful when reviewing one specific pair end-to-end. Cheaper than
calling `regression compare` and `coverage diff` separately because
the underlying memory entries are read once.

Text mode (illustrative):

```
✓ 01HX... → 01HY...

  regression  ✓ clean · regressed=0 fixed=0 still_failing=0
  coverage    85.4% → 87.1% (Δ +1.7%) · files +1/-0/~2
```

---

## `novetest memory` — history management

### `novetest memory list`

```bash
novetest memory list
```

List Run History newest-first (tombstones included with their
tombstoned-at marker).

Text mode (illustrative):

```
12 runs (1 tombstoned)

  01HZ... · passed · 2026-06-23T10:21:14Z · pytest (python)
  01HY... · failed · 2026-06-22T14:11:02Z · pytest (python)
  ...
  01HX... · passed · 2026-06-09T08:33:55Z · pytest (python) [tombstoned 2026-06-22]
```

### `novetest memory show <run_id>`

Show the raw Memory Entry for one run (live or tombstoned).

```bash
novetest memory show 01HX...
```

Text-mode is a verbose pretty-print of the Memory Entry's fields
(run_id, stored_at, status flags, tombstone marker if present).

### `novetest memory delete <run_id>`

Tombstone a Memory Entry (atomic POSIX rename; recoverable until
garbage collection).

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

---

## `novetest licenses [--full]`

```bash
novetest licenses          # summary list
novetest licenses --full   # summary + verbatim NOTICES.md text
```

Lists every third-party component Nove Test redistributes or links to,
with SPDX license tag. Required for legal / audit / SBOM workflows.

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

---

## Output mode override (any verb)

```bash
novetest <verb> --output {json|text|ndjson}
# or
NOVETEST_OUTPUT={json|text|ndjson} novetest <verb>
```

| Mode | Output |
|---|---|
| `text` | Human-readable summary (the default on a TTY). What this entire manual shows. |
| `json` | Pretty-printed `novetest/v1` envelope (`indent=2`). The default when piped. |
| `ndjson` | Same envelope on one line (no indent, trailing newline). For log streams. |

Precedence (canonical Unix): **explicit `--output` > `NOVETEST_OUTPUT`
env > TTY auto-detect**.

If you want to see what your agent counterpart sees:

```bash
NOVETEST_OUTPUT=json novetest test | jq .
```

---

## What this page deliberately does NOT cover

- The full SBFL math behind each formula → `design/implementation-plan/localization-strategy.md`.
- The recommendation synthesis taxonomy beyond what's in [after-test.md](./after-test.md) → `design/implementation-plan/recommendation-synthesis.md`.
- Adapter internals (how each engine is invoked, normalization rules) → `design/implementation-plan/engine-adapters.md`.
- Replay classification rules (what makes a result `inconsistent` vs `unable_to_replay`) → `design/workflows/replay.md`.

Those live under `design/`. This page is for using the verbs.
