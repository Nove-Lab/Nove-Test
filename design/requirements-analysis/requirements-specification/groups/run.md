# Requirements - Run

## Description

Run-sub-product behavior that resolves the requested target, selects the correct native engine path, executes tests, normalizes native results, and assigns stable run references for later workflows.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-RUN-001 | The system shall resolve each requested execution scope into a normalized test target representation that preserves the target expression, target type, and workspace context used for the run. | Execute Test Workflow, Run Test Target, Supply Test Target Material | SR-002 | Test Target | High | Draft |
| REQ-RUN-002 | The system shall determine the native engine context for each requested or replayed run before invoking execution. | Run Test Target, Replay Prior Run | SR-003 | Test Target, Native Engine, Run Record | High | Draft |
| REQ-RUN-003 | The system shall invoke the selected native engine against the resolved test target and capture the resulting native result bundle for downstream normalization. | Run Test Target, Replay Prior Run, Provide Native Execution Facts | SR-004 | Test Target, Native Engine, Native Result | High | Draft |
| REQ-RUN-004 | The system shall normalize each native result bundle into a run record that includes execution status, summary counts, failed-test references where available, and execution metadata required by downstream workflows. | Execute Test Workflow, Run Test Target, Replay Prior Run | SR-005 | Native Result, Run Record, Test Result | High | Draft |
| REQ-RUN-005 | The system shall assign a stable run reference to each normalized run record before the run is exposed for storage, inspection, comparison, replay, or citation. | Execute Test Workflow, Run Test Target, Replay Prior Run | SR-006 | Run Reference, Run Record | High | Draft |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-RUN-001 | The system shall preserve the native engine as the source of truth for test discovery, assertion semantics, and native reporting behavior. | Reliability | High | Draft |
| NFR-RUN-002 | The system shall preserve enough execution metadata in normalized run records to support deterministic downstream storage, comparison, and replay workflows. | Maintainability | High | Draft |
| NFR-RUN-003 | The system shall return a normalized run record or an explicit execution-failure state within 5 seconds after the underlying native engine process exits. | Performance | Medium | Draft |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- The Run group does not decide the meaning of coverage gaps, regressions, suspicious locations, or recommendations.
- Replay reuses this group’s execution behavior but does not own it.

---

## Assumptions

- A normalized run record may represent a failed, interrupted, or partially completed execution attempt if the native engine was invoked and observable execution state exists.

---

## Open Questions

None.
