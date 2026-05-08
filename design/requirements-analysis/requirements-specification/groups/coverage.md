# Requirements - Coverage

## Description

Coverage-sub-product behavior that structures native-derived coverage information into stored facts and computes cross-run coverage differences.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-COV-001 | The system shall derive stored coverage facts for a run from available native-derived coverage inputs and preserve their association to the originating run record. | Execute Test Workflow, Show Coverage Facts | SR-011 | Memory Entry, Run Record, Coverage Fact | High | Draft |
| REQ-COV-002 | The system shall represent available test-to-code mappings, line coverage, branch coverage, and uncovered code evidence as structured coverage facts for inspection. | Execute Test Workflow, Show Coverage Facts | SR-011 | Test Result, Coverage Fact, Code Location | High | Draft |
| REQ-COV-003 | The system shall compare stored coverage facts between two run references and identify structured coverage deltas for matching code locations where comparison is possible. | Compare Coverage Facts, Compare Run Behavior | SR-012 | Coverage Fact, Run Record, Code Location | High | Draft |
| REQ-COV-004 | The system shall return an explicit unavailable-or-incomplete state when requested coverage facts or coverage comparisons cannot be derived from the stored evidence for a run or run pair. | Show Coverage Facts, Compare Coverage Facts | SR-011, SR-012 | Memory Entry, Coverage Fact, Run Record | Medium | Draft |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-COV-001 | The system shall preserve coverage-fact traceability to the originating run reference and code location for every reported coverage fact or delta. | Reliability | High | Draft |
| NFR-COV-002 | The system shall generate coverage comparison results for two stored runs with up to 50,000 covered locations within 5 seconds when the needed evidence is already stored locally. | Performance | Medium | Draft |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- Coverage remains fact-only and does not rank faults or decide whether a gap is acceptable.

---

## Assumptions

- Coverage support may vary by native engine ecosystem, so unavailability is modeled as an explicit outcome rather than as an implicit failure.

---

## Open Questions

None.
