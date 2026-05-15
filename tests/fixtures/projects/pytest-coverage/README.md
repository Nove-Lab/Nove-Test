# pytest-coverage

Pytest-based fixture project used by Nove Test to validate the Run engine's
coverage-emission path (Phase 2 entry).

## What this fixture validates

- The pytest adapter, invoked with `collect_coverage=True`, must emit:
  - `native/coverage.json` (coverage.py JSON report with per-line `contexts`)
  - `native/coverage.xml` (Cobertura XML; interop safety net)
- The `coverage.json` `files` map must include `pytest_coverage/classifier.py`
  and that entry's `contexts` map must be non-empty, keyed by the test
  nodeid coverage.py records (per-test attribution proves `--cov-context=test`
  and `show_contexts=True` are both in effect).
- `pytest_coverage/classifier.py`'s third branch (`value < 0`) is **not**
  exercised by the test suite, so `missing_lines` and/or `missing_branches`
  for that file must be non-empty — proof for the Coverage engine that the
  emitted artifact carries the uncovered-branch evidence it needs.

## The deliberate gap

`pytest_coverage.classifier.classify(value)` has three branches: positive,
zero, negative. The test suite covers only positive and zero. The negative
branch is the fixture's contract — **do not "fix" the test suite by adding
a negative-value test**.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `test_classify_positive` | passed |
| `test_classify_zero` | passed |

(No failing tests — coverage gaps are the fixture's only signal.)

## Layout

```
pytest-coverage/
├── pyproject.toml
├── pytest_coverage/
│   ├── __init__.py
│   └── classifier.py        # three branches, one intentionally uncovered
└── tests/
    └── test_classifier.py   # 2 passing tests covering 2 of 3 branches
```

## Isolation

Own `pyproject.toml`, no `novetest` import. The child pytest runs with
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` (see `foundations.md` §6); the adapter
explicitly loads `pytest_jsonreport` and `pytest_cov` via `-p` so the
fixture is hermetic from the parent dev venv.
