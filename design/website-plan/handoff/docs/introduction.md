# Introduction

**novetest is a polyglot test orchestration CLI.** One binary wraps
six native test engines behind a single command surface. The
`novetest test` verb executes your suite through the native engine,
persists a Run Record, derives coverage / regression /
fault-localization facts, and synthesizes a prioritized, evidence-cited
recommendation — all under one stable JSON contract called
`novetest/v1`.

This page covers the conceptual model you need before
[installing](./installation.md) the binary: who novetest is for, the
six engines it wraps, the contract you can rely on, the working example
used throughout these docs, and where to go next.

> **About the `For human` / `For agent` tabs.** novetest serves two
> readers — the human developer at a terminal and the AI coding agent
> consuming the JSON envelope. Most of these Docs are identical for
> both. Where they diverge, you'll see a tab control like the one
> below — pick your role once at the top of any page and the choice
> propagates everywhere on the site.

::: tabs
@tab For human

You opened these docs because you (or a teammate) want to run
`novetest` interactively at a terminal. Examples on every page show
the **actual text** the CLI prints in human mode — glyph-prefixed
summary lines, no JSON parsing required.

@tab For agent

You opened these docs because you are (or you are configuring) an AI
coding agent, a CI pipeline, or any non-interactive caller. Examples
on every page show the **literal `novetest/v1` JSON envelope** and
every interpretation step is a deterministic branch on a structured
key. Pin `NOVETEST_OUTPUT=json` at session start and parse the
envelope — never grep the human-mode text.

:::

---

## What problem novetest solves

AI writes code now, but it still tests with engines — and test
output — built for humans. AI coding agents change code faster than
anyone can verify it by hand; plain `pytest` / `jest` / `cargo test`
answers "did it pass?" and throws everything else away. The deeper
analysis (what regressed, where the fault is) usually lives far away in
a CI pipeline, too slow and too distant for an AI agent's fast inner
loop.

novetest closes that gap. It is **AI-facing testing infrastructure**
that sits on top of the engines you already use, so testing becomes a
**cumulative, machine-readable loop that runs locally** — in cadence
with the agent's iterations.

It does **not** replace your test runner. It wraps it.

---

## The six native test engines

novetest detects your ecosystem and shells out to its native engine.
Each engine has real constraints — novetest rejects unsupported
frameworks rather than guessing:

| Ecosystem | `engine_name` | Constraint | Coverage facts |
|---|---|---|---|
| python | `pytest` | — | yes |
| javascript-typescript | `jest` | — | yes |
| java | `junit` | JUnit 5 (Jupiter) only — JUnit 4 / TestNG are rejected | yes |
| go | `go-test` | — | **no** — Go tests run, but coverage is not consumed |
| rust | `cargo-test` | requires cargo-nextest | yes |
| dotnet | `xunit` | xUnit v2 only — NUnit / MSTest are rejected | yes |

Five of the six engines produce coverage facts; `go-test` runs tests
but does not yield coverage. The `engine_name` strings are literally
`pytest`, `jest`, `junit`, `go-test`, `cargo-test`, `xunit`.

---

## The analysis loop

`novetest test` chains a best-effort pipeline on top of the native run:

`Execute → Store → Structure → Compare → Locate → Recommend`

1. **Execute** — run your tests through the native engine, capture one
   standardized result.
2. **Store** — persist the run as a durable, citable Run Record under
   `.novetest/`.
3. **Structure (coverage)** — compute per-run coverage and cross-run
   coverage deltas (for the five coverage-bearing engines).
4. **Compare (regression)** — diff against the most recent prior run to
   surface newly-failing, fixed, and still-failing tests.
5. **Locate (localization)** — rank the most suspicious code locations
   for a failure via SBFL (statistical fault localization).
6. **Recommend** — assemble the facts into a short, prioritized,
   evidence-cited next step.

Steps 3–5 are best-effort: if a stage can't run, that stage is marked
`unavailable` and the workflow continues — only the native run itself
is fatal. A seventh capability, **replay** (re-executing a stored run
to confirm a failure reproduces), runs via the explicit `novetest
replay <run_id>` verb; it is not auto-run during `novetest test`.

Every facet above is callable today. Each run's facts feed the next, so
the analysis sharpens as your history grows.

---

## The contract you can rely on

1. **Every verb emits exactly one envelope** with the schema string
   `"novetest/v1"`. No multi-document output.
2. **The envelope shape is uniform.** Six top-level keys, always
   present, never renamed, emitted in sorted (alphabetical) order in
   JSON mode:

   ```json
   {
     "schema":   "novetest/v1",
     "command":  "<verb>",
     "ok":       true,
     "data":     { },
     "errors":   [],
     "warnings": []
   }
   ```

   There is **no** top-level `version`, `verb`, or `exit_code` field.
   `errors[]` / `warnings[]` items are each `{code, message, details}`.
3. **`ok` and exit code together encode the outcome.** `ok: true`
   means the CLI did its job. Exit code `0` means the user's tests also
   passed; exit code `3` means the user's tests failed — which is real
   product data, so `ok` stays `true`. `ok: false` always pairs with a
   non-zero exit and at least one entry in `errors[]` (e.g. exit `4`
   for an engine-missing / adapter error).
4. **Run IDs are stable references.** A 26-character ULID
   (`01KVYRJJ4PN2F6DPKW1FHD1SP6`) created by the run engine is the
   durable handle into the per-project store and never changes across
   invocations.
5. **Routing keys are closed taxonomies.**
   `recommendations[].category` (7 values, each with an integer
   `priority`, lower = higher priority — there is no `severity` field),
   `errors[].code`, and `warnings[].code` all come from documented
   enumerations. Pin against these strings, not against the
   human-readable `summary` / `message`.

