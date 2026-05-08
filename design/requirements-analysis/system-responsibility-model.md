# System Responsibility Model

## References

- User request: continue from the existing analysis in `design/requirements-analysis/`, use `design/product-plans/` as supporting reference, and proceed from system responsibility modeling after confirming current status.
- Upstream models:
  - `design/requirements-analysis/context-model.md`
  - `design/requirements-analysis/use-case-model.md`
  - `design/requirements-analysis/domain-model.md`
- Supporting product plans:
  - `design/product-plans/overall-plan.md`
  - `design/product-plans/overall-architecture.md`
  - `design/product-plans/subproducts/nove-test-run.md`
  - `design/product-plans/subproducts/nove-test-memory.md`
  - `design/product-plans/subproducts/nove-test-coverage.md`
  - `design/product-plans/subproducts/nove-test-regression.md`
  - `design/product-plans/subproducts/nove-test-localization.md`
  - `design/product-plans/subproducts/nove-test-replay.md`

---

## Responsibilities

| ID | Responsibility | Description | Related Use Cases | Related Entities |
| --- | --- | --- | --- | --- |
| SR-001 | Orchestrate test workflow | Coordinate the integrated `novetest test` path so execution, storage, optional fact analysis, and recommendation synthesis run as one governed workflow. | Execute Test Workflow | Test Target, Run Record, Memory Entry, Recommendation |
| SR-002 | Resolve test target | Interpret the requested execution scope into the concrete test target context used by execution and downstream evidence. | Execute Test Workflow, Run Test Target, Supply Test Target Material | Test Target |
| SR-003 | Select native engine | Determine which native engine context applies to the requested or replayed run so execution remains traceable to the external ecosystem. | Run Test Target, Replay Prior Run | Test Target, Native Engine, Run Record |
| SR-004 | Invoke native execution | Trigger the external native engine against the resolved target and collect the raw native result bundle. | Run Test Target, Replay Prior Run, Provide Native Execution Facts | Test Target, Native Engine, Native Result |
| SR-005 | Normalize execution result | Transform the native result bundle into Nove Test's normalized run record and test-result evidence. | Execute Test Workflow, Run Test Target, Replay Prior Run | Native Result, Run Record, Test Result |
| SR-006 | Assign run reference | Create and attach a stable run reference that can be used for retrieval, comparison, replay, and citation. | Execute Test Workflow, Run Test Target, Replay Prior Run | Run Reference, Run Record |
| SR-007 | Persist run evidence | Store normalized run evidence and native-derived artifacts so later workflows can inspect, compare, replay, and cite the run. | Execute Test Workflow, Store Run Evidence | Memory Entry, Run Record, Native Result, Run Reference, Run History |
| SR-008 | Retrieve run evidence | Load stored run evidence and its availability state by run reference for inspection and downstream analysis workflows. | Execute Test Workflow, Inspect Run Evidence, Manage Stored Runs, Compare Coverage Facts, Compare Run Behavior, Localize Faults, Replay Prior Run, Generate Recommendations | Run Reference, Memory Entry, Run Record |
| SR-009 | Enumerate stored runs | Return ordered stored run references and summaries for memory management and status-oriented views. | Manage Stored Runs, Check Testing Status | Run History, Memory Entry, Run Reference |
| SR-010 | Remove stored run evidence | Delete a stored run from active memory scope and update the retained run history accordingly. | Manage Stored Runs | Memory Entry, Run Reference, Run History |
| SR-011 | Derive coverage facts | Structure native-derived coverage information into test-to-code mappings, line or branch facts, and uncovered-code evidence for a stored run. | Execute Test Workflow, Show Coverage Facts | Memory Entry, Run Record, Test Result, Coverage Fact, Code Location |
| SR-012 | Compare coverage facts | Compute cross-run coverage differences from stored coverage evidence for two run references. | Compare Coverage Facts, Compare Run Behavior | Coverage Fact, Run Record, Code Location |
| SR-013 | Resolve latest comparison baseline | Identify the two most recent comparable runs for the same resolved test target so regression comparison can execute without requiring both run references from the actor. | Review Latest Regression | Run History, Run Reference, Run Record, Test Target |
| SR-014 | Derive regression facts | Compare run records and available coverage evidence to identify behavioral transitions, output differences, and coverage changes. | Execute Test Workflow, Compare Run Behavior, Review Latest Regression | Run Record, Test Result, Coverage Fact, Regression Fact |
| SR-015 | Resolve latest analyzable run | Select the latest stored run that has the evidence needed for localization-oriented review. | Review Latest Localization | Run History, Run Reference, Run Record |
| SR-016 | Derive localization findings | Rank suspicious code locations for a run by combining failed-test context with available coverage and regression signals. | Execute Test Workflow, Localize Faults, Review Latest Localization | Run Record, Test Result, Coverage Fact, Regression Fact, Localization Finding, Code Location |
| SR-017 | Reconstruct replay context | Recover the original run context needed to replay a stored run through the governed execution path. | Replay Prior Run | Replay Attempt, Memory Entry, Run Record, Native Engine, Test Target |
| SR-018 | Classify replay consistency | Compare the original and replayed execution outcomes to determine reproducibility status and summarize consistency. | Replay Prior Run | Replay Attempt, Run Record, Replay Result |
| SR-019 | Summarize testing status | Synthesize current evidence availability, recent run context, and overall plus sub-report workflow readiness into a concise status view. | Check Testing Status | Status, Run History, Run Reference, Memory Entry, Coverage Fact, Regression Fact, Localization Finding, Replay Result |
| SR-020 | Synthesize recommendations | Turn available facts into top-level guidance about the next testing, debugging, or coding step. | Execute Test Workflow, Generate Recommendations | Recommendation, Coverage Fact, Regression Fact, Localization Finding, Replay Result, Status |
| SR-021 | Cite supporting evidence | Attach traceable evidence citations to recommendations and fact outputs that need explicit support references. | Execute Test Workflow, Generate Recommendations, Localize Faults | Evidence Citation, Recommendation, Localization Finding, Run Reference |

