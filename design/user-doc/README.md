# Nove Test — User Document (MVP, happy-case)

Nove Test is a **polyglot test orchestration CLI** that wraps your
native test runner (pytest, jest, `go test`, `cargo nextest`, JUnit,
xUnit) behind a single AI-friendly command surface. Every command
emits a structured JSON envelope (`schema: "novetest/v1"`) suitable
for direct consumption by an AI agent. This document walks an
AI-agent user from a fresh shell to a complete pass through the
canonical orchestration workflow.

> **Audience.** AI agents (or humans) who just downloaded the
> `novetest` binary and want to be productive in the first 5
> minutes. We cover the happy path; we do not cover every flag.
> See [advanced-cli-memo.md](./advanced-cli-memo.md) for the list
> of deeper verbs reserved for the (forthcoming) advanced user
> document.

---

## What "MVP happy case" means

- **Linux + macOS** are first-class targets. Windows install is
  deferred to post-MVP (the binary builds for Windows but the
  POSIX install script does not yet have a `install.ps1` sibling;
  if you are on Windows, the CLI still works once the binary is
  on your PATH).
- The **canonical workflow** is a single command:
  `novetest test [<target>]`. It runs your tests, derives coverage
  facts, derives a regression delta vs the previous baseline,
  derives an SBFL-based fault localization ranking, and synthesizes
  a recommendation — all in one shot, exit code routed to whether
  your tests passed or failed.
- All other verbs (`run`, `coverage show`, `regression compare`,
  `localization`, `replay`, `memory list`, `inspect`, `status`,
  `compare`) are documented one-line each in
  [advanced-cli-memo.md](./advanced-cli-memo.md). They are not
  required for the happy path; `novetest test` already invokes
  the underlying engines in the right order.

---

## Reading order

| # | File | When to read |
|---|---|---|
| 1 | [install.md](./install.md) | First. One curl-pipe-sh and two sanity-check commands. |
| 2 | [quick-start.md](./quick-start.md) | The 4-step canonical happy path with full envelope examples. Read this end-to-end before anything else. |
| 3 | [languages.md](./languages.md) | When your project is not Python. Each of pytest / jest / gotest / cargo / junit / xunit has its own short subsection covering toolchain prerequisites and per-language quirks. |
| 4 | [after-test.md](./after-test.md) | When `novetest test` has returned an envelope and you need to act on the recommendations, dig into a single run, or audit the cache. |
| 5 | [advanced-cli-memo.md](./advanced-cli-memo.md) | When you suspect you need a deeper verb than the happy path covers. Pointers only; full advanced doc is a separate future deliverable. |

---

## The working example (used throughout this document)

To keep the walkthrough concrete, the document uses a single tiny
project as its running example. All command outputs and envelope
shapes shown later are what the CLI would emit for this project.

The example is a Python + pytest project, which we use as the
**language-agnostic baseline**. [languages.md](./languages.md)
shows the equivalent skeleton for the other five engines.

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

This gives you a 3-test suite that should pass green out of the
box. The same flow scales to any pytest-compatible suite (and
analogously to the other five test engines covered in
`languages.md`).

### What you need on PATH for this example

- `python` ≥ 3.11
- `pytest` (e.g. `pip install pytest`) — the `novetest run`
  engine readiness probe will tell you precisely what is missing
  if you skip this.

`novetest` itself bundles its own Python runtime via PyApp, so
the system Python the CLI uses for **its own logic** is the
bundled one. The PATH-resident `python` and `pytest` above are
what the CLI shells out to in order to **execute your tests**.

---

## What this document explicitly does NOT cover

- Producing recommendations from intentionally-failing suites
  (we only show the all-green happy case).
- Tuning the SBFL formula (`--formula ochiai|op2|dstar2|tarantula`)
  or the top-N rank cap.
- Cross-run comparisons via `compare` or `coverage diff`.
- Replay-based flakiness investigation (`replay --reruns N`).
- The CI-friendly `--output ndjson` mode for streaming envelopes.
- Tombstone-aware history queries via `memory list/show/delete`.

All of these live in `advanced-cli-memo.md` as one-line pointers
to the future advanced user document.
