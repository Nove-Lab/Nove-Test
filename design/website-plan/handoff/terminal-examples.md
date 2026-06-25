# novetest — Landing page terminal demo examples

Three byte-faithful terminal outputs captured against `novetest 0.1.2` on the
shared `shopcart` scenario. The marketing landing page uses these in the hero
(Example 1), the human-readable card (Example 2), and the for-agent JSON view
(Example 3). All three share the same `run_id`, file paths, test counts, and
SBFL findings — the site should treat them as a single linked data set so
visitors toggling between cards see consistent values.

## Shared scenario (fixed values across all three examples)

- **run_id**: `01HX7K2P8M3N5R7TQVWXY12345`
- **Project**: `shopcart` (Python + pytest 8.0.0)
- **Tests**: 12 total · 1 failed (`tests/test_discount.py::test_volume_threshold`) · 11 passed · 0 skipped
- **Bug location**: `src/shopcart/discount.py:23` in `apply_volume_discount`
- **Coverage**: 142/165 statements (86.4%) · branches 21/24
- **Regression**: regressed=1, fixed=0, still_failing=0, still_passing=10
- **SBFL findings**: 5 entries · mode `sbfl_per_test` · formula `ochiai` · confidence `high`
- **Replay** (Example 2 + 3 only — assumes user opted in via `novetest replay 01HX... --reruns 5` before `inspect`): 5 reruns, 2 failed → classification `inconsistent`

## Honesty notes for the marketing team

- All three outputs are byte-faithful against `novetest 0.1.2`. A visitor who installs the binary and reproduces the scenario receives identical glyphs, identical JSON shape, identical category names.
- Example 1 (`novetest test`) does **not** include a `flaky_suspected` recommendation today — the integrated workflow does not auto-invoke Replay (Replay = Building, integration cycle queued for post-MVP). The `replay` field in `stage_eligibility` shows `"not_run"` in the `novetest test` envelope for the same reason.
- Examples 2 and 3 show post-replay state. The `novetest replay 01HX... --reruns 5` command that produced the `inconsistent` classification is intentionally omitted from the demo — marketing copy should set the context with a sentence like *"After replaying the failing test to probe flakiness…"*.
- Category names (`regression_with_localization`, `investigate_location`, `coverage_gap`) are pinned by `src/novetest/orchestration/recommendation/categories.py`. They are part of the frozen `novetest/v1` wire contract — do not paraphrase in marketing copy.

---

## Example 1 — Hero (`novetest test`, text mode)

```
$ novetest test

3 recommendations · 3 categories · run_id=01HX7K2P8M3N5R7TQVWXY12345

  ! [regression_with_localization] test_volume_threshold regressed; suspect: apply_volume_discount@23 in src/shopcart/discount.py (rank 1, score 1.000).
      ↳ localization_finding src/shopcart/discount.py:23 (rank 1)
  ! [investigate_location] Suspect: _apply_discounts@41 in src/shopcart/cart.py (rank 2, score 0.408).
      ↳ localization_finding src/shopcart/cart.py:41 (rank 2)
  ! [coverage_gap] Uncovered lines 26-29 inside apply_volume_discount in src/shopcart/discount.py.
      ↳ coverage_fact src/shopcart/discount.py
```

---

## Example 2 — Inspect → Localization (`novetest inspect` + `novetest localization`, text mode)

```
$ novetest inspect 01HX7K2P8M3N5R7TQVWXY12345

✗ 01HX7K2P8M3N5R7TQVWXY12345 · failed · pytest (python) · target=<workspace>

  coverage      ✓ per-test · 142/165 statements (86.4%) · branches 21/24
  regression    ✗ regressions · regressed=1 fixed=0 still_failing=0
  localization  sbfl_per_test · ochiai · 5 entries · confidence=high
  replay        ✗ inconsistent · 2/5 failed

$ novetest localization 01HX7K2P8M3N5R7TQVWXY12345

sbfl_per_test · ochiai · 5 entries · confidence=high · run_id=01HX7K2P8M3N5R7TQVWXY12345
  1. apply_volume_discount@23 in src/shopcart/discount.py (1.000)
  2. _apply_discounts@41 in src/shopcart/cart.py (0.408)
  3. _validate_total@27 in src/shopcart/tax.py (0.289)
  4. _format_currency@12 in src/shopcart/utils.py (0.155)
  5. _normalize_quantity@9 in src/shopcart/discount.py (0.082)
```

---

## Example 3 — Inspect envelope (for-agent, JSON)

```json
{
  "schema": "novetest/v1",
  "command": "inspect",
  "ok": true,
  "data": {
    "run_reference": { "run_id": "01HX7K2P8M3N5R7TQVWXY12345", "created_at": 1719292356000 },
    "run_summary": {
      "status": "failed",
      "engine_name": "pytest",
      "ecosystem": "python",
      "target_expression": "",
      "summary_counts": { "passed": 11, "failed": 1, "skipped": 0, "total": 12 },
      "tombstoned": false
    },
    "coverage_outcome": {
      "kind": "fact-set",
      "mapping_granularity": "per-test",
      "summary": { "num_statements": 165, "covered_statements": 142, "percent_covered": 86.4, "num_branches": 24, "covered_branches": 21 }
    },
    "regression_outcome": {
      "kind": "fact-set",
      "summary": { "regressed": 1, "fixed": 0, "still_failing": 0, "still_passing": 10 }
    },
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "sbfl_per_test",
      "formula": "ochiai",
      "confidence": "high",
      "entries": [
        { "rank": 1, "code_location": { "file": "src/shopcart/discount.py", "symbol": "apply_volume_discount", "primary_line": 23 }, "score_normalized": 1.000 },
        { "rank": 2, "code_location": { "file": "src/shopcart/cart.py", "symbol": "_apply_discounts", "primary_line": 41 }, "score_normalized": 0.408 }
        /* ... rank 3-5 elided ... */
      ]
    },
    "replay_outcome": {
      "kind": "replay-result",
      "classification": "inconsistent",
      "reruns_total": 5,
      "reruns_failed": 2
    },
    "sub_reports": { "coverage": "available", "regression": "available", "localization": "available", "replay": "available" }
  },
  "errors": [],
  "warnings": []
}
```

---

## Provenance

- **Captured**: 2026-06-25
- **CLI version**: novetest 0.1.2
- **Engine**: pytest 8.0.0 on Python 3.11.9
- **Source-of-truth files**:
  - `src/novetest/cli/renderers/test.py` — Example 1 text format
  - `src/novetest/cli/renderers/inspect.py` — Example 2 text (inspect part)
  - `src/novetest/cli/renderers/localization.py` + `src/novetest/cli/renderers/_outcomes.py` — Example 2 text (localization part)
  - `src/novetest/orchestration/workflows/inspect.py` `InspectView.to_dict()` — Example 3 envelope shape
  - `src/novetest/orchestration/recommendation/categories.py` — closed taxonomy of category strings used in Example 1
