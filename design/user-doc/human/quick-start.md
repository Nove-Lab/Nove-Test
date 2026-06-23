# Quick Start — the canonical happy path (Human)

The 4-step canonical workflow. We use the working example from
[README.md](./README.md#the-working-example-used-throughout-this-manual)
(a tiny Python + pytest project with 3 green tests). Every output
on this page is the actual text the CLI prints to your terminal.

The four steps:

1. `novetest init` — create the per-project store under `.novetest/`.
2. `novetest test` — run tests, derive coverage / regression / localization, synthesize a recommendation.
3. Read the recommendation block on stdout.
4. (Optional) `novetest inspect <run_id>` to dig deeper.

For everything beyond step 2 (status, inspect with all sub-reports,
replay), see [after-test.md](./after-test.md). For language-specific
toolchain notes, see [languages.md](./languages.md).

---

## Step 1 — `novetest init`

Run from the project root (the directory that contains
`pyproject.toml` in our example):

```bash
cd my-project
novetest init
```

You should see:

```
✓ Initialized .novetest/ at /home/you/my-project/.novetest
  engine readiness: ready — python/pytest 8.0.0
```

What just happened:

- A `.novetest/` directory was created. It holds every Run Record,
  Coverage Facts set, Regression Facts set, Localization Findings set,
  and Replay Result for this project — as plain JSON files.
- Nove Test auto-detected your engine (`pytest`) from
  `pyproject.toml`. The `engine readiness: ready` line means the
  native engine is fully installed and ready to run.

If you see `engine readiness: engine-missing` or
`engine-misconfigured` instead, the next line(s) will be
`issue: ...` explaining what to fix. See
[troubleshooting.md](./troubleshooting.md#engine-missing-or-misconfigured).

> **Where do I run `novetest test` from?** Anywhere inside
> `my-project/` (the project root or any subdirectory). Nove Test
> walks up from your current working directory to find `.novetest/`,
> just like `git` finds `.git/`. Running from a directory whose
> ancestors do not contain `.novetest/` returns an `uninitialized`
> error.

### Directory tree created by `init`

```
.novetest/
├── store.json              # schema_version, initialized_at, store_state
├── memory/
│   ├── runs/               # one Run Record per execution
│   └── tombstones/         # soft-deleted entries
├── run/
│   ├── artifacts/          # native engine raw output + logs
│   └── readiness/          # cached readiness probe result
├── coverage/facts/         # per-run Coverage Facts
├── regression/pairs/       # cached Regression Facts per (baseline,target) pair
├── localization/findings/  # SBFL findings per run
├── replay/results/         # Replay Results per replay
└── orchestration/
    ├── recommendations/    # synthesized recommendations
    └── status/             # latest cached status snapshot
```

You usually do not need to look inside. The CLI manages this for you.

`init` is fully idempotent — re-running it on an already-initialized
project does nothing destructive.

---

## Step 2 — `novetest test`

This is the single command that does everything.

```bash
novetest test
```

Or, equivalently:

```bash
novetest test tests/
novetest tests/        # bare default-verb alias — same thing as above
```

We recommend the explicit `novetest test` form in scripts. The bare
alias is handy at the prompt.

You should see:

```
1 recommendation · 1 category · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Read top to bottom:

- **Summary line.** "1 recommendation · 1 category · run_id=..." — Nove Test had one thing to tell you, in one category, for a run with this ULID.
- **Glyph + category.** `✓` means "good news"; `[all_green]` is the category from the closed taxonomy. Other categories you may see: `[tests_failed]`, `[coverage_regressed]`, `[new_test_failure]`, `[flaky_suspect]`, `[unavailable_analysis]`.
- **Sentence.** A self-contained English sentence summarizing the recommendation. You can act on this directly.
- **Citation arrow.** `↳ run_reference 01HX...` points at the Run Record this recommendation is based on. Copy that ULID to drill in with `novetest inspect`.

Exit code: **0** because the tests passed. If your tests had failed,
the exit code would be **3** (not 1) — that is meaningful product
data, not an error. See [after-test.md](./after-test.md#exit-codes)
for the full table.

### What `novetest test` did under the hood

1. **Ran** the native engine (`pytest`) and persisted a Run Record under `.novetest/memory/runs/`.
2. **Derived coverage** (via `pytest-cov`, if installed) and persisted facts under `.novetest/coverage/facts/`.
3. **Resolved a regression baseline** — the immediately preceding run on the same target. On the very first run there is no baseline, so this stage simply reports "unavailable".
4. **Computed SBFL fault localization** (Ochiai by default). With zero failing tests there is nothing to localize, so this stage may report "unavailable" too — that is expected, not an error.
5. **Synthesized recommendations** — picked deterministic recommendations from the facts above and printed them.

The five stages run in order. If a stage fails its readiness check
(e.g. `pytest-cov` not installed), `novetest test` does not abort —
it records the stage as "unavailable" and continues. The only hard
failures are: engine missing (exit 4), bad usage (exit 2), or a
corrupt Project Store (exit 5).

### Working with coverage

Coverage is auto-enabled when `pytest-cov` is present. If you do not
have it installed yet:

```bash
pip install pytest-cov
novetest test
```

You should now see a `✓` for coverage in the deeper view (`novetest
inspect <run_id>`, covered in step 4 below).

---

## Step 3 — read the recommendation

For the all-green happy case there is exactly one recommendation and
it tells you everything you need: nothing to do. You are done.

For non-trivial outcomes the same shape applies — read top to
bottom:

```
3 recommendations · 2 categories · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ! [tests_failed] 2 tests failed in tests/test_math_utils.py.
      ↳ test_result tests/test_math_utils.py::test_add_positive (failed)
  ! [tests_failed] (continued — see inspect for full list)
      ↳ test_result tests/test_math_utils.py::test_subtract (failed)
  ✓ [unavailable_analysis] Localization unavailable — no baseline yet.
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Two cues:

- **`!`** in front of `[tests_failed]` — needs action.
- **`✓`** in front of `[unavailable_analysis]` — informational, no
  action.

A pattern emerges: glyph carries urgency, category carries kind,
sentence carries detail, citation carries the pointer back.

Multiple recommendations are listed in priority order (most urgent
first). You can usually act on the top recommendation, re-run
`novetest test`, and re-read the new output.

For a worked example walking through "green → fail → green" with
real failure output, see
[after-test.md](./after-test.md#a-worked-example-green--fail--green).

---

## Step 4 — (optional) drill into the run with `inspect`

If you want to see everything for a single run on one screen:

```bash
novetest inspect 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

You should see:

```
✓ 01HX0K4M5N6P7Q8R9STUVWXYZ0 · passed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 10/11 statements (86.7%)
  regression    — unavailable (no-comparable-baseline)
  localization  — unavailable (no_failed_tests)
  replay        ? unavailable (not-run)
```

Read it like this:

- **Header line.** `✓` (passed), the run's ULID, the engine + ecosystem, and what target you ran. `target=<workspace>` is the explicit token for "the whole project".
- **Four sub-report lines.** One per engine — each gives you the kind-discriminated outcome (`✓ <fact-set summary>` if facts were derived, `—` or `?` followed by a reason if not).

Reasons you will commonly see in the happy path:

| Reason | Meaning |
|---|---|
| `no-comparable-baseline` | First run on this target. There is nothing to compare against; the next run will populate it. |
| `no_failed_tests` | SBFL had no failures to attribute, so nothing to rank. (Expected on green runs.) |
| `not-run` | `novetest test` deliberately did not auto-invoke replay (it would multiply wall time). Call `novetest replay <run_id>` explicitly if you want it. |

You do **not** need `inspect` for the simple happy case — the
recommendation from `novetest test` is enough. Reach for `inspect`
when you want a raw audit trail or are debugging why a stage reported
"unavailable".

---

## Two patterns to internalize

1. **One canonical command.** `novetest test` is the single call.
   Do not stitch together `run` + `coverage show` + `regression
   compare` + `localization` by hand for the happy path; `test` does
   it in the right order with the right defaults.
2. **Glyph + category + sentence + citation.** Every recommendation
   you ever see follows this shape. Learn to skim it.

---

## What to read next

- Your project is not Python? → [languages.md](./languages.md).
- You want to interpret a `tests_failed`, dig into a failing run, or
  see the exit-code table → [after-test.md](./after-test.md).
- You suspect you need a deeper verb than the happy path covers →
  [advanced.md](./advanced.md).
- Something went wrong → [troubleshooting.md](./troubleshooting.md).
