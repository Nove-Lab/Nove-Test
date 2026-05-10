# Requirements - Replay

## Description

Replay-sub-product behavior that reconstructs a prior run context, re-executes through the governed Run path, and classifies reproducibility against the original run.

---

## Functional Requirements

| ID | Description | Source Use Case | Source Responsibility | Related Entities | Priority | Status |
|----|------------|----------------|-----------------------|------------------|----------|--------|
| REQ-REP-001 | The system shall reconstruct replay context from stored run evidence, including the original run reference, resolved test target, and native engine context needed for replay execution. | Replay Prior Run | SR-017 | Replay Attempt, Memory Entry, Run Record, Native Engine, Test Target | High | Approved |
| REQ-REP-002 | The system shall submit replay execution through the same governed Run path used for ordinary execution where practical for the reconstructed context. | Replay Prior Run | SR-017 | Replay Attempt, Run Record, Test Target, Native Engine | High | Approved |
| REQ-REP-003 | The system shall compare the original run and replayed run outcomes and classify replay status as reproducible, inconsistent, or unable to replay. | Replay Prior Run | SR-018 | Replay Attempt, Run Record, Replay Result | High | Approved |
| REQ-REP-004 | The system shall preserve references to both the original run and the replayed run, when a replayed run is created, in the replay result returned to downstream consumers. | Replay Prior Run | SR-018 | Replay Attempt, Run Record, Replay Result | Medium | Approved |

---

## Non-Functional Requirements

| ID | Description | Category | Priority | Status |
|----|------------|----------|----------|--------|
| NFR-REP-001 | The system shall preserve replay-result traceability to the original run reference and replayed run reference when applicable. | Reliability | High | Approved |
| NFR-REP-002 | The system shall produce replay classification within 3 seconds after the replay execution run record becomes available. | Performance | Medium | Approved |

---

## Status Definitions

- **Draft**: Generated but not yet reviewed by a human
- **Approved**: Reviewed and accepted by a human; ready for implementation
- **Implemented**: Implemented in the system
- **Verified**: Verified through testing or validation

---

## Notes

- Replay depends on the Run and Memory groups but remains a separate fact-producing concern because it classifies reproducibility rather than normal execution outcome.

---

## Assumptions

- A replay attempt may complete with an `unable to replay` classification without producing a replayed run record if the stored context cannot be reconstructed sufficiently for governed execution.

---

## Open Questions

None.
