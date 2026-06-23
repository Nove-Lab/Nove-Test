# Nove Test — AI Agent User Manual

You are an AI coding agent, a CI pipeline, or any non-interactive
caller. You need a stable, machine-parseable contract: predictable
exit codes, a frozen JSON envelope, deterministic routing keys.

This manual walks the **same 4-step workflow** as the human set, but
every example output is the literal `novetest/v1` JSON envelope and
every interpretation step is a deterministic branch on a structured
key.

> **Human at a terminal? Use the [human/](../human/README.md) set
> instead.** Same flow, same verbs, but examples are scannable text
> with glyph summaries.

---

## Reading order

| # | File | Purpose |
|---|---|---|
| 1 | [install.md](./install.md) | Install command, env var defaults, the two sanity envelopes (`version`, `help`) you should round-trip before doing anything else. |
| 2 | [quick-start.md](./quick-start.md) | The 4-step canonical workflow with the full envelope shape at every step. Decision-tree pseudocode for routing. |
| 3 | [languages.md](./languages.md) | Per-engine detection markers, ecosystem identifiers, per-test ID conventions, coverage report formats. |
| 4 | [after-test.md](./after-test.md) | Exit-code table, `errors[].code` catalog, `stage_eligibility` reading, `recommendations[]` routing, follow-up envelopes for `status` and `inspect`. |
| 5 | [advanced.md](./advanced.md) | Every non-happy-path verb with its envelope shape: `coverage show/diff`, `regression compare/latest`, `localization`, `replay`, `compare`, `memory list/show/delete`, `licenses`. |
| 6 | [troubleshooting.md](./troubleshooting.md) | Error envelopes by `code`, retry policy, when to abort, when to fix and re-invoke. |

---

## The contract you can rely on

Five invariants are pinned for the lifetime of `novetest/v1`:

1. **Every verb emits exactly one envelope.** No multi-document
   output. Schema string is always `"novetest/v1"`.
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

3. **`ok` and exit code together encode the outcome.**
   `ok: true` → CLI did its job. Exit code 0 means the user's tests
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

---

## Default invocation pattern for agents

Pin output mode once at session start, then call verbs normally:

```bash
export NOVETEST_OUTPUT=json
novetest init
novetest test
novetest status
novetest inspect <run_id>
```

Or, per invocation:

```bash
novetest --output json test
```

Precedence: **explicit `--output` flag > `NOVETEST_OUTPUT` env > TTY
auto-detect** (canonical Unix). Setting the env var is enough; you
do not need to pass `--output json` on every call.

`text` is the default on a TTY (humans get pretty output); `json` is
the default when stdout is piped or redirected. Both `text` and `json`
modes emit the same `novetest/v1` payload — the difference is whether
the renderer projects it through a glyph + sentence formatter (text
mode) or pretty-prints the raw envelope (`json` mode). `ndjson` packs
the same envelope onto a single line for log-friendly streaming.

The JSON / NDJSON byte shape is **snapshot-pinned in CI** — any drift
fails the release pipeline. You can rely on byte-identical output for
the same input.

---

## The working example used throughout this manual

To keep examples concrete, every page uses one tiny Python project as
its running example.

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

A 3-test green pytest suite. We deliberately break one in
[after-test.md](./after-test.md) to show the `tests_failed` envelope.

### What must be on PATH

- `python` ≥ 3.11
- `pytest` (`pip install pytest`)
- (optional, for the `coverage: "available"` branch) `pytest-cov`
  (`pip install pytest-cov`)

The `novetest` binary bundles its own Python via PyApp. The PATH-
resident `python` and `pytest` above are what Nove Test shells out
to in order to execute *your* tests.

---

## What to read next

[install.md](./install.md) — the one-line install plus the two
sanity envelopes you should round-trip before driving any real
project.
