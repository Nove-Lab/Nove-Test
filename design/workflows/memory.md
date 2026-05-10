# Workflow - Memory

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/memory.md`](../interace-contract/memory.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## Workflow Sequences

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

- Every Memory interface is a leaf operation against the persisted Run History; cross-engine fan-out happens at the orchestration layer, not from inside Memory.
- `find_runs_for_target` and `find_latest_analyzable_run` are kept distinct from `list_run_history` so Regression and Localization can request narrowly-scoped subsets without re-implementing filtering logic.
- `delete_run_evidence` preserves a tombstone trace; downstream Evidence Citations remain resolvable to the original Run Reference even after deletion.
