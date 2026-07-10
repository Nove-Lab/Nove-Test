# Quick Start — the canonical happy path (Human)

The four-step workflow you will use every day. It uses the working
example from
[README.md](./README.md#the-working-example-used-throughout-this-manual)
— the tiny **`calc`** project (a Python + pytest package with three
green tests). Every block on this page is the **actual text** the CLI
prints to your terminal in its default human mode.

The four steps:

1. `novetest init` — create the per-project store under `.novetest/`.
2. `novetest test` — run the tests, derive coverage / regression /
   localization, and synthesize a recommendation.
3. Read the recommendation block on stdout.
4. (Optional) `novetest inspect <run_id>` to drill into one run.

For everything past step 2 — exit codes, the full category list, when to
reach for `status` / `inspect` — see
[after-test.md](./after-test.md). For non-Python projects, see
[languages.md](./languages.md).

---

## Step 1 — `novetest init`

Run it once from the project root (the directory that holds
`pyproject.toml`):

```bash
cd calc-demo
novetest init
```

You should see:

```
✓ Initialized .novetest/ at /home/you/calc-demo/.novetest
  engine readiness: ready — python/pytest 9.0.3
```

What happened:

- A `.novetest/` directory was created. It holds every Run Record,
  Coverage Facts set, Regression Facts set, Localization Findings set,
  and Replay Result for this project — as plain JSON files.
- Nove Test detected your engine (`pytest`) from `pyproject.toml` and
  **pinned** it into the store — every later verb runs this engine;
  nothing is re-detected at run time. (One-off exception: `novetest
  test --engine <name>` runs another engine once without changing the
  pin.) `engine readiness: ready` means the native engine resolved and
  is ready to run. The version shown (`9.0.3` here) is **your own
  installed pytest**, not a Nove Test version.

If you see `engine readiness: engine-missing` or `engine-misconfigured`
instead, the next line is an `issue:` explaining what to fix — see
[troubleshooting.md](./troubleshooting.md#engine-missing-or-misconfigured).

> **Where do I run novetest from?** Anywhere inside `calc-demo/`. Nove
> Test walks up from your current directory to find `.novetest/`, just
> like `git` finds `.git/`. Run it somewhere with no `.novetest/` in any
> ancestor and you get an `uninitialized` error (exit 2).

### The directory `init` creates

`init` creates these directories plus `store.json`:

```
.novetest/
├── store.json          # schema_version, initialized_at, store_state
├── blobs/
├── memory/
│   ├── runs/           # one Run Record per execution
│   └── tombstones/     # soft-deleted (tombstoned) entries
├── run/                # → run/artifacts/    on first run (native output + logs)
├── coverage/           # → coverage/facts/   on first coverage derive
├── regression/         # → regression/pairs/ on first comparison
├── localization/       # → localization/findings/ on first SBFL run
├── replay/             # → replay/results/   on first replay
└── orchestration/      # reserved; recommendations are computed live, not stored
```

Each engine creates its own leaf subdirectory (shown after `→`) lazily,
on its first write — so right after `init` you only see the parent
directories above. You never need to look inside; the CLI manages it.
(Recommendations are synthesized fresh on every `test`; they are **not**
written to disk.)

---

## Step 2 — `novetest test`

The headline verb. It runs your tests through the native engine, stores a
Run Record, derives coverage / regression / localization where it can,
and prints a synthesized recommendation:

```bash
novetest test
```

On the all-green `calc` project:

```
1 recommendation · 1 category · run_id=01KVYRJJJ75ZRHC05GNKYRK99S

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVYRJJJ75ZRHC05GNKYRK99S
```

Exit code **0**. Reading it:

- **Header line** — how many recommendations, how many distinct
  categories, and the `run_id` (a 26-character ULID) you can pass to
  other verbs.
- **The block** — a glyph (`✓` here), a bracketed `[category]`, a
  one-line summary, and an `↳` citation pointing at the evidence.
- `[all_green]` is one of a closed set of **seven** categories. Each
  carries an integer `priority` (1 = most urgent … 7 = all green). See
  the full list in [after-test.md](./after-test.md#the-seven-recommendation-categories).

`novetest test` always collects coverage; there is no `--coverage` flag
on it. (The lower-level `novetest run` executes the engine and stores a
Run Record **without** the analysis pipeline, and takes `--coverage` /
`-c` if you want coverage on a bare run.)

> **Shortcut:** `novetest <path>` is the same as `novetest test <path>`
> — any first argument that is not a known verb is treated as a test
> target. For example `novetest tests/test_arithmetic.py` runs just that
> file. Bare `novetest` with no arguments prints the help screen; it does
> **not** run your tests.

---

## Step 3 — read the recommendation

For the happy path there is nothing to do: `[all_green]` means every test
passed and no action is recommended. When a test fails, `test` instead
emits one or more `[investigate_location]` recommendations that point at
the most suspicious code — and the exit code becomes **3** (your tests
failed) while the envelope itself still reports success. The
green → bug → drill-in walkthrough lives in
[after-test.md](./after-test.md#a-worked-example-green--bug--drill-in-the-calc-project).

The whole project's analysis availability is summarized by
`novetest status`:

```bash
novetest status
```

```
latest run · 01KVYRJK97SSR5DR840PH26VQK · history: 4 runs

  — coverage      unavailable
  — regression    unavailable
  — localization  unavailable
  — replay        unavailable
```

`—` means a sub-report is unavailable for this latest run (e.g. it was a
bare `novetest run` with no coverage, or there were no failing tests to
localize) — not an error.

---

## Step 4 — (optional) `novetest inspect <run_id>`

To see everything Nove Test knows about a single run, pass its `run_id`:

```bash
novetest inspect 01KVYRJJJ75ZRHC05GNKYRK99S
```

```
✓ 01KVYRJJJ75ZRHC05GNKYRK99S · passed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 13/13 statements (100.0%)
  regression    ✓ clean · regressed=0 fixed=0 still_failing=0
  localization  — unavailable (missing-derived-facts)
  replay        ? unavailable (missing-derived-facts)
```

`inspect` is a pure read — it executes nothing. It aggregates the four
derived sub-reports for that run:

- **coverage** — `✓` because `novetest test` always collects it; 13 of
  13 statements covered.
- **regression** — `✓ clean` because this run was compared against the
  previous run and nothing regressed.
- **localization** — unavailable: there were no failing tests to localize
  (a passing run has nothing to rank).
- **replay** — unavailable until you explicitly run `novetest replay
  <run_id>`; `test` never replays for you.

---

## That's the whole loop

`init` once, then `test` whenever you want a verdict, `status` /
`inspect` to review. From here:

- **[languages.md](./languages.md)** — the one toolchain note your engine
  needs if `calc` were jest / go-test / cargo-test / JUnit / xUnit.
- **[after-test.md](./after-test.md)** — exit codes, the seven categories,
  and the green → bug → fix walkthrough.
- **[advanced.md](./advanced.md)** — `coverage diff`, `regression
  compare`, `localization`, `replay`, `memory` cleanup, `licenses`.

Next: [languages.md](./languages.md).
