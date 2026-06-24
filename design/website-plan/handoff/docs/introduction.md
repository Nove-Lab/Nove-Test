# Introduction

**novetest is a polyglot test orchestration CLI.** One binary wraps
six native test engines (pytest, jest, JUnit, go test, dotnet, cargo)
behind a single command surface. Every verb persists a Run Record,
derives coverage / regression / fault-localization facts, and
synthesizes an actionable recommendation — all under one stable JSON
contract called `novetest/v1`.

This page covers the conceptual model you need before
[installing](./installation.md) the binary: who novetest is for, what
the contract looks like, the working example used throughout these
docs, and where to go next.

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
analysis (what regressed, where the fault is, whether a failure is
flaky) usually lives far away in a CI pipeline, too slow and too
distant for an AI agent's fast inner loop.

novetest closes that gap. It is the **AI-facing testing
infrastructure** that sits on top of the engines you already use,
so testing becomes a **cumulative, machine-readable loop that runs
locally** — in cadence with the agent's iterations.

It does **not** replace your test runner. It wraps it.

---

## The six engines, one loop

novetest is a system of six engines that continuously interact:

| Engine | What it does | Maturity |
|---|---|---|
| **Run** | Executes your tests through the native engine (pytest / jest / JUnit / go test / dotnet / cargo nextest) and emits one standardized result. | Live |
| **Memory** | Stores every run as a durable, citable Run Record under `.novetest/`. | Live |
| **Coverage** | Structures what each test exercised; computes per-run coverage and cross-run coverage deltas. | Live |
| **Regression** | Compares runs to surface new failures, fixed failures, and behavior diffs. | Live |
| **Localization** | Ranks the most suspicious code locations for a failure via SBFL (statistical fault localization). | Live |
| **Replay** | Re-executes a stored run to tell a stable failure from a flaky one. | Building |
| **Recommendation** (layer, not an engine) | Assembles all the facts into a short, prioritized, evidence-cited next step. | Building (facts are Live; end-to-end synthesis is in progress) |

The loop: `Execute -> Store -> Structure -> Compare -> Locate ->
Validate -> Recommend`. Each run's facts feed the next, so the
analysis gets sharper as you go.

---

## The contract you can rely on

Five invariants are pinned for the lifetime of `novetest/v1`:

1. **Every verb emits exactly one envelope** with the schema string
   `"novetest/v1"`. No multi-document output.
2. **The envelope shape is uniform.** Six top-level keys, always
   present, never renamed:

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

3. **`ok` and exit code together encode the outcome.** `ok: true`
   means the CLI did its job. Exit code 0 means the user's tests
   also passed; exit code 3 means the user's tests failed (which is
   real product data, not a tooling error). `ok: false` always pairs
   with a non-zero exit and at least one entry in `errors[]`.
4. **Run IDs are stable references.** A 26-character ULID
   (`01ARZ3NDEKTSV4RRFFQ69G5FAV`) created by the Run engine is the
   durable handle into the per-project store and never changes
   across invocations.
5. **Routing keys are closed taxonomies.**
   `recommendations[].category`, `errors[].code`, and
   `warnings[].code` all come from documented enumerations. New
   values may be added in `novetest/v1`; existing values never
   change semantics. Pin against these strings, not against the
   human-readable `summary` / `message`.

The full envelope schema is published as JSON Schema in the
repository (see [Installation](./installation.md) for the link).

---

## Output modes and the default-mode rule

novetest emits the same envelope as either pretty text (default on a
TTY) or as JSON (default when stdout is piped or redirected). You
almost never have to override this.

| Where you are | Default | How to lock it explicitly |
|---|---|---|
| Interactive terminal (stdout is a TTY) | `text` | `novetest <verb> --output text` or `NOVETEST_OUTPUT=text` |
| Piped, redirected, or scripted | `json` | `novetest <verb> --output json` or `NOVETEST_OUTPUT=json` |
| Streaming many runs (CI log) | (opt-in) `ndjson` | `novetest <verb> --output ndjson` or `NOVETEST_OUTPUT=ndjson` |

Precedence (canonical Unix): **explicit `--output` flag >
`NOVETEST_OUTPUT` env > TTY auto-detect**.

