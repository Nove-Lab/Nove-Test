# localization-shared-defect

Pytest fixture project that reproduces the **SBFL test-file bias** in its
undisguised form: the failing tests' own bodies outscore the actual defect
under Ochiai, so an unfiltered ranking puts non-actionable test code at
rank 1.

## Why this fixture exists alongside `localization-branch`

`localization-branch` has ONE failing test and a defect line touched by no
passing test, so the defect and the failing test's own body both score
Ochiai 1.0 and **tie** at rank 1 — the defect only prints first because the
tie-break sorts by file path and `localization_branch/` < `tests/`. The bias
is present there but masked.

This fixture removes the mask, matching the shape observed in wave-1 persona
P1 (`agent-comms/findings/eval-wave1-2026-07-28-scorecard.md` F2):

- **two** failing tests, so a single failing test's own body has `nf = 1`;
- the defect line is executed by passing tests too, so it carries `ep > 0`.

With per-test coverage over 7 tests (2 failing, 5 passing):

| location | `ef` | `ep` | `nf` | `np` | Ochiai |
| --- | --- | --- | --- | --- | --- |
| a failing test's own body (`tests/test_totals.py`) | 1 | 0 | 1 | 5 | **0.7071** |
| `shared_defect/totals.py::invoice_total` (the defect) | 2 | 3 | 0 | 2 | 0.6325 |
| `shared_defect/tax.py::compute_tax` | 2 | 4 | 0 | 1 | 0.5774 |
| `shared_defect/discounts.py::compute_discount` | 2 | 4 | 0 | 1 | 0.5774 |

`ep = 0` beats `ef = 2` under Ochiai: a failing test's body is executed by
exactly one failing test and by no passing test, by construction, on every
project. Excluding locations whose file owns a discovered test node puts
`invoice_total` at rank 1.

## The deliberate gap

`shared_defect.totals.invoice_total` taxes the **undiscounted** subtotal —
the taxable base should be `subtotal - discount`. The bug is invisible unless
both a discount and a tax rate are non-zero, which is why three of the five
totals tests pass while executing the same line.

**Do not "fix" the bug** — the fixture's contract is the bug.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `tests/test_totals.py::test_total_no_discount_no_tax` | passed |
| `tests/test_totals.py::test_total_tax_only` | passed |
| `tests/test_totals.py::test_total_discount_only` | passed |
| `tests/test_totals.py::test_total_percentage_discount_with_tax` | **failed** |
| `tests/test_totals.py::test_total_larger_discount_with_tax` | **failed** |
| `tests/test_helpers.py::test_discount_is_a_percentage_of_the_subtotal` | passed |
| `tests/test_helpers.py::test_tax_is_a_percentage_of_the_taxable_base` | passed |

## Layout

```
localization-shared-defect/
├── pyproject.toml
├── shared_defect/
│   ├── __init__.py
│   ├── discounts.py      # correct
│   ├── tax.py            # correct
│   └── totals.py         # holds the seeded one-line defect
└── tests/
    ├── test_totals.py    # 5 tests; 2 fail
    └── test_helpers.py   # 2 tests; both pass
```

## Isolation

Own `pyproject.toml`, no `novetest` import. Same hermetic discipline as the
other `tests/fixtures/projects/*` fixtures.
