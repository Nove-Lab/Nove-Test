# After `novetest test` — interpret + follow up (Human)

After `novetest test` returns, you have a recommendation block on
your terminal. This page covers:

1. The exit-code → meaning table.
2. How to read the text-mode output line by line.
3. The seven recommendation categories.
4. The follow-up verbs: `novetest status` and `novetest inspect <run_id>`.
5. The sub-report verbs (`coverage show`, `regression compare`,
   `localization`, `replay`, `compare`, `memory`).
6. Warnings.
7. A worked example on the `calc` project (green → bug → drill in).

Everything beyond this — `coverage diff`, non-default `localization`
formulas, `memory delete` cleanup — lives in
[advanced.md](./advanced.md).

All outputs on this page are real captures from the `calc` example
(a tiny Python package with `add` and `subtract`). Run ids are 26-char
ULIDs; yours will differ — copy the one printed in your own output.

---

## Exit codes

Nove Test uses **6 well-defined exit codes**. Read the exit code in
your shell with `echo $?` (or `$LASTEXITCODE` in PowerShell).

| Code | Meaning | What to do |
|---|---|---|
| `0` | Transport succeeded; your tests passed. | Done. (Or read the recommendation.) |
| `1` | Unexpected error (CLI crash). | This is a bug. File an issue with the output. |
| `2` | Bad input (missing Project Store, invalid flag, unknown `run_id`). | Fix the invocation. The `✗` block on stdout names what's wrong. |
| `3` | Transport succeeded; your tests **failed or errored**. | Read recommendations. This is real product information, not a tooling problem. |
| `4` | Native test engine not ready (missing on PATH, adapter error). | Install / configure the missing tool. The `✗` block names what to install. |
| `5` | Project Store corrupt or unreadable. | Inspect `.novetest/store.json`. Worst case: `rm -rf .novetest && novetest init` (you lose history). |

Crucial nuance: **exit code 3 is normal**. Your tests failed — or a
suite errored before producing results (`run_record.status: "errored"`);
the CLI did its job; the output is a recommendation telling you which
tests failed. The envelope's `ok` is still `true` — the failing (or
errored) tests are *data*, not a tooling problem.

A second nuance: an **"unavailable" outcome is exit 0**. When coverage,
regression, or localization can't produce facts for a structural reason
(no baseline yet, no failing tests, ran without `--coverage`), that is
reported as data on a successful (exit 0) command — never an error.

---

## Reading text-mode output

Every `novetest test` invocation prints a block in the same shape:

```
<count> <recommendation|recommendations> · <count> <category|categories> · run_id=<ULID>

  <glyph> [<category>] <human-readable sentence>
      ↳ <citation>
```

### Glyphs

| Glyph | When you see it | What it means |
|---|---|---|
| `✓` | `[all_green]`, passed status, available sub-report | Good news / informational. No action required. |
| `✗` | failed status, regression with `regressed>0`, error envelopes | Bad news. Look here. |
| `—` | `unavailable_analysis`, unavailable sub-report (`status`, `inspect`) | Unavailable for a structural reason. Not an error. |
| `!` | Any action recommendation (`investigate_location`, `investigate_regression`, …) | Needs your attention. |
| `?` | Replay sub-report in `inspect` | "We can't tell" / not yet attempted. |
| `⚠` | Trailing `warnings:` block | Advisory. |
| `·` | Separator | Whitespace with a dot. |
| `↳` | Citation pointer | The recommendation is based on this thing. |

### The header line

```
1 recommendation · 1 category · run_id=01KVYRJJ4PN2F6DPKW1FHD1SP6
```

Three things:

- **Recommendation count** — how many distinct things Nove Test wants
  you to know about this run.
- **Category count** — how many unique categories the recommendations
  span.
- **`run_id=...`** — the ULID of the Run Record. Copy this for
  `novetest inspect <run_id>` and the per-stage verbs.

### The all-green block

```
1 recommendation · 1 category · run_id=01KVYRJJ4PN2F6DPKW1FHD1SP6

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJ4PN2F6DPKW1FHD1SP6
```

Each recommendation is two lines: `<glyph> [<category>] <sentence>`
then `↳ <citation>`. The sentence is self-contained English; the
citation tells you what justifies the recommendation.

---

## The seven recommendation categories

The synthesizer draws from a **closed set of 7 categories**. Each
recommendation carries a numeric `priority` — **lower means higher
priority** (1 is the most urgent). There is no "severity" field;
`priority` is the only ranking.

| Priority | Category | What it means |
|---|---|---|
| 1 | `regression_with_localization` | A newly-failing test overlaps a top SBFL location — the strongest signal. |
| 2 | `investigate_location` | SBFL ranked a code location suspicious (high/medium confidence, rank ≤ 3). |
| 3 | `investigate_regression` | A test newly failed versus the baseline (a regression transition). |
| 4 | `coverage_gap` | Uncovered lines overlap a suspicious location. |
| 5 | `flaky_suspected` | A replay classified the run inconsistent. Fires from `novetest test --reruns N` (N ≥ 1): when the run has failures, the whole run is replayed N times and divergence produces this recommendation. Default (`--reruns 0`) never replays. |
| 6 | `unavailable_analysis` | Tests failed but a downstream stage couldn't run (e.g. no baseline). Informational. |

