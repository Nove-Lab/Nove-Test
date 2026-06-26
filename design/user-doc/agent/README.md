# Nove Test — AI Agent User Manual

You are an AI coding agent, a CI pipeline, or any non-interactive
caller. You need a stable, machine-parseable contract: predictable
exit codes, a frozen JSON envelope, deterministic routing keys.

This manual walks the **same workflow** as the human set, but every
example output is the literal `novetest/v1` JSON envelope and every
interpretation step is a deterministic branch on a structured key.

> **Human at a terminal? Use the [human/](../human/README.md) set
> instead.** Same flow, same verbs, but examples are scannable text
> with glyph summaries.

---

## Reading order

| # | File | Purpose |
|---|---|---|
| 1 | [install.md](./install.md) | Install command, env var defaults, the two sanity envelopes (`version`, `help`) you should round-trip before doing anything else. |
| 2 | [quick-start.md](./quick-start.md) | The canonical workflow with the full envelope shape at every step. Decision-tree pseudocode for routing. |
| 3 | [languages.md](./languages.md) | Per-engine detection markers, `engine_name` strings, per-test ID conventions, coverage availability. |
| 4 | [after-test.md](./after-test.md) | Exit-code table, `errors[].code` catalog, `stage_eligibility` reading, `recommendations[]` routing, follow-up envelopes for `status` and `inspect`. |
| 5 | [advanced.md](./advanced.md) | Every non-happy-path verb with its envelope shape: `coverage show/diff`, `regression compare/latest`, `localization`, `replay`, `compare`, `memory list/show/delete`, `licenses`. |
| 6 | [troubleshooting.md](./troubleshooting.md) | Error envelopes by `code`, retry policy, when to abort, when to fix and re-invoke. |

---

## The contract you can rely on

1. **Every verb emits exactly one envelope.** No multi-document
   output. The schema string is always `"novetest/v1"`.
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
   `errors[]` / `warnings[]` items are `{code, message, details}`.

3. **`ok` and exit code together encode the outcome.**
   `ok: true` → the CLI did its job. Exit `0` means the user's tests
   also passed; exit `3` means the user's tests **failed** — which is
   real product data, so `ok` is still `true`. `ok: false` always pairs
   with a non-zero exit and at least one entry in `errors[]` (e.g. exit
   `4` for an engine-missing / adapter error, exit `2` for usage).

4. **Run IDs are stable references.** A 26-character ULID
   (`01KVYRJJ4PN2F6DPKW1FHD1SP6`) created by the run engine is the
   durable handle into the per-project store and never changes across
   invocations.

5. **Routing keys are closed taxonomies.**
   `recommendations[].category` (7 values, each with an integer
   `priority`, lower = higher priority), `errors[].code`, and
   `warnings[].code` all come from documented enumerations. Pin against
   these strings, not against the human-readable `summary` / `message`.
   There is **no** `severity` field — ranking is `priority`.

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

Or, per invocation (the `--output` flag is global and may appear
**anywhere** in argv — it is stripped before the verb is dispatched):

```bash
novetest --output json test
```

Precedence: **explicit `--output` flag > `NOVETEST_OUTPUT` env > TTY
auto-detect**. `text` is the default on a TTY (humans get pretty
output); `json` is the default when stdout is piped or redirected. JSON
is pretty-printed (indent 2, sorted keys); `ndjson` packs the same
envelope onto a single compact line for log-friendly streaming.

A real `novetest test` envelope for the all-green working example:

```json
{
  "command": "test",
  "data": {
    "recommendation_schema_version": 1,
    "recommendations": [
      {
        "category": "all_green",
        "priority": 7,
        "summary": "All tests green; no action recommended (passed 3, skipped 0, total 3)."
      }
    ],
    "run_reference": {
      "created_at": 1782370093639,
      "run_id": "01KVYRJJJ75ZRHC05GNKYRK99S",
      "schema_version": 1
    },
    "stage_eligibility": {
      "coverage": "available",
      "localization": "unavailable",
      "regression": "available",
      "replay": "not_run"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

(Each `recommendations[]` item actually carries six keys —
`recommendation_id`, `category`, `priority`, `summary`, `slots`,
`evidence_citations`; the slots/citations are elided here. See
[after-test.md](./after-test.md) for the full shape.)

---

## The working example used throughout this manual

Every page uses one tiny Python project — **`calc`** — as its running
example so all envelopes are real and consistent.

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

A 3-test green pytest suite. We deliberately break `subtract` (change
`return a - b` to `return a + b`) in [after-test.md](./after-test.md) to
show the exit-3 failure envelope and the `investigate_location`
recommendations SBFL produces.

### What must be on PATH

- `python` ≥ 3.11
- `pytest` (the native engine Nove Test shells out to)

The `novetest` binary bundles its own Python via PyApp. The
PATH-resident `python` and `pytest` above are what Nove Test invokes to
execute *your* tests.

---

## What to read next

[install.md](./install.md) — the one-line install plus the two
sanity envelopes you should round-trip before driving any real
project.
