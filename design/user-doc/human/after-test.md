# After `novetest test` — interpret + follow up (Human)

After `novetest test` returns, you have a recommendation block on
your terminal. This page covers:

1. The exit-code → meaning table.
2. How to read the text-mode output line by line.
3. The two follow-up verbs you may want next: `novetest status` and
   `novetest inspect <run_id>`.
4. Warnings.
5. A worked example walking through "green → fail → green".

Everything beyond this — `compare`, `coverage diff`, `regression
compare`, `localization`, `replay`, `memory` cleanup — lives in
[advanced.md](./advanced.md).

---

## Exit codes

Nove Test uses **6 well-defined exit codes**. Read the exit code in
your shell with `echo $?` (or `$LASTEXITCODE` in PowerShell).

| Code | Meaning | What to do |
|---|---|---|
| `0` | Transport succeeded; your tests passed. | Done. (Or read recommendations for non-trivial all-green cases.) |
| `1` | Unexpected error (CLI crash). | This is a bug. File an issue with the output. |
| `2` | Bad input (missing Project Store, invalid flag, bad arg). | Fix the invocation. The `✗` block on stdout names what's wrong. |
| `3` | Transport succeeded; your tests **failed**. | Read recommendations. This is real product information, not a tooling problem. |
| `4` | Native test engine not ready (missing on PATH, misconfigured). | Install / configure the missing tool. The `✗` block on stdout names what to install. |
| `5` | Project Store corrupt or unreadable. | Inspect `.novetest/store.json`. Worst case: `rm -rf .novetest && novetest init` (you lose history). |

Crucial nuance: **exit code 3 is normal**. Your tests failed; the
CLI did its job; the output is a recommendation telling you which
tests failed. Treat it as the same severity as exit 0 — both are
"the CLI succeeded".

---

## Reading text-mode output

Every `novetest test` invocation prints a block in the same shape:

```
<count> <recommendation|recommendations> · <count> <category|categories> · run_id=<ULID>

  <glyph> [<category>] <human-readable sentence>
      ↳ <citation>
  <glyph> [<category>] ...
      ↳ <citation>
```

### Glyphs

| Glyph | When you see it | What it means |
|---|---|---|
| `✓` | `[all_green]`, `[unavailable_analysis]`, "passed" status | Good news / informational. No action required. |
| `✗` | `[tests_failed]`, regression summary, error envelopes | Bad news. Look here. |
| `—` | Sub-report availability (`status`, `inspect`) | Unavailable for a structural reason (no baseline yet, no failing tests, etc.). Not an error. |
| `⚠` | Trailing `warnings:` block | Advisory. Won't stop your work; might be worth investigating. |
| `!` | Recommendation categories that need action (`[tests_failed]`, `[coverage_regressed]`, `[new_test_failure]`, …) | Needs your attention. |
| `?` | Replay-specific "we can't tell" outcome | Replay couldn't classify reproducibility. Usually means a host-level limitation. |
| `·` | Separator | Just whitespace with a dot. |
| `↳` | Citation pointer | The recommendation is based on this thing. Often a `run_id`. |

### The header line

```
3 recommendations · 2 categories · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Three numbers + one ID:

- **Recommendation count.** How many distinct things Nove Test wants you to know about this run.
- **Category count.** How many unique categories the recommendations span. Often equal to the recommendation count.
- **`run_id=...`** — the ULID of the Run Record that produced this recommendation set. Copy this for `novetest inspect <run_id>`.

### Recommendation blocks

Each recommendation gets two lines:

```
  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

- **Line 1** — `<glyph> [<category>] <sentence>`. The sentence is a self-contained piece of English; you can show it to a teammate verbatim.
- **Line 2** — `↳ <citation kind> <citation target>`. The citation tells you "if you want to see what justifies this recommendation, look at this Run / test / coverage file / SBFL finding".

Citation kinds you may see:

| Kind | Looks like | Drill-in command |
|---|---|---|
| `run_reference` | `↳ run_reference 01HX...` | `novetest inspect <run_id>` |
| `test_result` | `↳ test_result tests/test_x.py::test_y (failed)` | `novetest inspect <run_id>` and scroll to the test result |
| `localization_finding` | `↳ localization_finding src/foo.py:42 (rank 1)` | `novetest localization <run_id>` to see the full ranked list |
| `coverage_fact` | `↳ coverage_fact src/foo.py` | `novetest coverage show <run_id>` |
| `regression_fact` | `↳ regression_fact tests/test_x.py::test_y` | `novetest regression latest` |

You usually only need to read the **first** citation per recommendation
on the happy path — Nove Test puts the most actionable pointer first.

---

## `novetest status` — what's cached in this project?

```bash
novetest status
```

You should see:

```
latest run · 01HX0K4M5N6P7Q8R9STUVWXYZ0 · history: 12 runs

  ✓ coverage      available
  ✓ regression    available
  ✓ localization  available
  — replay        unavailable
```

Read top to bottom:

- **Header.** The most recent Run Record's ULID, and how many runs total are in your history.
- **Sub-report list.** One line per derived stage, with the same glyph language as before. `✓ available` means "queryable via the per-stage verb"; `—` means "structural reason it isn't here".

`status` is read-only and fast. It is the right verb to peek at when
you come back to a project after a while and want to remember where
you left off.

