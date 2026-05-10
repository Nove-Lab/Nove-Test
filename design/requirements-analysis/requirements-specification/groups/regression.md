# Requirements - Regression

## Description

Regression-sub-product behavior that resolves the correct latest comparison baseline for a test target and derives factual behavior changes across runs.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-REG-001 | The system shall resolve `regression latest` against the two most recent comparable stored runs for the same resolved test target. | Review Latest Regression | SR-013 | Run History, Run Reference, Run Record, Test Target | High | Approved |
| REQ-REG-002 | The system shall compare two run records and derive structured regression facts for pass-to-fail, fail-to-pass, and other observable test outcome transitions. | Execute Test Workflow, Compare Run Behavior, Review Latest Regression | SR-014 | Run Record, Test Result, Regression Fact | High | Approved |
| REQ-REG-003 | The system shall derive structured regression facts for native output differences between compared runs when such output is available in stored evidence. | Compare Run Behavior, Review Latest Regression | SR-014 | Run Record, Regression Fact | Medium | Approved |
| REQ-REG-004 | The system shall incorporate available coverage changes into regression results when comparable coverage facts exist for the selected run pair. | Execute Test Workflow, Compare Run Behavior, Review Latest Regression | SR-014 | Run Record, Coverage Fact, Regression Fact | Medium | Approved |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-REG-001 | The system shall produce deterministic regression results for the same pair of stored run references and the same stored evidence state. | Reliability | High | Approved |
| NFR-REG-002 | The system shall complete regression comparison for two stored runs with up to 10,000 test results within 5 seconds when required evidence is already stored locally. | Performance | Medium | Approved |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- Baseline selection is target-scoped by design and should not silently compare unrelated recent runs.

---

## Assumptions

- ?œComparable??runs share a resolved test target and enough normalized evidence to support meaningful transition analysis.

---

## Open Questions

None.
