# pytest-failing

Pytest-based fixture project containing one intentional bug, used to validate Nove Test's failed-test capture path.

## What this fixture validates

- `assess_engine_readiness` should classify this workspace as `ready` with pytest detected.
- `novetest run tests/` should complete with a non-zero native pytest exit code but a successful Nove Test envelope (the run was executed and observed — the failure is in the SuT, not in Nove Test).
- The persisted Run Record must capture the failing `Test Result` with:
  - `nodeid` resolving to `tests/test_counter.py::test_count_up_to_includes_endpoint`
  - `status: failed`
  - a failure reference handle (message / traceback location) preserved for later `inspect` / `localization` consumption.
- `novetest memory show <run_id>` must surface the failed test in the normalized summary counts.

## The intentional bug

`pytest_failing.counter.count_up_to(n)` returns `list(range(1, n))` instead of `list(range(1, n + 1))` — a classic off-by-one. The bug is the fixture's contract; **do not fix it**.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `test_count_up_to_includes_endpoint` | **failed** (the off-by-one detector) |
| `test_count_up_to_starts_at_one` | passed |
| `test_is_even_true` | passed |
| `test_is_even_false` | passed |

## Layout

```
pytest-failing/
├── pyproject.toml
├── pytest_failing/
│   ├── __init__.py
│   └── counter.py            # contains the intentional off-by-one
└── tests/
    └── test_counter.py       # 1 failing + 3 passing tests
```

## Isolation

Own `pyproject.toml`, no `novetest` import. Same plugin-autoload-disabled rule as `pytest-basic/` (see `foundations.md` §6).
