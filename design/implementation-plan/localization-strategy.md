# Implementation Plan - Localization Strategy

**Scope:** Implementation strategy for the Localization sub-product. SBFL formula choice, graceful degradation when per-test coverage is unavailable, code-location granularity, score normalization and ranking output, empty-evidence behavior.

**Upstream**
- Foundations: [`foundations.md`](./foundations.md)
- Engine adapters (per-test attribution tiering): [`engine-adapters.md`](./engine-adapters.md#cross-cutting-per-test-coverage-attribution)
- Localization interface contract: [`design/interace-contract/localization.md`](../interace-contract/localization.md)
- Localization product plan: [`design/product-plans/subproducts/nove-test-localization.md`](../product-plans/subproducts/nove-test-localization.md)
- Requirements: [`design/requirements-analysis/requirements-specification/groups/localization.md`](../requirements-analysis/requirements-specification/groups/localization.md)

---

## 1. Formula Choice

**Decision: Ochiai as the default. Compute Op2, DStar(\*=2), and Tarantula in parallel and persist all four. Formula selection is a presentation-layer decision, not a recomputation.**

### Why Ochiai as the default

The published SBFL literature converges on a small set of formulas that are theoretically and empirically defensible:

| Formula | Definition | Notes |
| --- | --- | --- |
| **Ochiai** | `ef / sqrt((ef + nf) * (ef + ep))` | Bounded in [0,1]. Robust across single- and multi-bug cases. The most replicated baseline. |
| **Op2** (Naish et al.) | `ef - ep / (ep + np + 1)` | Provably maximal under the single-bug assumption (Naish, Lee & Ramamohanarao TOSEM 2011). |
| **DStar(\*=2)** | `ef^2 / (ep + nf)` | Empirically strongest with many failing tests (Wong et al. TSE 2014). |
| **Tarantula** | `(ef/(ef+nf)) / (ef/(ef+nf) + ep/(ep+np))` | Provably non-optimal vs Ochiai (Xie et al. TOSEM 2013). Included for parity with prior tools. |

Where for each statement: `ef` = failing tests that executed it, `ep` = passing tests that executed it, `nf` = failing tests that did not, `np` = passing tests that did not.

The decisive arguments for Ochiai-as-default:

1. **Scale stability** - bounded score in [0,1] makes the ranking output schema clean. Op2 and DStar are unbounded; their raw scores require normalization before they are useful as cross-run signals.
2. **Graceful degradation under high `ep`** - real projects have many always-passing utility tests covering shared code; Op2 and DStar can over-penalize or saturate. Ochiai degrades smoothly.
3. **Broadest replication base** - explaining "we use Ochiai" requires the least defending in any technical review.
4. **Pearson et al. ICSE 2017** found that on Defects4J real bugs, Ochiai retains the most robust mean rank and is the least sensitive to single-bug assumption violations.

### Why compute all four

Configuration:

```
localization.formula: "ochiai"
localization.formula_alternates: ["op2", "dstar2", "tarantula"]
```

- All four are cheap once the spectra matrix is built; the matrix construction dominates cost.
- Persist all four scores in the Localization Finding so users (and AI agents) can inspect alternates without re-deriving.
- Op2 is the right answer when the project is genuinely single-bug (e.g. CI run with one new failing test on a small diff).
- DStar(\*=2) is the right answer for "many failing tests" runs.
- Tarantula is included only for users whose prior tooling was Tarantula-based and who want side-by-side comparison.

### Implementation

Under `src/novetest/localization/sbfl/`, one file per formula plus `spectra.py` that builds the (tests x lines) matrix from Coverage Facts. All four formulas are vector ops over the same matrix; `numpy` for the math, persisted as a sparse representation if the matrix is sufficiently large.

```python
# localization/sbfl/ochiai.py
import numpy as np
def ochiai(ef: np.ndarray, ep: np.ndarray, nf: np.ndarray, np_: np.ndarray) -> np.ndarray:
    denom = np.sqrt((ef + nf) * (ef + ep))
    return np.where(denom > 0, ef / denom, 0.0)
```

### Cited literature

- Naish, Lee & Ramamohanarao - *A Model for Spectra-Based Software Diagnosis* - TOSEM 2011 (Op2 / single-bug optimality).
- Xie, Chen, Kuo & Xu - *A Theoretical Analysis of the Risk Evaluation Formulas for Spectrum-Based Fault Localization* - TOSEM 2013 (Ochiai / DStar / Jaccard equivalence; Tarantula non-optimality).
- Wong, Debroy, Gao & Li - *The DStar Method for Effective Software Fault Localization* - TSE 2014 (DStar empirical strength with many failures).
- Lucia, Lo, Jiang, Thung & Budi - *Extended Comprehensive Study of Association Measures for Fault Localization* - STVR 2014.
- Pearson, Campos, Just et al. - *Evaluating and Improving Fault Localization* - ICSE 2017 (Defects4J real-bug evaluation).
- Sohn & Yoo - *FLUCCS: Using Code and Change Metrics to Improve Fault Localization* - ISSTA 2017 (regression-aware reweighting).
- Li, Li, Li & Zhang - *DeepFL: Integrating Multiple Fault Diagnosis Dimensions for Deep Fault Localization* - ISSTA 2019.
- Parnin & Orso - *Are Automated Debugging Techniques Actually Helping Programmers?* - ICSE 2011.
- Kochhar, Xia, Lo & Li - *Practitioners' Expectations on Automated Fault Localization* - ISSTA 2016.

---

## 2. Degradation when Per-Test Coverage is Unavailable

This is the load-bearing question for Localization, because four of our six target ecosystems do not expose per-test coverage cheaply. See [`engine-adapters.md`](./engine-adapters.md#cross-cutting-per-test-coverage-attribution) for the per-ecosystem table.

**Decision: Three explicit modes, surfaced in the Localization Finding so AI agents can reason about evidence strength.**

| Mode | Precondition | Algorithm | Defensibility |
| --- | --- | --- | --- |
| `sbfl_per_test` | per-test coverage available (Python coverage.py contexts; .NET Coverlet PerTestCoverage) | Ochiai/Op2/DStar(\*=2)/Tarantula over per-test spectra | Strong - the published SBFL story |
| `sbfl_aggregate` | only aggregate or coarser coverage + pass/fail counts | Failing-test-set Ochiai over files/symbols covered by the failing-tests union; passing component approximated from aggregate minus failing | Medium - degraded but principled |
| `failure_proximity` | no coverage at all, or coverage too coarse to be useful | Rank by (a) files named in failing-test stack frames and (b) files modified in the regression set intersected with files mentioned in failure output | Weak but explicit; mark `confidence: "low"` |

The Localization Finding carries a `mode` field with one of these values plus a `confidence` field (`high` / `medium` / `low`) so the consumer can react.

### Most defensible fallback hierarchy when only aggregate coverage exists

In priority order:

1. **Regression-aware reweighting first.** If a Regression Fact set exists for the run (which Nove Test produces from prior runs), use it as a strong prior. Recently changed code that was covered by a now-failing test is the highest-signal evidence available without per-test coverage. This is the FLUCCS approach (Sohn & Yoo ISSTA 2017), which empirically closes much of the gap with per-test SBFL on Defects4J.
2. **Failure-only Ochiai as the floor.** Compute Ochiai using only the failing tests' coverage union vs. the aggregate covered set as the "passing" approximation: `ef = 1 if covered by any failing test, ep ≈ aggregate_hits − failing_hits`. Biased but bounded.
3. **Coverage-weighted heuristic** (rank by hit-count of failing-test-touched files) is the weakest. Emit only when neither regression facts nor a failing-test coverage subset is available. Mark `confidence: "low"`.

### Why regression-aware is the most defensible

It is the only fallback with a published track record of closing the gap with per-test SBFL on real bugs. Failure-only Ochiai is a sensible floor; regression reweighting is a sensible default.

### Mode selection algorithm (pseudocode)

```python
def pick_mode(coverage_facts, regression_facts, failed_tests):
    if not failed_tests:
        return Mode.UNAVAILABLE  # see section 5
    granularity = coverage_facts.mapping_granularity if coverage_facts else None
    if granularity == "per-test":
        return Mode.SBFL_PER_TEST
    if granularity in ("per-test-class", "per-test-file", "aggregate"):
        if regression_facts:
            return Mode.SBFL_AGGREGATE_REGRESSION_REWEIGHTED
        return Mode.SBFL_AGGREGATE_FAILURE_ONLY
    return Mode.FAILURE_PROXIMITY
```

These modes map directly to the contract's "available" / "unavailable" outcomes (REQ-LOC-001 / REQ-LOC-004 in the requirements spec).

---

## 3. Code Location Granularity

**Decision: Symbol/function-level as the default; line-level retained as evidence inside each finding.**

### Rationale

Parnin & Orso (ICSE 2011) and Kochhar et al. (ISSTA 2016) on practitioner expectations consistently show:
- Line-level is what SBFL papers report, but practitioners (and now AI agents) almost always need the function to act.
- File-level loses too much; large files dominate the ranking by sheer line count.
- Branch-level requires branch coverage, which most aggregate coverage backends do not expose uniformly.

### Output shape

```python
@dataclass(slots=True, frozen=True)
class CodeLocation:
    kind: Literal["symbol", "line", "branch", "file"]
    file: str                          # repo-relative
    symbol: str | None                 # qualified symbol e.g. "BarService.compute"
    line_range: tuple[int, int] | None
    primary_line: int                  # top-ranked line inside the symbol
    evidence_lines: list[int]          # other suspicious lines inside the symbol
```

### Aggregation

Compute SBFL at line granularity internally (cheap, well-defined), then **aggregate up to the enclosing symbol using `max(score)` of its lines**. Do **not** use mean - mean dilutes by symbol size, recreating the file-level pathology.

This also gives a clean answer to the "huge file" pathology: a 2000-line file contributes one entry per function, not one entry per line.

### Symbol resolution

Each language adapter provides a symbol-resolution helper that maps a `(file, line)` pair to a `(symbol, line_range)` tuple. For Python, parse with `ast`; for JS/TS, with `tree-sitter` or `@babel/parser` (via subprocess); for Java/Kotlin, parse from JaCoCo class metadata. We can ship Phase 4 with file-level fallback when the symbol resolver is missing for an ecosystem, then upgrade per language.

---

## 4. Score Normalization and Ranking Output

### Output fields (per finding entry)

| Field | Definition |
| --- | --- |
| `score_raw` | The formula's native value. Ochiai in [0,1]; DStar/Op2 unbounded. |
| `score_normalized` | Min-max within this finding set, in [0,1]. |
| `rank` | 1-based dense rank (ties share a rank, next rank skips). |
| `tied_with` | List of CodeLocation ids sharing this rank - explicit tie disclosure. |
| `formula` | The formula whose score `rank` is derived from. Default: `"ochiai"`. |
| `alternate_scores` | Map of `{formula -> score}` for the other three computed formulas. |

### Why explicit ties

SBFL ties are common at the top of the list - Parnin & Orso showed top-1 ties of 5-15 locations are routine. Silently breaking ties is the single most-cited usability complaint in the literature. Surface them.

### Default top-N

**10**, configurable via `--top-n`. Rationale:
- Kochhar et al. (2016) found practitioners lose patience after rank ~5; AI agents have higher tolerance but context budget is real.
- 10 is the smallest N that reliably contains the true fault on Defects4J for Ochiai (Pearson et al. 2017 reports top-10 hit rates of ~55-70% on real bugs).

### Why both raw and normalized

- **Raw is for explainability.** Useful in single-run inspection.
- **Normalized is for cross-run / cross-formula comparison.** Raw Ochiai is not comparable across runs because it depends on test suite size; normalized is portable.
- AI agents will compare across runs; do not return only raw scores.

---

## 5. Empty-Evidence Behavior

**Decision: Return an explicit `unavailable` state, not a fallback ranking.** The interface contract already names this (`or explicit unavailable state` in `localization.md`); honor it strictly.

### Output shape for unavailable

```json
{
  "status": "unavailable",
  "reason": "no_failed_tests | no_coverage | no_run_evidence | run_not_analyzable",
  "run_reference": "run_2026_05_11_abcd",
  "available_evidence": {
    "failed_tests": 0,
    "coverage_facts": false,
    "regression_facts": false
  },
  "findings": []
}
```

### Why explicit-unavailable beats a heuristic fallback

- The primary consumer is an AI agent. A weak ranking with no signal is worse than a clear "no signal" - the agent will spend tokens reasoning over noise.
- It satisfies NFR-LOC-001 (traceability) trivially: there is nothing to trace.
- It composes cleanly with `orchestration/evaluate_stage_eligibility` - Localization saying "unavailable" is one of the inputs that gates downstream synthesis.

### The one nuance

When **failed tests exist but coverage does not**, return the `failure_proximity` mode from §2 with `confidence: "low"` rather than `unavailable`. That is a real degraded fallback, not a heuristic on noise.

---

## 6. Putting It Together

The Localization Finding the engine returns:

```json
{
  "finding_id": "loc_run_2026_05_11_abcd_0001",
  "run_reference": "run_2026_05_11_abcd",
  "mode": "sbfl_aggregate",
  "confidence": "medium",
  "formula": "ochiai",
  "alternate_scores_available": ["op2", "dstar2", "tarantula"],
  "top_n": 10,
  "findings": [
    {
      "rank": 1,
      "tied_with": [],
      "code_location": {
        "kind": "symbol",
        "file": "src/foo/bar.py",
        "symbol": "BarService.compute",
        "line_range": [42, 71],
        "primary_line": 58,
        "evidence_lines": [58, 63]
      },
      "score_raw": 0.71,
      "score_normalized": 0.92,
      "alternate_scores": {"op2": 4.3, "dstar2": 12.5, "tarantula": 0.61},
      "related_failed_tests": ["tests/test_bar.py::test_compute_negative"],
      "evidence_citations": [
        {"kind": "test_result", "run_reference": "run_2026_05_11_abcd",
         "test_id": "tests/test_bar.py::test_compute_negative", "outcome": "failed"},
        {"kind": "coverage_fact", "run_reference": "run_2026_05_11_abcd",
         "selector": {"file": "src/foo/bar.py", "lines": [58, 63]}, "mode": "aggregate"}
      ]
    }
  ]
}
```

The `evidence_citations` field is a Localization-internal concern and is distinct from the recommendation-layer citations produced by `orchestration/cite_recommendation_evidence`. Localization owns its own citations (per the orchestration deduplication review earlier in design); the Recommendation engine cites the Localization Finding as a whole, not its internal citation entries.

---

## Open Items

The following are flagged for follow-up during Phase 4 (Localization) implementation; see also [`delivery-phasing.md`](./delivery-phasing.md#open-questions):

1. **Per-language symbol resolvers.** Python (`ast`) is ready; JS/TS, Java/Kotlin, Go, Rust, C# need pluggable resolvers. Phase 4 ships with file-level fallback for ecosystems whose resolver is not yet ready.
2. **Branch-level granularity** when branch coverage is reliably available - currently optional auxiliary evidence inside each finding, not a primary kind.
3. **Spectra-matrix size limits.** For very large suites (>10k tests x >100k lines), decide between sparse representation, sampling, or partition-by-target. Empirically validate at Phase 4 against the largest fixture project.
4. **Cross-run reweighting** (DeepFL-style multi-run features) is explicitly out of scope for Phase 4. Revisit post-MVP.