---

## Model Notes

- Responsibilities were consolidated around reusable system actions instead of CLI commands. For example, replay reuses `Select native engine`, `Invoke native execution`, `Normalize execution result`, and `Assign run reference` rather than duplicating a separate replay-execution stack.
- Latest-run workflows were split into explicit selection responsibilities (`SR-013`, `SR-015`) plus analysis responsibilities (`SR-014`, `SR-016`) to keep "latest" behavior distinct from comparison or localization logic.
- Recommendation synthesis stays isolated in `SR-020` so sub-product responsibilities remain fact-oriented and consistent with the product-plan rule that only top-level Nove Test emits recommendations.
- `SR-019` assumes the status view can expose both an aggregated readiness state and sub-report availability for downstream analysis capabilities.
- End-to-end traceability check: `AI Agent` -> `Execute Test Workflow` -> `SR-001`, `SR-004`, `SR-007`, `SR-020`, `SR-021` -> `Test Target`, `Native Result`, `Run Record`, `Memory Entry`, `Recommendation`, `Evidence Citation`. This flow is consistent across the context, use-case, domain, and responsibility layers.

---

## Assumptions

- `design/requirements-analysis/` is treated as the active single-task analysis workspace for Nove Test even though it does not use the newer `requirements-analysis-<task-name>/` naming convention.
- The integrated `Execute Test Workflow` may invoke coverage, regression, localization, and recommendation-related responsibilities conditionally when the required stored evidence or native-derived facts are available.
- `Remove stored run evidence` should preserve a safer audit trail or tombstone rather than performing an untraceable hard removal from the evidence history.
- Evidence citation is modeled as a shared system responsibility for both top-level recommendations and localization outputs because both need explicit traceability to supporting run evidence.
- `Review Latest Regression` is scoped to the two most recent comparable runs for the same resolved test target, not simply the two most recent runs overall.

---

## Open Questions

None.
