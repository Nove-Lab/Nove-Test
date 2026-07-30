# localization-wrong-expectation

Pytest fixture project where **the defect is the test's expected value** and
the failing test also calls product code. It pins the shape Manual Test
reported as L1 issue 3 (2026-07-30): the exclusion removes the one location
that actually contains the mistake, and the revert cannot fire.

## Layout

```
wrong_expectation/money.py   cents(), dollars()   ← both CORRECT
tests/test_money.py          test_cents_of_one        (passes)
                             test_cents_of_two_fifty  (FAILS — asserts 25, not 250)
                             test_dollars_roundtrip   (passes)
```

## What it demonstrates

Run `novetest test tests/` then `novetest localization latest`.

| location | `ef` | `ep` | `nf` | Ochiai |
| --- | --- | --- | --- | --- |
| `tests/test_money.py::test_cents_of_two_fifty` (the real mistake) | 1 | 0 | 0 | **1.0000** |
| `wrong_expectation/money.py::cents` (correct code) | 1 | 2 | 0 | 0.5774 |

`cents` survives the exclusion with a positive score, so the revert does not
fire and the ranking leads with **correct** code at `score_normalized 1.000`.
SBFL cannot separate this from the structural bias the filter exists to fix —
both put `ef = 1, ep = 0` on the test body — so the engine does not try to.
It reports what it removed instead:

```
metadata.test_file_locations_suppressed
  [{"file": "tests/test_money.py",
    "symbol": "test_cents_of_two_fifty",
    "score_raw": 1.0}]
```

Compare that against `entries[0].score_raw` (0.5774): a suppressed suspect
outscoring the top entry is the signal that the failing test's own
expectation is worth reading before its production code.