(Category names are pinned verbatim to the code — see "Closed taxonomy v1" in `design/implementation-plan/recommendation-synthesis.md` §8.)
| 7 | `all_green` | Zero failures, zero regressions. Exclusive — never appears alongside another category. |

Notes worth internalising:

- `regression_with_localization` and `investigate_regression` only fire
  on a **newly-failing** transition (passing in the baseline, failing
  now). Re-running an already-failing suite does **not** re-trigger them.
- `flaky_suspected` never appears from `novetest test` — replay is a
  separate verb (see below).
- The failing `calc` run below produces only `investigate_location`
  (priority 2) — it fires purely because SBFL ranks a suspicious code
  location (high confidence, rank ≤ 3), independent of any baseline. The
  regression categories (1/3) would additionally appear only if a
  newly-failing transition were detected for that run.

---

## A worked example: green → bug → drill in (the `calc` project)

### 1. Green run

```bash
novetest init
novetest test
```

```
1 recommendation · 1 category · run_id=01KVYRJJ4PN2F6DPKW1FHD1SP6

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJ4PN2F6DPKW1FHD1SP6
```

Exit code: 0. Done.

### 2. Introduce the bug

Change `calc/arithmetic.py` line 6 so `subtract` adds instead:

```python
def subtract(a: int, b: int) -> int:
    return a + b   # bug: was a - b
```

```bash
novetest test
```

```
5 recommendations · 1 category · run_id=01KVYRRS331FVE3XP71RKNYMMH

  ! [investigate_location] Investigate `add`@2 in `calc/arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).
      ↳ localization_finding calc/arithmetic.py:2 (rank 2)
  ! [investigate_location] Investigate `subtract`@6 in `calc/arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
      ↳ localization_finding calc/arithmetic.py:6 (rank 1)
  ! [investigate_location] Investigate `test_subtract`@13 in `tests/test_arithmetic.py` (rank 1, ochiai=1.000, sbfl_per_test).
      ↳ localization_finding tests/test_arithmetic.py:13 (rank 1)
  ! [investigate_location] Investigate `test_add_positive`@5 in `tests/test_arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).
      ↳ localization_finding tests/test_arithmetic.py:5 (rank 2)
  ! [investigate_location] Investigate `test_add_zero`@9 in `tests/test_arithmetic.py` (rank 2, ochiai=0.000, sbfl_per_test).
      ↳ localization_finding tests/test_arithmetic.py:9 (rank 2)
```

Exit code: **3** (your tests failed; `ok` is still `true`).

The top signal is `subtract`@6 at `ochiai=1.000`, rank 1 — that is the
line you broke. The `sbfl_per_test` token is the SBFL mode; `ochiai`
is the formula.

### 3. Drill in

For the rest of this page the failing run's id is
`01KVYRRRN9FWVNQWVHNE1QHAQ4` and its passing baseline is
`01KVYRRR9ZNAM1PBA9JTR4QXC6` (copy yours from `memory list`).

See the full SBFL ranking:

```bash
novetest localization 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
sbfl_per_test · ochiai · 5 entries · confidence=high · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
  1. subtract@6 in calc/arithmetic.py (1.000)
  1. test_subtract@13 in tests/test_arithmetic.py (1.000)
  2. add@2 in calc/arithmetic.py (0.000)
  2. test_add_positive@5 in tests/test_arithmetic.py (0.000)
  2. test_add_zero@9 in tests/test_arithmetic.py (0.000)
```

(Ties share a rank. `subtract` and the test that exercises it both
score 1.000.)

See coverage for the run (`test` always collects coverage):

```bash
novetest coverage show 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✓ per-test · 13/13 statements (100.0%) · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

Confirm the regression versus the green baseline:

```bash
novetest regression compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✗ regressions · regressed=1 fixed=0 still_failing=0
  baseline=01KVYRRR9ZNAM1PBA9JTR4QXC6 target=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

(Argument order is baseline first, target second, and it matters.)
Exit code: 0 — a regression is *data*, not an error.

### 4. Fix and re-run

Restore line 6 to `return a - b`, then `novetest test` — you are back
to the green block from step 1, exit 0.

The loop is: read the top recommendation, act on it, re-run.

---

## `novetest status` — what's cached in this project?

```bash
novetest status
```

```
latest run · 01KW0PATQMBP2GXMFRX3J5EEX3 · history: 2 runs

  ✓ coverage      available
  ✓ regression    available
  — localization  unavailable
  — replay        unavailable
```

Read top to bottom:

- **Header** — the most recent Run Record's ULID and the run count.
- **Sub-report list** — one line per derived stage. `✓ available` means
  "queryable via the per-stage verb"; `—` means it isn't there yet for a
  structural reason. Here `localization` is unavailable because the
  latest run had no failing tests, and `replay` is always unavailable
  until you run `novetest replay`.

`status` is read-only, fast, and never derives anything. Reach for it
when you come back to a project and want to remember where you left off.

---

## `novetest inspect <run_id>` — drill into one run

```bash
novetest inspect 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✗ 01KVYRRRN9FWVNQWVHNE1QHAQ4 · failed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 13/13 statements (100.0%)
  regression    ✗ regressions · regressed=1 fixed=0 still_failing=0
  localization  sbfl_per_test · ochiai · 5 entries · confidence=high
  replay        ? unavailable (missing-derived-facts)
