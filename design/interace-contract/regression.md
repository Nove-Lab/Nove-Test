# Interface Contract - Regression

**Scope:** Regression sub-product. Resolves the correct latest comparison baseline for a Test Target and derives factual behavioral differences between two Run Records, including test outcome transitions, native output differences, and available coverage changes. Regression produces facts only; it does not prescribe fixes or assign root cause.

**Upstream references**
- `design/product-plans/subproducts/nove-test-regression.md`
- `design/requirements-analysis/requirements-specification/groups/regression.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-013, SR-014)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration, Localization) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Regression Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest regression compare <run_id1> <run_id2>` | External | Two Run References | Regression Fact set covering test outcome transitions (pass-to-fail, fail-to-pass), native output differences, and Coverage changes when Coverage Facts are available for both runs |
| `novetest regression latest` | External | (none; resolved against current Run History) | Regression Fact set comparing the two most recent comparable Run Records for the same resolved Test Target, or explicit unavailable state when no comparable pair exists |
| `compare_runs(run_reference_1, run_reference_2)` | Internal | Two Run References | Regression Fact set with transition records, output-difference records, and Coverage-change records |
| `resolve_latest_baseline(test_target)` | Internal | Test Target (or active Test Target context) | Pair of Run References (baseline_run_reference, target_run_reference) for the most recent comparable runs sharing the same resolved Test Target, or unavailable state |
| `derive_latest_regression()` | Internal | (none; uses current Run History) | Regression Fact set for the resolved latest pair, or unavailable state (composes `resolve_latest_baseline` then `compare_runs`) |
| `get_regression_facts(run_reference_1, run_reference_2)` | Internal | Two Run References | Previously derived Regression Fact set for the run pair, or unavailable state if not yet derived |
| `check_regression_availability(run_reference)` | Internal | Run Reference | Availability flag indicating whether a comparable prior run exists for the same Test Target (used by Orchestration eligibility evaluation and Localization) |

---

## Notes

- Baseline selection is target-scoped (REQ-REG-001); regression results are deterministic for the same stored evidence state (NFR-REG-001).
- Regression depends on Memory (`retrieve_run_evidence`, `find_runs_for_target`) and optionally on Coverage (`compare_coverage_facts`, `get_coverage_facts`) when coverage changes are incorporated.
- Localization consumes Regression Facts via `get_regression_facts` to focus on changed behavior when available.
