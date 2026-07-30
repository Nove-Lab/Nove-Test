# localization-colocated-tests

Pytest fixture project where **one file holds production code and collected
tests**. It pins the false negative the first cut of the SBFL test-file
exclusion introduced (Manual Test L1 finding, 2026-07-30, issue 2).

## Layout

```
pyproject.toml        python_files = ["*.py"]  ← makes pytest collect from any module
colocated/helpers.py  discount(), tax()        ← correct, called only from totals.py
colocated/totals.py   invoice_total()          ← THE DEFECT: taxes the undiscounted subtotal
                      test_total_no_discount_no_tax()   (passes)
                      test_total_discount_with_tax()    (fails)
```

`python_files = ["*.py"]` is a real, if minority, pytest configuration. The
same *shape* is the native layout in Rust (`#[cfg(test)] mod tests`) and
common in Go — those ecosystems escape the problem today only because their
node ids carry no file path, so the filter no-ops there entirely.

## What it demonstrates

Run `novetest test colocated/` then `novetest localization latest`.

| filter | ranking |
| --- | --- |
| file-granular (`088091e`) | `colocated/helpers.py::discount`, `::tax` — **the defect is gone**, `test_file_exclusion_reverted: false` |
| symbol-granular (today) | `colocated/totals.py::invoice_total` back at rank 1, tied with the two helpers; only the two `test_*` functions are excluded |

The revert cannot rescue this: it fires only when *no* candidate anywhere
scores positive, and `colocated/helpers.py` does. Whole-file exclusion
therefore deleted a real suspect silently, with every metadata key reading
healthy.

Ochiai counts (2 tests, 1 failing): every symbol the failing test touches is
`ef = 1, ep = 1` → 0.7071, while the failing test's own body is
`ef = 1, ep = 0` → 1.0. The three surviving suspects tie at rank 1.
