# Advanced verbs (Human)

The happy path (`--version`, `--help`, `init`, `test`) plus the two
follow-ups (`status`, `inspect`) cover ~90% of day-to-day Nove Test
use. This page documents the **other verbs** — when to reach for them,
what they print in text mode, and the one-line summary of what they do.

Every example here uses the canonical `calc` demo project (a tiny
Python package: `add`/`subtract` in `calc/arithmetic.py`, three tests).
The "with the bug" examples flip `subtract` to return `a + b`, so
`test_subtract` fails. Run ids shown are the real 26-char ULIDs from
those runs.

Verbs covered here:

- **Run engine raw** — `novetest run`
- **Coverage engine** — `novetest coverage show`, `novetest coverage diff`
- **Regression engine** — `novetest regression compare`, `novetest regression latest`
- **Localization engine** — `novetest localization`, `novetest localization latest`
- **Replay engine** — `novetest replay`
- **Composed view** — `novetest compare`
- **Memory / history management** — `novetest memory list`, `novetest memory show`, `novetest memory delete`
- **Destructive reset** — `novetest reset --confirm`
- **Attribution** — `novetest licenses [--full]`

For the agent set's full envelope shapes, see
[agent/advanced.md](../agent/advanced.md).

---

## `novetest run` — run tests without orchestration

```bash
novetest run [<target>] [--coverage]   # or -c
```

