# Interface Contract - Memory

**Scope:** Memory sub-product. Persists Run Records and Native Results, retrieves stored evidence by Run Reference, exposes Run History for latest/status workflows, and supports safer deletion that preserves citation traceability via tombstones.

**Upstream references**
- `design/product-plans/subproducts/nove-test-memory.md`
- `design/requirements-analysis/requirements-specification/groups/memory.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-007, SR-008, SR-009, SR-010)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration, Run, Coverage, Regression, Localization, Replay) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Memory Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest memory list` | External | (none) | Run History view (ordered Memory Entry summaries with Run Reference, Test Target, Native Engine context, status, availability flags for Coverage Fact / Regression Fact / Localization Finding / Replay Result) |
| `novetest memory show <run_id>` | External | Run Reference | Memory Entry view with full Run Record, Test Result summary, captured-output handles, and availability state of related artifacts |
| `novetest memory delete <run_id>` | External | Run Reference | Deletion acknowledgement plus retained Memory Entry tombstone preserving Run Reference traceability |
| `store_run_evidence(run_record, native_result)` | Internal | Run Record (with Run Reference) and its Native Result handle | Persisted Memory Entry (entryId, runId, storedAt, availabilityState) appended to Run History |
| `retrieve_run_evidence(run_reference)` | Internal | Run Reference | Memory Entry containing Run Record, Test Result entries, Native Result handle, and current availability state |
| `list_run_history(filter?)` | Internal | Optional filter (e.g. by Test Target, Native Engine, status, time range) | Run History (ordered Memory Entry summaries with Run Reference and availability flags) |
| `find_runs_for_target(test_target)` | Internal | Test Target | Ordered subset of Run History whose Run Records executed the same resolved Test Target (used by Regression latest baseline resolution) |
| `find_latest_analyzable_run(criteria)` | Internal | Criteria for analyzability (e.g. has failed Test Results, has Coverage Fact availability) | Run Reference of the most recent Memory Entry meeting the criteria, or unavailable state (used by Localization latest) |
| `delete_run_evidence(run_reference)` | Internal | Run Reference | Tombstone-preserving deletion result; active Memory Entry is removed but Run Reference retains trace integrity for Evidence Citation |
| `get_memory_entry_availability(run_reference)` | Internal | Run Reference | Availability state describing which derived facts (Coverage / Regression / Localization / Replay) and Native Result fragments are currently retrievable |

---

## Notes

- Tombstone behavior (REQ-MEM-005, NFR-MEM-003) is exposed via the `delete_*` interfaces; downstream Evidence Citation consumers can still resolve a deleted Run Reference to a tombstoned Memory Entry.
- Memory does not derive Coverage Fact, Regression Fact, Localization Finding, or Replay Result; those engines call `retrieve_run_evidence` and `find_*` interfaces here as their source.
- All retrieval interfaces honor the durability guarantee from NFR-MEM-001.
