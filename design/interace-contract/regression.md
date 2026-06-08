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

---

## Transition Detection Semantics

`compare_runs` walks the **union** of `node_id` values from both Run Records' `test_results`, then classifies each `node_id` into exactly one of the 9 categories pinned by `decisions/2026-05-26-regression-facts-json-layout.md` §3 (`TRANSITION_CATEGORIES` closed enum). Set-membership of the `node_id` determines which subset of categories is reachable:

| `node_id` membership | Reachable categories |
| --- | --- |
| Present on **both** sides | `regressed` / `fixed` / `still_failing` / `still_passing` / `still_skipped` / `newly_skipped` / `newly_active` (the (baseline_bucket, target_bucket) tuple decides which) |
| Present on **target only** | `added` (regardless of `target_outcome` — pass-like, fail-like, or skip-like) |
| Present on **baseline only** | `removed` (regardless of `baseline_outcome`) |

Two consequences fall out of the above and are binding contract:

1. **`fixed` and `regressed` require the same `node_id` on both sides.** A test that exists only in the target run, even if its outcome is `passed`, is `category="added"` — NOT `category="fixed"`. Symmetrically, a test that exists only in the baseline, even if its outcome is `failed`, is `category="removed"` — NOT `category="regressed"`. The transition counts in `RegressionSummary.fixed` / `RegressionSummary.regressed` therefore reflect changes within the shared `node_id` intersection only.

2. **Disjoint test sets are still a valid comparison; both `regressed` and `fixed` may be zero.** If two Run Records over the same `target_expression` have no shared `node_id` values (for example, the baseline run errored before discovery emitted any `TestResult`s, or the test suite was wholesale renamed between runs), the Regression Fact Set is still produced and is still authoritative; the per-test signal lives entirely in `category="added"` and `category="removed"` records. Consumers MUST NOT read `summary.regressed == 0 AND summary.fixed == 0` as "nothing changed" without also checking `summary.added` and `summary.removed`.

### Consumer guidance for "newly-introduced failures"

Per `decisions/2026-05-26-regression-facts-json-layout.md` §C.7, a consumer that wants the "suspect" universe of behavior changes (Localization's typical filter) should match on:

- `category in {"regressed", "still_failing"}` — failures present in both runs, with `regressed` highlighting the new failures and `still_failing` the inherited ones, AND
- `category == "added" AND target_outcome` in the fail-like bucket (`failed`, `errored`) — newly-introduced failures on tests that did not exist in the baseline.

Symmetrically, a consumer reasoning about "newly-introduced passes" should match on `category == "fixed"` (same-`node_id` fail→pass) AND `category == "added" AND target_outcome` in the pass-like bucket (`passed`, `xpassed`).

The closed 9-category taxonomy is **load-bearing** — adding a new category is a breaking change requiring a `RegressionFactSet.schema_version` bump and a `decisions/` follow-up.