The envelope is versioned by its own `schema` field: while it reads
`novetest/v1` the wire shape is frozen. Every envelope shown in these
docs is a real, byte-accurate capture from the CLI.

---

## Output modes and the default-mode rule

novetest emits the same envelope as either pretty text (default on a
TTY) or as JSON (default when stdout is piped or redirected). You
almost never have to override this.

| Where you are | Default | How to lock it explicitly |
|---|---|---|
| Interactive terminal (stdout is a TTY) | `text` | `novetest --output text <verb>` or `NOVETEST_OUTPUT=text` |
| Piped, redirected, or scripted | `json` | `novetest --output json <verb>` or `NOVETEST_OUTPUT=json` |
| Streaming many runs (CI log) | (opt-in) `ndjson` | `novetest --output ndjson <verb>` or `NOVETEST_OUTPUT=ndjson` |

Precedence (canonical Unix): **explicit `--output` flag >
`NOVETEST_OUTPUT` env > TTY auto-detect**. The `--output` flag is
global and may appear **anywhere** in the command line (it is stripped
before the verb is dispatched).

The `text` mode is a deterministic projection of the same envelope; the
JSON output is pretty-printed (indent 2, keys sorted alphabetically)
and NDJSON is one compact line per envelope.

::: tabs
@tab For human

You almost never need to think about this. Type `novetest test`,
read the pretty output, move on. If you ever want to see exactly
what your agent counterpart sees, run:

```bash
NOVETEST_OUTPUT=json novetest test | jq .
```

@tab For agent

Pin the output mode once at session start. You do NOT need
`--output json` on every invocation:

```bash
export NOVETEST_OUTPUT=json
novetest init
novetest test
novetest status
novetest inspect <run_id>
```

Or per-invocation if you need to override the env temporarily:

```bash
novetest --output json test
```

:::

---

## The text-mode glyph palette

Wherever the human-mode output uses a symbol, it comes from this
closed palette. No ANSI color at MVP — meaning is carried by glyphs
+ words.

| Glyph | When you see it | What it means |
|---|---|---|
| `✓` | `[all_green]`, "passed" status, available sub-reports | Good news / informational. No action required. |
| `✗` | A failing-run header, a regression summary, error envelopes | Bad news. Look here. |
| `—` | Sub-report availability (`status`, `inspect`) | Unavailable for a structural reason (no baseline yet, no failing tests, etc.). Not an error. |
| `⚠` | Trailing `warnings:` block | Advisory. Won't stop your work; might be worth investigating. |
| `!` | Action-needed recommendation categories (e.g. `[investigate_location]`) | Needs your attention. |
| `?` | Unavailable / "we can't tell" outcomes (e.g. replay) | Couldn't classify. Usually a structural or host-level limitation. |
| `·` | Separator | Just whitespace with a dot. |
| `↳` | Citation pointer | The recommendation is based on this thing. Often a `run_id`. |

(You will see these all over the human-mode samples in the rest of
these docs. There is no need to memorize them — most are
self-evident in context.)

---

## The working example used throughout these docs

To keep examples concrete, every page in this Docs set uses the same
tiny Python project — **`calc`** — as its running example.
Per-language equivalents appear on the
[Supported Languages](./supported-languages.md) page.

### Directory layout

```
calc-demo/
├── pyproject.toml
├── calc/
│   ├── __init__.py
│   └── arithmetic.py
└── tests/
    └── test_arithmetic.py
```

### Files

**`pyproject.toml`** (the pytest section is what matters)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

**`calc/__init__.py`** — empty.

**`calc/arithmetic.py`**

```python
def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b
```

**`tests/test_arithmetic.py`**

```python
from calc.arithmetic import add, subtract


def test_add_positive() -> None:
    assert add(2, 3) == 5


def test_add_zero() -> None:
    assert add(0, 0) == 0


def test_subtract() -> None:
    assert subtract(10, 4) == 6
```

A 3-test pytest suite. Green on the first run; we deliberately break
`subtract` (change `return a - b` to `return a + b`) in
[Understanding Results](./understanding-results.md) to show what a
failure looks like end-to-end — including SBFL pinning `subtract`@6.

### What you need on PATH

- `python` ≥ 3.11
- `pytest` (the native engine novetest shells out to)

The `novetest` binary bundles its **own** Python via PyApp; you do
**not** install Python for the CLI itself. The `python` and `pytest`
above are what novetest invokes in order to actually run your tests.

---

## Where to go next

The rest of these Docs follow the natural reading order:

1. **[Installation](./installation.md)** — one-line install for
   Linux / macOS / Windows; two sanity checks
   (`novetest --version`, `novetest --help`); environment overrides
   you almost never need.
2. **[Quick Start](./quick-start.md)** — the canonical happy path:
   `init` -> `test` -> read the recommendation -> (optional)
   `inspect`.
3. **[Supported Languages](./supported-languages.md)** — pytest /
   jest / go-test / cargo-test / JUnit / xUnit: prerequisites,
   project skeleton, per-engine quirks.
4. **[Understanding Results](./understanding-results.md)** — exit
   codes, reading text-mode output, the `recommendations[]` taxonomy,
   the `status` / `inspect` follow-up verbs.
5. **[Advanced Usage](./advanced-usage.md)** — the less-common verbs
   (`run`, `coverage show/diff`, `regression compare/latest`,
   `localization`, `replay`, `compare`, `memory list/show/delete`,
   `licenses`).
6. **[Troubleshooting](./troubleshooting.md)** — common errors and
   their one-line fixes.

If you already have novetest installed and just want the canonical
flow, [Quick Start](./quick-start.md) is the right entry point.
