# localization-no-coverage

Pytest fixture project used by Nove Test's Localization engine to validate
the **`failure_proximity` mode** — the no-coverage fallback ranking.

## What this fixture validates

- Running the test target WITHOUT `--coverage` (so no per-test, per-test-file,
  or aggregate coverage facts are produced) still yields a `LocalizationFinding`.
- The mode is `failure_proximity`; `confidence` is `"low"`.
- The failing test's `failure_reference` points at the buggy SuT file (the
  exception originates inside the SuT, so pytest's `crash.path` resolves
  to `localization_no_coverage/statistics.py`).
- The buggy SuT file is ranked top-1 in the failure_proximity output.

## The deliberate gap

`localization_no_coverage.statistics.average(numbers)` divides `sum(numbers)`
by `len(numbers)` without guarding the empty-list case. The test
`test_average_of_empty_returns_zero` calls `average([])`, which raises
`ZeroDivisionError` inside the SuT — pytest's failure capture identifies
the **SuT file** as the crash site, so the inline `failure_reference`
emitted by the pytest adapter contains `localization_no_coverage/statistics.py:N: ...`.

The `failure_proximity` parser picks up that pattern and ranks the SuT file
ahead of the test file (which is also mentioned in pytest's longrepr).

**Do not "fix" the bug** — the fixture's contract is the bug.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `test_sum_returns_total` | passed |
| `test_max_returns_largest` | passed |
| `test_average_of_empty_returns_zero` | **failed** (ZeroDivisionError from SuT) |

## Layout

```
localization-no-coverage/
├── pyproject.toml
├── localization_no_coverage/
│   ├── __init__.py
│   └── statistics.py        # 3 functions; ``average`` raises on empty input
└── tests/
    └── test_statistics.py   # 3 tests; ``test_average_of_empty_returns_zero`` fails
```

## Isolation

Own `pyproject.toml`, no `novetest` import. Same hermetic discipline as the
other fixture projects under `tests/fixtures/projects/`.
