# Interface Contract - Localization

**Scope:** Localization sub-product. Selects an analyzable Run Record and ranks suspicious Code Locations using failed Test Result context, available Coverage Facts, and (when available) Regression Facts. Localization produces ranked findings with supporting Evidence Citations; it does not prescribe a fix or assign final root cause.

**Upstream references**
- `design/product-plans/subproducts/nove-test-localization.md`
- `design/requirements-analysis/requirements-specification/groups/localization.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-015, SR-016, SR-021)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Localization Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest localization <run_id>` | External | Run Reference | Localization Finding set (ranked Code Locations with score or equivalent ranking evidence, related failed Test Result references, supporting Evidence Citations) or explicit unavailable state |
| `novetest localization latest` | External | (none; resolved against current Run History) | Localization Finding set for the most recent stored run that has the evidence required for localization-oriented analysis, or explicit unavailable state |
| `derive_localization_findings(run_reference)` | Internal | Run Reference (resolved through Memory) | Localization Finding set with ranked Code Locations, supporting Evidence Citations referencing Test Results, Coverage Facts, and Regression Facts when available |
| `resolve_latest_analyzable_run()` | Internal | (none; uses current Run History) | Run Reference of the most recent run with sufficient evidence for localization, or unavailable state |
| `derive_latest_localization()` | Internal | (none; uses current Run History) | Localization Finding set for the resolved latest analyzable run (composes `resolve_latest_analyzable_run` then `derive_localization_findings`) |
| `get_localization_findings(run_reference)` | Internal | Run Reference | Previously derived Localization Finding set for the run, or unavailable state if not yet derived |
| `check_localization_availability(run_reference)` | Internal | Run Reference | Availability flag indicating whether failed Test Results plus Coverage Facts (and optionally Regression Facts) exist for derivation (used by Orchestration eligibility evaluation) |

---

## Notes

- Localization depends on Memory (`retrieve_run_evidence`), Coverage (`get_coverage_facts` / `derive_coverage_facts`), and optionally Regression (`get_regression_facts`).
- Every Localization Finding preserves traceability to the run evidence used to rank it (NFR-LOC-001) via Evidence Citations attached during derivation.
- Localization may still produce findings without Regression Facts, provided failed Test Results and Coverage Facts are available (REQ-LOC-003 assumption).