If your project has zero runs yet (you just `init`'d), you'll see:

```
no runs yet · history: 0 runs
```

---

## `novetest inspect <run_id>` — drill into one run

```bash
novetest inspect 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

You should see:

```
✓ 01HX0K4M5N6P7Q8R9STUVWXYZ0 · passed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 245/287 statements (85.4%) · branches 59/68
  regression    ✓ clean · regressed=0 fixed=0 still_failing=0
  localization  sbfl_per_test · ochiai · 0 entries · confidence=high
  replay        ? unavailable (not-run)
```

Three rows + four sub-reports:

- **Header.** Glyph + ULID + Run status (`passed` / `failed` / `errored`) + engine (ecosystem) + target. `target=<workspace>` is the explicit token for "the whole project".
- **coverage.** Either `✓ <granularity> · <covered>/<total> statements (<pct>%)` (plus branches if the engine reports them), or `— unavailable (<reason>)`.
- **regression.** Either `✓ clean ...` / `✗ regressions ...` with regressed/fixed/still_failing counts, or `— unavailable (<reason>)`.
- **localization.** Header line; full ranked list lives in `novetest localization <run_id>`.
- **replay.** `✓ reproducible · N/N`, `✗ inconsistent · N/N failed`, or `? <classification> (<reason>)`.

A failing run looks like:

```
✗ 01HX0K4M5N6P7Q8R9STUVWXYZ0 · failed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 240/287 statements (83.6%)
  regression    ✗ regressions · regressed=2 fixed=0 still_failing=0
  localization  sbfl_per_test · ochiai · 3 entries · confidence=high
  replay        ? unavailable (not-run)
```

The same shape; just `✗` instead of `✓` and non-zero counts.

### When `inspect` is useful

- You want the raw coverage percentage.
- You want to see whether regression detected new regressions.
- You want to know if SBFL had something to rank (the `N entries`
  count).
- You're debugging why a stage said "unavailable" — the parenthesized
  reason tells you.

### When `inspect` is overkill

For the simple green case, the `novetest test` recommendation already
tells you everything. Reach for `inspect` only when you need a number
or a reason.

---

## Warnings

A trailing `warnings:` block can appear under any verb's output:

```
warnings:
  ⚠ localization-cache-rederived: cache was rewritten because --formula differed from cached value
  ⚠ engine-misconfigured: pytest-cov is not installed; coverage will be unavailable
```

Each line is `⚠ <code>: <message>`. Warnings are **advisory** — the
command succeeded; we just wanted you to know something. You can
safely ignore them in interactive work; production scripts may want to
log them.

Common warning codes you may see:

| Code | Meaning |
|---|---|
| `localization-cache-rederived` | The cache was rewritten because the requested `--formula` or `--top-n` differed from what was cached. |
| `localization-formula-noop-in-mode` | `--formula` was specified but the chosen SBFL mode (`failure_proximity`) does not consume a formula. |
| `engine-misconfigured` | Readiness probe found the engine but flagged missing optional pieces (e.g. coverage tool). |
| `junit-multiple-build-systems` | Both `pom.xml` and `build.gradle` present; the adapter picked Maven. |
| `coverlet-floor-degraded` | The .NET project pins an older Coverlet that cannot do per-test coverage. |

---

## A worked example: green → fail → green

We start with the working example from
[README.md](./README.md#the-working-example-used-throughout-this-manual).

### Run 1 — green

```bash
cd my-project
novetest init
novetest test
```

Output:

```
1 recommendation · 1 category · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Exit code: 0. Done.

### Run 2 — break a test, re-run

Edit `tests/test_math_utils.py` so `test_add_positive` fails:

```python
def test_add_positive() -> None:
    assert add(2, 3) == 99  # was 5
```

```bash
novetest test
```

Output (illustrative):

```
2 recommendations · 2 categories · run_id=01HX1L5N6O7P8Q9R0STUVWXYZ1

  ! [tests_failed] 1 test failed in tests/test_math_utils.py.
      ↳ test_result tests/test_math_utils.py::test_add_positive (failed)
  ! [new_test_failure] test_add_positive went green → failed since the previous run.
      ↳ regression_fact tests/test_math_utils.py::test_add_positive
```

Exit code: **3** (your tests failed). `ok` is still `true` — the CLI
did its job.

To see what failed and why, drill in:

```bash
novetest inspect 01HX1L5N6O7P8Q9R0STUVWXYZ1
```

Look for the failed `test_result` block in the inspect output, or use
`novetest run` directly to see the raw pytest stdout.

### Run 3 — fix the bug, re-run

Revert the edit:

```python
def test_add_positive() -> None:
    assert add(2, 3) == 5
```

```bash
novetest test
```

Output:

```
1 recommendation · 1 category · run_id=01HX2M6O7P8Q9R0STUVWXYZ12

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX2M6O7P8Q9R0STUVWXYZ12
```

(Depending on the specific synthesizer rule, you may also see a
`[recovered_from_failure]` recommendation — same shape, glyph `✓`,
recommends "you've recovered, all green now".)

Exit code: 0.

The loop is: read the top recommendation, act on it, re-run.

---

## Where to go from here

- Need a deeper verb (`replay`, `coverage diff`, `localization` with a
  non-default formula, `memory delete`) → [advanced.md](./advanced.md).
- Per-engine quirk biting you → [languages.md](./languages.md).
- Something didn't work → [troubleshooting.md](./troubleshooting.md).
