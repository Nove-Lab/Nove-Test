# Requirements - Memory

## Description

Memory-sub-product behavior that persists run evidence, retrieves stored evidence by run reference, exposes stored history, and supports safer deletion behavior that preserves traceability.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-MEM-001 | The system shall persist each normalized run record together with its associated native-derived artifacts as a stored memory entry keyed by run reference. | Execute Test Workflow, Store Run Evidence | SR-007 | Memory Entry, Run Record, Native Result, Run Reference, Run History | High | Draft |
| REQ-MEM-002 | The system shall retrieve stored run evidence and its availability state by run reference for inspection, comparison, localization, replay, and recommendation workflows. | Execute Test Workflow, Inspect Run Evidence, Manage Stored Runs, Compare Coverage Facts, Compare Run Behavior, Localize Faults, Replay Prior Run, Generate Recommendations | SR-008 | Run Reference, Memory Entry, Run Record | High | Draft |
| REQ-MEM-003 | The system shall list stored runs in historical order and include enough summary information to identify each run and its available related artifacts or derived facts. | Manage Stored Runs, Check Testing Status | SR-009 | Run History, Memory Entry, Run Reference | Medium | Draft |
| REQ-MEM-004 | The system shall support deletion of stored run evidence from active memory scope by run reference. | Manage Stored Runs | SR-010 | Memory Entry, Run Reference, Run History | Medium | Draft |
| REQ-MEM-005 | When stored run evidence is deleted from active memory scope, the system shall preserve a tombstone or equivalent retained trace sufficient to maintain run-history integrity and evidence-citation traceability. | Manage Stored Runs | SR-010 | Memory Entry, Run Reference, Run History | High | Draft |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-MEM-001 | The system shall preserve stored run evidence durably enough that a successfully persisted run remains retrievable after process restart. | Reliability | High | Draft |
| NFR-MEM-002 | The system shall retrieve stored run metadata by run reference within 1 second and full stored evidence within 3 seconds for a history of up to 1,000 stored runs. | Performance | Medium | Draft |
| NFR-MEM-003 | The system shall record deletion operations in a way that prevents silent loss of citation-relevant history. | Security | High | Draft |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- `REQ-MEM-004` and `REQ-MEM-005` are split intentionally so active-memory deletion and retained-trace behavior can be implemented and tested separately.
- The exact tombstone representation is left implementation-neutral at this stage.

---

## Assumptions

- Deletion removes active evidence access for normal workflows but does not erase the minimum historical trace needed to keep references and citations meaningful.

---

## Open Questions

None.
