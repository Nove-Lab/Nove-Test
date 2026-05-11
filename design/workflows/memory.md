# Workflow - Memory

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/memory.md`](../interace-contract/memory.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## 1. Project Store Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `create_project_store(project_workspace)` | `memory/locate_project_store` |
| `locate_project_store(workspace_context)` | - |
| `get_project_store_state()` | `memory/locate_project_store` |

---

## 2. Memory Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `novetest memory list` | `memory/list_run_history` |
| `novetest memory show <run_id>` | `memory/retrieve_run_evidence` -> `memory/get_memory_entry_availability` |
| `novetest memory delete <run_id>` | `memory/delete_run_evidence` |
| `store_run_evidence(run_record, native_result)` | - |
| `retrieve_run_evidence(run_reference)` | - |
| `list_run_history(filter?)` | - |
| `find_runs_for_target(test_target)` | - |
| `find_latest_analyzable_run(criteria)` | - |
| `delete_run_evidence(run_reference)` | - |
| `get_memory_entry_availability(run_reference)` | - |

---

## Notes

- Section 1 governs the `.novetest/` Project Store boundary. `create_project_store` first calls `locate_project_store` to satisfy the idempotency guarantee from the contract (REQ-MEM-006): if an active store is already registered for the workspace, the existing handle is returned without overwriting durable state.
- Every Section 2 interface implicitly resolves its durable state through the active Project Store. The lookup is treated as a precondition rather than an explicit step here to keep sequences readable; production implementations are free to call `memory/locate_project_store` defensively at the head of each operation.
- Every Memory interface is a leaf operation against the persisted Run History; cross-engine fan-out happens at the orchestration layer, not from inside Memory.
- `find_runs_for_target` and `find_latest_analyzable_run` are kept distinct from `list_run_history` so Regression and Localization can request narrowly-scoped subsets without re-implementing filtering logic.
- `delete_run_evidence` preserves a tombstone trace; downstream Evidence Citations remain resolvable to the original Run Reference even after deletion.
