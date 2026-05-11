# Interface Contract - Memory

**Scope:** Memory sub-product. Creates and governs the per-project `.novetest/` Project Store, persists Run Records and Native Results inside it, retrieves stored evidence by Run Reference, exposes Run History for latest/status workflows, and supports safer deletion that preserves citation traceability via tombstones.

**Upstream references**
- `design/product-plans/subproducts/nove-test-memory.md`
- `design/product-plans/ux-goal.md`
- `design/requirements-analysis/requirements-specification/groups/memory.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-007, SR-008, SR-009, SR-010, SR-023, SR-025)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration, Run, Coverage, Regression, Localization, Replay) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md` (including `Project Workspace` and `Project Store` for onboarding interfaces).

---

## 1. Project Store Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `create_project_store(project_workspace)` | Internal | Project Workspace context (workspace path, workspace type, engine hints) | Project Store handle (storePath = `<workspace>/.novetest/`, initializedAt, storeState) for the newly created store, registered as the active project store for the workspace. Idempotent on re-invocation against an already-initialized workspace: returns the existing Project Store handle without overwriting durable state. (REQ-MEM-006) |
| `locate_project_store(workspace_context)` | Internal | Workspace context (resolved from current working directory) | Active Project Store handle for the workspace, or unavailable state when no `.novetest/` has been initialized. All other Memory interfaces below resolve their durable state through this handle. (REQ-MEM-007) |
| `get_project_store_state()` | Internal | (none; uses active Project Store) | Project Store metadata (storePath, initializedAt, storeState, schema/version markers) suitable for status, inspection, and self-update flows. |

---

## 2. Memory Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest memory list` | External | (none) | Run History view (ordered Memory Entry summaries with Run Reference, Test Target, Native Engine context, status, availability flags for Coverage Fact / Regression Fact / Localization Finding / Replay Result) |
| `novetest memory show <run_id>` | External | Run Reference | Memory Entry view with full Run Record, Test Result summary, captured-output handles, and availability state of related artifacts |
| `novetest memory delete <run_id>` | External | Run Reference | Deletion acknowledgement plus retained Memory Entry tombstone preserving Run Reference traceability |
| `store_run_evidence(run_record, native_result)` | Internal | Run Record (with Run Reference) and its Native Result handle | Persisted Memory Entry (entryId, runId, storedAt, availabilityState) appended to Run History inside the active Project Store |
| `retrieve_run_evidence(run_reference)` | Internal | Run Reference | Memory Entry containing Run Record, Test Result entries, Native Result handle, and current availability state |
| `list_run_history(filter?)` | Internal | Optional filter (e.g. by Test Target, Native Engine, status, time range) | Run History (ordered Memory Entry summaries with Run Reference and availability flags) |
| `find_runs_for_target(test_target)` | Internal | Test Target | Ordered subset of Run History whose Run Records executed the same resolved Test Target (used by Regression latest baseline resolution) |
| `find_latest_analyzable_run(criteria)` | Internal | Criteria for analyzability (e.g. has failed Test Results, has Coverage Fact availability) | Run Reference of the most recent Memory Entry meeting the criteria, or unavailable state (used by Localization latest) |
| `delete_run_evidence(run_reference)` | Internal | Run Reference | Tombstone-preserving deletion result; active Memory Entry is removed but Run Reference retains trace integrity for Evidence Citation |
| `get_memory_entry_availability(run_reference)` | Internal | Run Reference | Availability state describing which derived facts (Coverage / Regression / Localization / Replay) and Native Result fragments are currently retrievable |

---

## Notes

- Section 1 interfaces are the entry point for the onboarding flow. Orchestration's `initialize_project_workspace` delegates Project Store creation to `create_project_store`; every Section 2 interface resolves its durable state through `locate_project_store` against the active Project Workspace.
- Project Store creation is idempotent (REQ-MEM-006); re-running `novetest init` on an already-initialized workspace must not destroy durable run evidence or tombstones.
- Project-scoped state - Memory Entries, Run History, Coverage / Regression / Localization / Replay artifacts, Recommendations, Status caches - lives inside `.novetest/`. Users are not expected to read or edit those files directly (NFR-MEM-004); the Memory and Orchestration command surfaces are the supported access path.
- Tombstone behavior (REQ-MEM-005, NFR-MEM-003) is exposed via the `delete_*` interfaces; downstream Evidence Citation consumers can still resolve a deleted Run Reference to a tombstoned Memory Entry.
- Memory does not derive Coverage Fact, Regression Fact, Localization Finding, or Replay Result; those engines call `retrieve_run_evidence` and `find_*` interfaces here as their source.
- All retrieval interfaces honor the durability guarantee from NFR-MEM-001.
