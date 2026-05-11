# pytest-basic

Minimal pytest-based fixture project used by Nove Test as software under test.

## What this fixture validates

A clean happy-path Run + Memory loop with the pytest Native Engine:

- `assess_engine_readiness` should classify this workspace as `ready` with pytest detected.
- `novetest run tests/` should succeed: 3 passing tests, no failures.
- A Run Record should be persisted under `.novetest/memory/runs/.../record.json` with a stable Run Reference; native artifacts under `.novetest/run/artifacts/.../`.
- `novetest memory list` / `memory show` should return this run with the derived-fact availability flags all set to `false`.
- `novetest test tests/` should yield an `all_green` recommendation once the integrated workflow lands.

## Layout

```
pytest-basic/
├── pyproject.toml         # pytest dev-group only; no novetest import
├── pytest_basic/
│   ├── __init__.py
│   └── math_utils.py      # add, subtract
└── tests/
    └── test_math_utils.py # 3 passing tests
```

## Isolation

The fixture has its own `pyproject.toml` and does not import any `novetest` code. When invoked by Nove Test's adapter the child pytest must run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `cwd=` this directory so it does not inherit the parent repo's dev venv plugins (see `design/implementation-plan/foundations.md` §6).