```

- **Header** — glyph + ULID + run status + engine (ecosystem) + target.
  `target=<workspace>` means "the whole project".
- **coverage** — `✓ <granularity> · <covered>/<total> statements (<pct>%)`,
  or `— unavailable (<reason>)`.
- **regression** — `✓ clean …` / `✗ regressions …` with
  regressed/fixed/still_failing counts, or `— unavailable (<reason>)`.
- **localization** — a one-line summary; the full ranked list lives in
  `novetest localization <run_id>`.
- **replay** — `? unavailable (missing-derived-facts)` until you have run
  `novetest replay` for this id; `inspect` itself never runs replay.

`inspect` is a pure read — it executes nothing and works on tombstoned
runs too. Reach for it when you need a number or a reason; for a green
run the `novetest test` recommendation already tells you everything.

---

## Sub-report verbs at a glance

All take a `run_id` you copy from `memory list` / `inspect` / the
`run_id=` header.

| Verb | Shows |
|---|---|
| `novetest memory list` | Table of every run (`run_id  target  status  created_at`). |
| `novetest memory show <run_id>` | One run's full stored record. |
| `novetest coverage show <run_id>` | Cached coverage for a run (cache-read only; needs an earlier `run --coverage` or `test`). |
| `novetest regression compare <base> <target>` | Pass/fail transitions between two runs. |
| `novetest regression latest` | The two most recent comparable runs, compared automatically. |
| `novetest localization <run_id>` | The full SBFL ranking (add `--formula` / `--top-n`). |
| `novetest replay <run_id>` | Re-executes the run to check reproducibility. |
| `novetest compare <base> <target>` | Regression **and** coverage delta in one shot. |

`novetest memory list` for the `calc` project:

```
4 runs

run_id                      target       status  created_at
01KVYRJK97SSR5DR840PH26VQK  <workspace>  passed  2026-06-25T06:48:14.375000Z
01KVYRJJYJTS2NRCB2QZ57SSPJ  <workspace>  passed  2026-06-25T06:48:14.034000Z
01KVYRJJJ75ZRHC05GNKYRK99S  <workspace>  passed  2026-06-25T06:48:13.639000Z
01KVYRJJ4PN2F6DPKW1FHD1SP6  <workspace>  passed  2026-06-25T06:48:13.206000Z
```

`novetest compare` shows both signals; here coverage is unavailable
because the baseline run was stored without coverage facts:

```bash
novetest compare 01KVYRRR9ZNAM1PBA9JTR4QXC6 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
regression: ✗ regressions · regressed=1 fixed=0 still_failing=0
coverage:   — unavailable (missing-derived-facts)
```

`novetest replay` re-executes the run and classifies it. The reruns are
stored as new runs (they show up in `memory list`):

```bash
novetest replay 01KVYRRRN9FWVNQWVHNE1QHAQ4
```

```
✓ reproducible · 1/1 · run_id=01KVYRRRN9FWVNQWVHNE1QHAQ4
```

The classification is one of `reproducible`, `inconsistent`, or
`unable_to_replay`. To hunt flakiness, point replay at a suspect run
with `--reruns 5`.

You can also opt into replay directly from `test`: `novetest test
--reruns 5` replays a **failed** run five times as part of the same
invocation, and an `inconsistent` classification surfaces as a
`! [flaky_suspected]` recommendation with a `replay_result` citation
(summary like ``Test `…` flaky: 1/5 reruns failed.``). The default
`--reruns 0` keeps today's behavior — no replay.

---

## Warnings

A trailing `warnings:` block can appear under any verb's output:

For example, re-running `novetest localization <run_id> --formula op2`
on a run whose findings were cached at the default `ochiai` re-derives the
cache and appends:

```
warnings:
  ⚠ localization-cache-rederived: cached findings (--formula='ochiai' --top-n=10) were re-derived at requested --formula='op2' --top-n=10; cache overwritten at .novetest/localization/findings/run_<id>/localization_findings.json
```

Each line is `⚠ <code>: <message>`. Warnings are **advisory** — the
command succeeded; we wanted you to know something. The two you may see
both come from `localization`:

| Code | Meaning |
|---|---|
| `localization-cache-rederived` | You passed `--formula`/`--top-n` that differed from the cached finding, so it was re-derived at the new flags. |
| `localization-formula-noop-in-mode` | You passed `--formula`, but the run's SBFL mode (`failure_proximity`) does not consume a formula, so nothing changed. |

Warnings never affect the exit code or `ok`.

---

## Where to go from here

- Deeper usage (`coverage diff`, non-default formulas, `memory delete`)
  → [advanced.md](./advanced.md).
- Per-engine quirk biting you → [languages.md](./languages.md).
- Something didn't work → [troubleshooting.md](./troubleshooting.md).
