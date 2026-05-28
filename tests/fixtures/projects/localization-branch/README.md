# localization-branch

Pytest fixture project used by Nove Test's Localization engine to validate
end-to-end SBFL derivation against a real `coverage.py` per-test payload.

## What this fixture validates

- The pytest adapter, invoked with `collect_coverage=True`, must emit a
  `coverage.json` whose `files` block carries non-empty `contexts` keyed by
  the test node IDs (per-test attribution).
- `derive_localization_findings` against the resulting Run Record + per-
  test `CoverageFactSet` ranks the deliberately-buggy function top-1 under
  Ochiai.

## The deliberate gap

`localization_branch.calculator.divide(a, b)` returns `a + b` instead of
`a / b`. The corresponding `test_divide_yields_quotient` test fails; every
other test passes. The failing test is the only test that executes
`divide`'s line, so the SBFL engine's per-test Ochiai score for that line
is 1.0 and it ranks top-1.

**Do not "fix" the bug** — the fixture's contract is the bug.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `test_add_sums_two_numbers` | passed |
| `test_subtract_yields_difference` | passed |
| `test_multiply_yields_product` | passed |
| `test_divide_yields_quotient` | **failed** |
| `test_negate_flips_sign` | passed |
| `test_counter_increments_monotonically` | passed |

## Layout

```
localization-branch/
├── pyproject.toml
├── localization_branch/
│   ├── __init__.py
│   └── calculator.py        # 5 functions + 1 class with 1 method; ``divide`` is the bug
└── tests/
    └── test_calculator.py   # 6 tests; ``test_divide_yields_quotient`` fails
```

## Isolation

Own `pyproject.toml`, no `novetest` import. Same hermetic discipline as the
other `tests/fixtures/projects/*` fixtures.
