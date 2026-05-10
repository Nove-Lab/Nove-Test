# Interface Contract - Coverage

**Scope:** Coverage sub-product. Structures native-derived coverage information stored in Memory into Coverage Facts (test-to-code mapping, line/branch coverage, uncovered code evidence) and computes cross-run coverage deltas. Coverage produces facts only; it never decides whether a gap is acceptable.

**Upstream references**
- `design/product-plans/subproducts/nove-test-coverage.md`
- `design/requirements-analysis/requirements-specification/groups/coverage.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-011, SR-012)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration, Regression, Localization) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Coverage Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest coverage show <run_id>` | External | Run Reference | Coverage Fact set for the run (test-to-code mapping, line coverage, branch coverage, uncovered Code Locations) or explicit unavailable-or-incomplete state |
| `novetest coverage diff <run_id1> <run_id2>` | External | Two Run References | Coverage delta across matching Code Locations (newly covered, newly uncovered, branch transitions) or explicit unavailable-or-incomplete state when comparison cannot be derived |
| `derive_coverage_facts(run_reference)` | Internal | Run Reference (resolved through Memory) | Coverage Fact set bound to the originating Run Record, with Code Location references; or unavailable state when native-derived coverage inputs are missing |
| `get_coverage_facts(run_reference)` | Internal | Run Reference | Previously derived Coverage Fact set for the run, or unavailable state if not yet derived |
| `compare_coverage_facts(run_reference_1, run_reference_2)` | Internal | Two Run References | Coverage delta entity (per-Code-Location transitions, summary deltas) or unavailable-or-incomplete state when either side lacks comparable Coverage Facts |
| `check_coverage_availability(run_reference)` | Internal | Run Reference | Availability flag indicating whether Coverage Facts can be derived or retrieved for this run (used by Orchestration eligibility evaluation) |

---

## Notes

- Every Coverage Fact and Coverage delta entry preserves traceability to its originating Run Reference and Code Location (NFR-COV-001).
- Coverage is invoked by Orchestration (integrated workflow + `novetest compare`), Regression (to incorporate coverage changes), and Localization (to connect failed tests to executed code).
- Unavailability is an explicit outcome (REQ-COV-004) rather than an error, because native engines vary in coverage support.
