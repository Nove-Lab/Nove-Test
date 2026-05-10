# Requirements - Localization

## Description

Localization-sub-product behavior that selects an analyzable run and derives ranked suspicious code locations from failed-test, coverage, and regression evidence.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-LOC-001 | The system shall resolve `localization latest` to the most recent stored run that has the evidence required for localization-oriented analysis. | Review Latest Localization | SR-015 | Run History, Run Reference, Run Record | High | Approved |
| REQ-LOC-002 | The system shall derive localization findings by combining failed-test context with available coverage facts for the selected run. | Execute Test Workflow, Localize Faults, Review Latest Localization | SR-016 | Run Record, Test Result, Coverage Fact, Localization Finding, Code Location | High | Approved |
| REQ-LOC-003 | The system shall incorporate available regression facts into localization findings when regression evidence exists for the relevant run context. | Execute Test Workflow, Localize Faults, Review Latest Localization | SR-016 | Run Record, Regression Fact, Localization Finding, Code Location | Medium | Approved |
| REQ-LOC-004 | The system shall return localization findings as ranked suspicious code locations with associated score or equivalent ranking evidence and related failed-test references. | Localize Faults, Review Latest Localization | SR-016 | Localization Finding, Code Location, Test Result | High | Approved |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-LOC-001 | The system shall preserve traceability from each localization finding to the run evidence used to rank it. | Reliability | High | Approved |
| NFR-LOC-002 | The system shall produce localization results for a run with up to 500 failed-test references and 50,000 covered locations within 8 seconds when required evidence is already stored locally. | Performance | Medium | Approved |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- Localization remains fact-oriented: it ranks suspicious locations but does not prescribe a fix.

---

## Assumptions

- Localization may still produce findings when regression evidence is absent, provided failed-test and coverage evidence are available.

---

## Open Questions

None.
