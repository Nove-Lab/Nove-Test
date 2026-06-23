# Nove Test — Human User Manual

You are a developer at a terminal. You typed `novetest test` and you
want a clear, scannable summary of what just happened — not a 60-line
JSON dump.

This manual walks you from "I just installed the binary" to "I can read
the output and act on the recommendations" without ever requiring you
to parse a single byte of JSON. Every example output on every page is
the **actual text** the CLI prints to your terminal in its default
human mode.

> **AI agent? Use the [agent/](../agent/README.md) set instead.**
> It mirrors this same flow but every example is a full `novetest/v1`
> JSON envelope and every interpretation step is deterministic
> machine routing.

---

## Reading order

| # | File | Read when … |
|---|---|---|
| 1 | [install.md](./install.md) | First. One curl-pipe-sh and two sanity checks (`--version`, `--help`). |
| 2 | [quick-start.md](./quick-start.md) | After install. The 4-step canonical workflow: `init` → `test` → read the recommendations → optional `inspect`. |
| 3 | [languages.md](./languages.md) | Your project is not Python. Per-engine toolchain notes for jest / go test / cargo / JUnit / dotnet. |
| 4 | [after-test.md](./after-test.md) | After `novetest test` returned a verdict. Exit-code table, reading text-mode output, when to reach for `status` and `inspect`. |
| 5 | [advanced.md](./advanced.md) | When the happy path's four verbs are not enough — `coverage diff`, `regression compare`, `localization`, `replay`, `memory` cleanup, `licenses`. |
| 6 | [troubleshooting.md](./troubleshooting.md) | When something goes wrong. Common error glyphs, their meaning, and the one-line fix. |

---

## What text mode actually looks like

This is the default when you type `novetest test` in a normal terminal:

```
1 recommendation · 1 category · run_id=01HX0K4M5N6P7Q8R9STUVWXYZ0

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01HX0K4M5N6P7Q8R9STUVWXYZ0
```

Things to notice — these are conventions you will see on every page:

- **`✓ ✗ — ⚠ ! ? · ↳`** — the entire glyph palette. `✓` is good, `✗` is bad, `—` is "unavailable for a structural reason", `⚠` is advisory, `!` is "needs action", `?` is "we are not sure", `·` is just a separator, `↳` points to a citation. No ANSI color at MVP — meaning is carried by glyphs + words.
- **Run IDs** are 26-character ULIDs (`01HX...`). They are the durable handle into your local run history. Copy-paste them into `novetest inspect <run_id>`.
- **Bracketed categories** (`[all_green]`, `[tests_failed]`, `[coverage_regressed]`, …) come from a closed taxonomy. They are stable across versions; humans and machines route off the same string.

You will see this shape over and over: a one-line summary, a blank,
then a glyph + bracketed category + sentence + optional `↳ citation`.

---

## The working example used throughout this manual

To keep the walkthrough concrete, every page uses one tiny Python
project as its running example. Each page on the [languages.md](./languages.md)
spread shows the equivalent skeleton for the other five engines.

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

A 3-test pytest suite. Greens on the first run; we'll deliberately
break one in [after-test.md](./after-test.md) to show what a failure
looks like in text mode.

### What you need on PATH

- `python` ≥ 3.11
- `pytest` (`pip install pytest`)
- (optional, for coverage) `pytest-cov` (`pip install pytest-cov`)

The `novetest` binary bundles its **own** Python via PyApp; you do
**not** install Python for the CLI itself. The `python` and `pytest`
above are what Nove Test shells out to in order to actually run your
tests.

---

## A note on what this manual does NOT do

- It does not teach you how to write Python or pytest tests. It assumes
  you have a project that already has tests.
- It does not document every flag of every native engine — those live
  in pytest / jest / cargo / JUnit / dotnet / go's own docs. Nove Test
  passes through the targets you give it.
- It does not cover the SBFL math behind fault localization. The
  [advanced.md](./advanced.md) page shows how to invoke it; the design
  rationale lives under `design/implementation-plan/`.
- It does not document the JSON envelope schema field-by-field. That
  is the agent set's job — see [agent/after-test.md](../agent/after-test.md)
  if you ever need to script Nove Test.

Next: [install.md](./install.md).
