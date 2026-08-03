# pytest-collection-error

Pytest-based fixture project whose test module **fails to parse**, so the suite
never executes at all. Used to validate that Nove Test never reports a
non-executing suite as green (delivery-phasing row 45).

## What this fixture validates

- `novetest test tests/` exits **3** and persists a Run Record with
  `status: "errored"`, `summary_counts == {"total": 0, "collected": 0}` and an
  empty `test_results`.
- `data.recommendations[0].category` is **`unavailable_analysis`**, never
  `all_green`.
- `warnings[]` carries exactly one `suite-did-not-execute` entry whose
  `details` name the status (`errored`) and the collected count (`0`).

## The intentional bug

`tests/test_calculator.py` line 21 reads `assert multiply(4, 5 == 20` — the
closing parenthesis is missing. `pytest` reports
`SyntaxError: '(' was never closed` during collection, collects zero tests and
exits 2. **Do not fix it**; the unparsable file is the fixture's contract.

A syntax error was chosen over the other realistic collection-time defect (a
bad module-scope import) deliberately: both normalize to the identical Run
Record shape, but a missing module can be silently "repaired" by an unrelated
package landing on `sys.path`, whereas a file that does not compile is broken
unconditionally, on every host, forever.

## Why this differs from the `zero-tests-collected` case

The Run engine already warns `zero-tests-collected` for a **clean** empty run —
an engine that executed, exited 0 (`status: "passed"`) and found no tests (a Go
package with no test functions). That run happened and found nothing. This
fixture's run **never happened**: `status: "errored"`, and nothing about the
project's correctness has been established. The two carry different warning
codes precisely so a consumer switching on `warnings[].code` can tell them
apart.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `test_add_returns_sum` | **never runs** — the module does not compile |
| `test_multiply_returns_product` | **never runs** — contains the defect |

Note that `test_add_returns_sum` is perfectly valid and would pass. It is here
to make the blast radius visible: one unparsable file takes down the tests that
have nothing wrong with them, which is why "0 failures" must never be read as
"all green".

## Layout

```
pytest-collection-error/
├── pyproject.toml
├── pytest_collection_error/
│   ├── __init__.py
│   └── calculator.py         # correct; never exercised
└── tests/
    └── test_calculator.py    # DOES NOT PARSE (the intentional defect)
```

## Isolation

Own `pyproject.toml`, no `novetest` import. The unparsable module is invisible
to this repo's own tooling by construction, verified: `pyproject.toml`'s
`norecursedirs = ["tests/fixtures"]` keeps the repo's pytest run out,
`[tool.mypy] packages = ["novetest"]` keeps type checking to `src/`, and
`[tool.hatch.build.targets.sdist] include` lists only `/src`, `/README.md`,
`/LICENSE`, `/NOTICES.md`, so no published artifact ships it.