The `text` mode is a deterministic projection of the same envelope;
the JSON / NDJSON byte shape is the **frozen wire contract** and is
snapshot-pinned in CI — any drift fails the release pipeline.

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

You can rely on byte-identical output for the same input — useful
for memoization, content-addressed caches, and contract tests in
your agent.

:::

---

## The 7-glyph text-mode palette

Wherever the human-mode output uses a symbol, it comes from this
closed palette. No ANSI color at MVP — meaning is carried by glyphs
+ words.

| Glyph | When you see it | What it means |
|---|---|---|
| `✓` | `[all_green]`, "passed" status, available sub-reports | Good news / informational. No action required. |
| `✗` | `[tests_failed]`, regression summary, error envelopes | Bad news. Look here. |
| `—` | Sub-report availability (`status`, `inspect`) | Unavailable for a structural reason (no baseline yet, no failing tests, etc.). Not an error. |
| `⚠` | Trailing `warnings:` block | Advisory. Won't stop your work; might be worth investigating. |
| `!` | Recommendation categories that need action | Needs your attention. |
| `?` | Replay-specific "we can't tell" outcome | Replay couldn't classify reproducibility. Usually means a host-level limitation. |
| `·` | Separator | Just whitespace with a dot. |
| `↳` | Citation pointer | The recommendation is based on this thing. Often a `run_id`. |

(You will see these all over the human-mode samples in the rest of
these docs. There is no need to memorize them — most are
self-evident in context.)

---

## The working example used throughout these docs

To keep examples concrete, every page in this Docs set uses the same
tiny Python project as its running example. Per-language equivalents
(jest, go, cargo, JUnit, dotnet) appear on the
[Supported Languages](./supported-languages.md) page.

### Directory layout

```
my-project/
├── pyproject.toml
├── my_module/
│   ├── __init__.py
│   └── math_utils.py
└── tests/
    └── test_math_utils.py
```

### Files

**`pyproject.toml`**

```toml
[project]
name = "my-project"
version = "0.0.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

**`my_module/__init__.py`** — empty.

**`my_module/math_utils.py`**

```python
def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b
```

**`tests/test_math_utils.py`**

```python
from my_module.math_utils import add, subtract


def test_add_positive() -> None:
    assert add(2, 3) == 5


def test_add_zero() -> None:
    assert add(0, 0) == 0


def test_subtract() -> None:
    assert subtract(10, 4) == 6
```

A 3-test pytest suite. Green on the first run; we deliberately
break one in [Understanding Results](./understanding-results.md) to
show what a failure looks like end-to-end.

### What you need on PATH

- `python` ≥ 3.11
- `pytest` (`pip install pytest`)
- (optional, for coverage) `pytest-cov` (`pip install pytest-cov`)

The `novetest` binary bundles its **own** Python via PyApp; you do
**not** install Python for the CLI itself. The `python` and `pytest`
above are what novetest shells out to in order to actually run your
tests.

---

## Where to go next

The rest of these Docs follow the natural reading order:

1. **[Installation](./installation.md)** — one-line install for
   Linux / macOS / Windows; two sanity checks
   (`novetest --version`, `novetest --help`); environment overrides
   you almost never need.
2. **[Quick Start](./quick-start.md)** — the canonical 4-step happy
   path: `init` -> `test` -> read the recommendation -> (optional)
   `inspect`.
3. **[Supported Languages](./supported-languages.md)** — pytest /
   jest / go test / cargo nextest / JUnit / dotnet: prerequisites,
   project skeleton, per-engine quirks.
4. **[Understanding Results](./understanding-results.md)** — exit
   codes, reading text-mode output, the `recommendations[]` taxonomy,
   the `status` / `inspect` follow-up verbs.
5. **[Advanced Usage](./advanced-usage.md)** — the ten less-common
   verbs (`run`, `coverage show/diff`, `regression compare/latest`,
   `localization`, `replay`, `compare`, `memory list/show/delete`,
   `licenses`).
6. **[Troubleshooting](./troubleshooting.md)** — common errors and
   their one-line fixes.

If you already have novetest installed and just want the canonical
flow, [Quick Start](./quick-start.md) is the right entry point. If
you'd like to skim what novetest can do first,
[Advanced Usage](./advanced-usage.md) is the most data-dense page.
