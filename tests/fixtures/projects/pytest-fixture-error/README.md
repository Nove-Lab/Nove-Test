# pytest-fixture-error

Pytest-based fixture project whose tests **error inside a pytest fixture** — in
setup in one module, in teardown in another. The suite *executes*; it just
establishes nothing. Used to validate that Nove Test never reports a suite whose
tests errored as green (delivery-phasing row 49, the direct successor to row 45).

## Why it exists

`pytest-collection-error` covers the suite that never *ran* (`status: "errored"`,
zero results, exit 3). This fixture covers the suite that ran, produced results,
and still proves nothing: pytest-json-report labels a setup/teardown failure with
the singular outcome `"error"`, and before the row-49 fix the pytest normalizer
copied that string through verbatim. `"error"` is not in
`FAIL_LIKE_OUTCOMES = {"failed", "errored"}`, so the run aggregated to
`status: "passed"` and `novetest test` answered `[all_green] … (passed 1,
skipped 0, total 2)` at **exit 0** — no bad exit code, no warning, nothing.

The fix maps pytest's own outcome vocabulary at the adapter boundary
(`run/normalizer.py::_map_pytest_outcome`, `"error" -> "errored"`), the same way
the jest / go-test / cargo paths already did. This fixture is what keeps it
fixed.

## What this fixture validates

Per module (each is targeted individually — see "How to run it" below):

| Module | Raw pytest | `RunRecord.status` | Per-test outcomes |
| --- | --- | --- | --- |
| `tests/test_setup_error.py` | `1 passed, 1 error`, exit 1 | **`failed`** | `errored`, `passed` |
| `tests/test_teardown_error.py` | `1 passed, 1 error`, exit 1 | **`failed`** | `errored` |
| `tests/test_error_and_failure.py` | `1 failed, 1 error`, exit 1 | **`failed`** | `errored`, `failed` |
| `tests/` (whole suite) | `1 failed, 2 passed, 3 errors`, exit 1 | **`failed`** | 3×`errored`, 1×`failed`, 1×`passed` |

- No shape here may ever produce `status: "passed"`, and
  `data.recommendations[0].category` may never be `all_green`.
- `novetest run <module>` exits **3** (a persisted, honest, non-green user
  result — not an error envelope: `ok` stays `true`).
- The third module is the row of the blast-radius table that was **already
  correct before the fix** (one genuine `failed` test makes the run non-green on
  its own). It is pinned here so the mapping change cannot silently move it.

## The intentional bugs

Three, all in the test modules' pytest fixtures, none in `pytest_fixture_error/`:

1. `test_setup_error.py::warehouse_connection` raises `RuntimeError` — the test
   that requests it errors during **setup** and its body never runs.
2. `test_teardown_error.py::warehouse_session` yields, then raises — the test
   body passes and the error arrives during **teardown**.
3. `test_error_and_failure.py::test_reorder_quantity_wrong_expectation` asserts
   `reorder_quantity(2, 10) == 99` when the (correct) answer is `8` — a genuine
   assertion **failure** sitting next to an error.

**Do not fix any of them**; they are the fixture's contract. `inventory.py` is
correct and stays correct — the wrong expectation lives in the test, so this
fixture has a `failed` outcome without a buggy production module.

## Why setup AND teardown

They are two different pytest phases and one shared reporting shape, and both
were silently green before the fix. A setup error means the test body never ran;
a teardown error means it ran and passed, and then the world fell over
afterwards. pytest-json-report resolves the whole test item to the non-passing
category in both cases, so both arrive at the normalizer as outcome `"error"` —
which is exactly why one mapping table covers both. Note that the teardown
module's report `summary` block carries **no `passed` key at all**
(`{"collected": 1, "error": 1, "total": 1}`), even though pytest's own terminal
line says "1 passed, 1 error".

## How to run it

Target the modules **individually**. A whole-`tests/` run mixes the shapes and
its one genuine `failed` test would mask a regression in the error handling —
the very masking this fixture exists to make impossible:

```
novetest run tests/test_setup_error.py        # errored + passed, no `failed`
novetest run tests/test_teardown_error.py     # errored only
novetest run tests/test_error_and_failure.py  # errored + failed (control)
```

## Layout

```
pytest-fixture-error/
├── pyproject.toml
├── pytest_fixture_error/
│   ├── __init__.py
│   └── inventory.py                  # correct; the defects are NOT here
└── tests/
    ├── test_setup_error.py           # fixture raises during setup
    ├── test_teardown_error.py        # fixture raises during teardown
    └── test_error_and_failure.py     # setup error + a real assertion failure
```

## Isolation

Own `pyproject.toml`, no `novetest` import. Same plugin-autoload-disabled rule as
`pytest-basic/` (see `foundations.md` §6): the repo's own pytest run never
recurses into it (`norecursedirs = ["tests/fixtures"]`), `[tool.mypy] packages =
["novetest"]` keeps type checking to `src/`, and the sdist ships only `/src`.