What it does: invokes the native engine and persists a Run Record.
That's it. It does **not** auto-derive regression, localization, or
recommendations (that's what `novetest test` is for).

Use when:

- You want fine-grained control over the pipeline (e.g. CI splitting "run" from "analyze").
- You're debugging an adapter and want the raw run result without orchestration.
- You want to control coverage. **`run` is the only verb with `--coverage`/`-c`.** `novetest test` *always* collects coverage and has no such flag; `run` collects it only when you ask.

`<target>` is forwarded verbatim to the native engine as a test
selector (a pytest nodeid, a path, etc.). Omit it to run the whole
suite. The default-verb alias means `novetest <selector>` is the same
as `novetest test <selector>`.

Text-mode output (all-pass, no coverage):

```
✓ passed · 3/3 · run_id=01KVYRJJYJTS2NRCB2QZ57SSPJ
```

With the bug, and `--coverage`:

```
✗ failed · 2/3 · run_id=01KVYRRSWDPWGGGV3GX5QXXJK6
  failed tests:
    ✗ tests/test_arithmetic.py::test_subtract
  coverage: ✓ per-test · 13/13 statements (100.0%)
```

The `coverage:` line only appears when you pass `--coverage`. A run
with failing tests exits **3** (the failing tests are data, not an
error). A clean run exits **0**.

> **Note on Go:** `go-test` runs execute, but `--coverage` produces no
> coverage facts for Go (the adapter writes a coverage profile the
> coverage engine doesn't consume). The other five engines —
> `pytest`, `jest`, `junit`, `cargo-test`, `xunit` — produce coverage.

---

## `novetest coverage` — coverage engine

Coverage facts are produced by `run --coverage` (and by `test`). The
`coverage` sub-app only **reads** what's already on disk — it never
re-derives. If a run was executed without coverage, you'll get an
`unavailable` result (still exit 0 — unavailability is data). The
sub-app has exactly two verbs: `show` and `diff` (there is no
`coverage latest`).

### `novetest coverage show <run_id>`

```bash
novetest coverage show 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Text mode:

```
✓ per-test · 13/13 statements (100.0%) · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

When the suite has branch coverage, a `· branches C/N` segment is
appended (e.g. `· branches 3/4`). For a run that never had coverage
derived:

```
— unavailable (missing-derived-facts)
```

Use when you want to re-query a known run without re-running it.

### `novetest coverage diff <baseline_run_id> <target_run_id>`

Per-file coverage delta between two runs (both must have coverage
facts). Order is `baseline` then `target`.

```bash
novetest coverage diff 01KVYRRSF4... 01KVYRRSWD...
```

Text mode (two coverage-bearing `calc` runs, both 13/13 statements):

```
coverage diff · 01KVYRRSF48RMYV84MTB4XQ6P9 → 01KVYRRSWDPWGGGV3GX5QXXJK6
  100.0% → 100.0% (Δ +0.0%) · files +0/-0/~0
```

If either side lacks coverage facts, the diff is `— unavailable
(missing-derived-facts)`. In the bug scenario the passing baseline was
run without `--coverage`, so a diff against it is unavailable. Use for
PR review automation and "did I cover the new code?" probes.

---

## `novetest regression` — regression engine

The `regression` sub-app has exactly two verbs: `compare` and
`latest`.

### `novetest regression compare <baseline_run_id> <target_run_id>`

Explicit pair comparison; `baseline` first, `target` second (order is
significant — it sets the direction of every transition).

```bash
novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Text mode (the bug regressed `test_subtract`):

```
✗ regressions · regressed=1 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Clean (no regressions):

```
✓ clean · regressed=0 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

A successful comparison always exits **0** — even an `unavailable`
outcome (tombstoned side, engine mismatch, no comparable baseline) is
data, not an error. Only a stale/unknown run id is an error (exit 2).

### `novetest regression latest`

```bash
novetest regression latest
```

Same output shape. It auto-resolves the two most recent comparable
runs (newest non-tombstoned run's target, then its most-recent prior
comparable run) and compares them. `novetest test` already runs this
for you; the standalone verb is mainly for diagnostic re-querying. It
needs **≥2 comparable runs**; with fewer it reports `— unavailable
(no-comparable-baseline)`.

---

## `novetest localization` — SBFL fault localization

```bash
novetest localization <run_id> [--formula <ochiai|op2|dstar2|tarantula>] [--top-n <int>]
novetest localization latest [--formula ...] [--top-n ...]
```

Rank suspicious code locations for a run via Spectrum-Based Fault
Localization. `novetest localization <run_id>` is the default verb (no
verb word) — there is no `localization run` subcommand. The only named
sub-verb is `latest`.

| Flag | Default | Meaning |
|---|---|---|
| `--formula` | `ochiai` | SBFL scoring formula. One of `ochiai`, `op2`, `dstar2`, `tarantula`. |
| `--top-n` | `10` | Cap the ranked list (positive integer). |

The four formulas are the only accepted values. Note it is **`dstar2`,
not `dstar`** — `--formula dstar` is rejected (in text mode the error
renders as a `✗ <command>` header plus an indented `<code>: <message>`
line):

```
✗ localization
  invalid-flag: Invalid --formula='dstar'; expected one of ['dstar2', 'ochiai', 'op2', 'tarantula']
```

(That's an exit-2 usage error, as is `--top-n 0`.)

Text-mode output (with the bug):

```
sbfl_per_test · ochiai · 5 entries · confidence=high · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
  1. subtract@6 in calc/arithmetic.py (1.000)
  1. test_subtract@13 in tests/test_arithmetic.py (1.000)
  2. add@2 in calc/arithmetic.py (0.000)
  2. test_add_positive@5 in tests/test_arithmetic.py (0.000)
  2. test_add_zero@9 in tests/test_arithmetic.py (0.000)
```

The header is `<mode> · <formula> · <N> entries · confidence=<level>`.
Each line is `<rank>. <symbol>@<line> in <file> (<normalized score>)`.
The buggy `subtract@6` lands rank 1 with score 1.000. Ranks are dense,
so ties share a rank (here two entries are tied at rank 1).

The mode is chosen automatically from the run's coverage:
`sbfl_per_test` (pytest with per-test coverage, confidence high),
`sbfl_aggregate` (other engines' file-level coverage, confidence
medium), or `failure_proximity` (no coverage at all — a heuristic, not
SBFL, confidence low). There is no `--mode` flag.

With no failing tests, localization is `— unavailable
(no_failed_tests)` (exit 0). `localization latest` walks newest-first
to the first analyzable run on the active target (on a store with no
analyzable run it reports `— unavailable (run_not_analyzable)`).

**Switching formulas.** All four formulas are always computed and
cached. If you re-invoke `localization` with a *different, explicit*
`--formula` or `--top-n` than what was cached, Nove Test rewrites the
cache and emits a `⚠ localization-cache-rederived` warning. This is
deliberate. (In the `failure_proximity` mode the formula is a
placeholder; a formula-only mismatch there emits
`⚠ localization-formula-noop-in-mode` instead and does not re-derive.)

---

## `novetest replay <run_id>` — re-execute and classify

```bash
novetest replay <run_id> [--reruns <int>] [--timeout <seconds>]
```

`<run_id>` is the **original** run's id. Replay reconstructs that run's
target and engine context and re-executes it.

| Flag | Default | Meaning |
|---|---|---|
| `--reruns` | `1` | How many times to re-execute. Bump to 5 or 10 to probe flakiness. |
| `--timeout` | `600.0` | Per-rerun ceiling in seconds. |

It classifies reproducibility as `reproducible` / `inconsistent` /
`unable_to_replay`. The policy is strict: a single differing rerun makes
the whole result `inconsistent` (no majority vote).

Text-mode output (replaying the failing run — it fails again, so it's
reproducible):

```
✓ reproducible · 1/1 · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

The `1/1` is reruns matched / reruns total. `reproducible` means every
rerun's run-level outcome matched the original (a reliably-failing run
is just as reproducible as a passing one).

Two things to know:

- **Replay persists its reruns as real Memory Entries.** After a replay,
  `memory list` shows the extra run(s) — it is not a dry operation.
- `novetest test` never auto-invokes replay (it would multiply
  wall-clock time by `--reruns`). Replay is the only producer of replay
  facts.

`unable_to_replay` is a valid success (exit 0). Some host-level
unavailability (`engine-not-ready`, `target-missing`) exits **4**
instead.

---

## `novetest compare <baseline_run_id> <target_run_id>`

Composed regression **and** coverage delta in a single envelope.

```bash
novetest compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Distinct from `regression compare`: that emits regression only; `compare`
emits both blocks. Cheaper than calling `regression compare` and
`coverage diff` separately because the memory entries are read once.

Text mode (bug scenario — baseline had no coverage, so the coverage
side is unavailable):

```
regression: ✗ regressions · regressed=1 fixed=0 still_failing=0
coverage:   — unavailable (missing-derived-facts)
```

Each block can be `unavailable` independently; the verb still exits 0.

---

## `novetest memory` — history management

### `novetest memory list`

```bash
novetest memory list
```

List Run History newest-first (tombstoned runs included). Text mode:

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

### `novetest memory show <run_id>`

Show one run's Memory Entry (live or tombstoned).

```bash
novetest memory show 01KVYP0WNB8X47ZPN85ZAYBKSN
```

Text mode:

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

The `evidence:` line reflects which peer-engine artifacts exist for the
run (they flip to `yes` as coverage / regression / localization / replay
are derived). The pytest version shown is *your* pytest, not a Nove Test
constant.

### `novetest memory delete <run_id>`

Tombstone a Memory Entry. This is a **soft delete** — an atomic POSIX
rename into `memory/tombstones/`; the entry still appears in
`memory list` / `memory show` with `tombstoned_at` set and its
`status` rewritten to `tombstoned`.

```bash
novetest memory delete 01KVYQ1SA2751X90JDNSG00RFD
```

Text mode:

```
✓ Tombstoned run_id=01KVYQ1SA2751X90JDNSG00RFD
```

The underlying JSON is not erased. Re-deleting an already-tombstoned
run is a no-op success (exit 0). To *hard*-wipe everything, use
`reset --confirm` (below).

---

## `novetest reset --confirm` — hard wipe

`reset` deletes the **entire** `.novetest/` store (live runs,
tombstones, and all derived coverage / regression / localization /
replay facts) and re-initializes an empty store. Nothing survives —
this is the destructive counterpart to `memory delete`.

It refuses to run without acknowledgement:

```bash
novetest reset
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

The `removed:` line summarizes what was wiped (it reads `nothing` when
the store was already empty). Reset re-detects your engine and reports
its readiness, exactly like `init` (the example above ran in a
workspace with no detectable engine). A corrupt store is **not**
auto-wiped — reset refuses with `store-corrupt` (exit 5) rather than
destroy data.

---

## `novetest licenses [--full]`

```bash
novetest licenses          # summary list
novetest licenses --full   # summary + verbatim NOTICES.md text
```

Lists every third-party component Nove Test redistributes or links to,
with its SPDX license tag. For legal / audit / SBOM workflows.

Text-mode output (without `--full`):

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

With `--full`, the verbatim `NOTICES.md` body is appended. Use that when
you need the actual license text bodies.

---

## Output mode override (any verb)

```bash
novetest --output {text|json|ndjson} <verb>
# or
NOVETEST_OUTPUT={text|json|ndjson} novetest <verb>
```

| Mode | Output |
|---|---|
| `text` | Human-readable summary (the default on a TTY). What this manual shows. |
| `json` | Pretty-printed `novetest/v1` envelope (`indent=2`, sorted keys). The default when piped. |
| `ndjson` | The same envelope on one compact line. For log streams. |

Precedence: **explicit `--output` > `NOVETEST_OUTPUT` env > TTY
auto-detect**. The `--output` flag is global and may appear **anywhere**
in the command line (it is stripped before the verb is dispatched). There
is no `--text` / `--json` flag (`--text` is rejected as an unknown
command).

To see what your agent counterpart sees:

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
