# Interface Contract - Orchestration

**Scope:** Top-level Nove Test orchestration product. Coordinates the integrated workflow across Run, Memory, Coverage, Regression, Localization, and Replay sub-products and synthesizes recommendations with cited evidence.

**Upstream references**
- `design/product-plans/overall-plan.md`
- `design/product-plans/overall-architecture.md`
- `design/requirements-analysis/requirements-specification/groups/orchestration.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-001, SR-019, SR-020, SR-021)

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules within the tool boundary.
- Inputs and outputs are described with domain-entity vocabulary from `design/requirements-analysis/domain-model.md` (e.g. `Test Target`, `Run Reference`, `Run Record`, `Recommendation`, `Status`, `Evidence Citation`).

---

## Orchestration Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest test [target]` | External | Test Target (target expression, optional workspace context) | Recommendation set with Evidence Citations, normalized Run Record summary, and per-stage availability flags for Coverage Fact / Regression Fact / Localization Finding / Replay Result |
| `novetest inspect <run_id>` | External | Run Reference | Aggregated run view composing the Memory Entry (Run Record, Test Result summary, captured-output handles) with the actual content of derived facts when available - Coverage Fact set, Regression Fact set versus prior run when resolvable, Localization Finding set, Replay Result - returned as a single top-level payload (distinct from `novetest memory show`, which returns Memory's own evidence and only availability flags) |
| `novetest compare <run_id1> <run_id2>` | External | Two Run References | Regression Fact set across the run pair, optional Coverage delta when Coverage Facts exist for both runs |
| `novetest status` | External | (none) | Status entity summarizing latest Run Reference, Run History readiness, and per-sub-report availability (Coverage / Regression / Localization / Replay) |
| `synthesize_recommendation(fact_bundle)` | Internal | Bundle of available facts (Coverage Fact set, Regression Fact set, Localization Finding set, Replay Result, Status) for a Run Reference | Recommendation set with attached Evidence Citations linking each item back to a supporting Run Reference and fact source |
| `cite_recommendation_evidence(recommendation, supporting_facts)` | Internal | Recommendation plus referenced facts (Run Reference, Coverage Fact, Regression Fact, Localization Finding, Replay Result) used to derive it | Recommendation with attached Evidence Citation set (each item resolvable to a Run Reference and fact source). Scoped to top-level Recommendations only; Localization owns citations on its own findings. |
| `evaluate_stage_eligibility(run_reference)` | Internal | Run Reference plus current Memory Entry availability state | Per-stage eligibility flags for Coverage / Regression / Localization / Replay used by the integrated workflow |
| `build_status_view(run_history)` | Internal | Run History (ordered Memory Entry collection) | Status entity with latest Run Reference, overall readiness, and sub-report availability flags |

---

## Notes

- All External CLI surfaces above must produce structured output suitable for AI-agent consumption (NFR-ORCH-001).
- The integrated `novetest test` flow is the only place where Recommendations are emitted; sub-product CLIs return facts only.
- Internal interfaces above are reused at least once by the workflow modeling step (sequence diagrams).
