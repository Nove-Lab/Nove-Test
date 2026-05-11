# Requirements - Orchestration

## Description

Top-level Nove Test behavior that covers onboarding entrypoints, coordinates the integrated workflow, exposes overall and sub-report readiness, synthesizes recommendations, and cites the supporting evidence used by those recommendations.

---

## Functional Requirements


| ID           | Description                                                                                                                                                                                                                             | Source Use Case                                 | Source Responsibility | Related Entities                                                                                                      | Priority | Status |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------- | -------- | ------ |
| REQ-ORCH-001 | The system shall execute the integrated `novetest test` workflow as a governed sequence that invokes run execution, persists run evidence, and then evaluates eligible downstream analyses before returning the final top-level result. | Execute Test Workflow                           | SR-001                | Test Target, Run Record, Memory Entry, Recommendation                                                                 | High     | Approved |
| REQ-ORCH-002 | The system shall determine, for each integrated test workflow, which downstream analysis stages are eligible based on the availability of stored evidence and native-derived facts for the current run.                                 | Execute Test Workflow                           | SR-001                | Run Record, Memory Entry, Coverage Fact, Regression Fact, Localization Finding, Replay Result                         | High     | Approved |
| REQ-ORCH-003 | The system shall provide a status view that reports the latest relevant run reference, overall readiness, and sub-report availability for coverage, regression, localization, and replay-related outputs.                               | Check Testing Status                            | SR-019                | Status, Run History, Run Reference, Memory Entry, Coverage Fact, Regression Fact, Localization Finding, Replay Result | High     | Approved |
| REQ-ORCH-004 | The system shall synthesize top-level recommendations only from available Nove Test facts and shall not treat sub-product outputs as final recommendations by themselves.                                                               | Execute Test Workflow, Generate Recommendations | SR-020                | Recommendation, Coverage Fact, Regression Fact, Localization Finding, Replay Result, Status                           | High     | Approved |
| REQ-ORCH-005 | The system shall attach at least one traceable evidence citation to each top-level recommendation item it returns.                                                                                                                      | Execute Test Workflow, Generate Recommendations | SR-021                | Recommendation, Evidence Citation, Run Reference                                                                      | High     | Approved |
| REQ-ORCH-006 | The system shall expose installed CLI identity and top-level help behavior that allows a user to verify immediately after installation that `novetest` is callable and available.                                                      | Install Nove Test CLI, Verify CLI Availability  | SR-022                | CLI Installation                                                                                                      | High     | Approved |
| REQ-ORCH-007 | The system shall provide a single `novetest init` onboarding command that initializes Nove Test for the current project workspace without requiring manual Nove Test configuration steps.                                              | Initialize Project Workspace                    | SR-023                | CLI Installation, Project Workspace, Project Store                                                                    | High     | Approved |


---

## Non-Functional Requirements


| ID           | Description                                                                                                                                                                                       | Category    | Priority | Status |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | -------- | ------ |
| NFR-ORCH-001 | The system shall expose orchestration outputs in a structured format that preserves machine-readable fields for run references, readiness states, recommendation items, and evidence citations.   | Usability   | High     | Approved |
| NFR-ORCH-002 | The system shall preserve recommendation traceability such that every returned recommendation item can be resolved to its cited evidence without requiring informal terminal-text interpretation. | Reliability | High     | Approved |
| NFR-ORCH-003 | The system shall complete status generation for stored-run metadata and already-derived facts within 2 seconds for a history of up to 1,000 stored runs.                                          | Performance | Medium   | Approved |
| NFR-ORCH-004 | The system shall return version and top-level help responses for an installed `novetest` CLI within 1 second on a supported onboarding environment.                                           | Performance | Medium   | Approved |


---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- This group owns only top-level orchestration and recommendation behavior. Fact derivation remains in the sub-product groups.
- `REQ-ORCH-005` intentionally constrains citation behavior at the top-level response layer, while localization-specific fact production remains in the Localization group.
- `REQ-ORCH-006`, `REQ-ORCH-007`, and `NFR-ORCH-004` are onboarding additions introduced from `design/product-plans/ux-goal.md` and are now approved.

---

## Assumptions

- The integrated workflow may skip ineligible downstream analysis stages without failing the entire top-level workflow, provided the result clearly reflects what was and was not available.

---

## Open Questions

None.
