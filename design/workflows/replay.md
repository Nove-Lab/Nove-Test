# Workflow - Replay

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/replay.md`](../interace-contract/replay.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## Workflow Sequences

| Interface | Workflow Sequence |
| --- | --- |
| `novetest replay <run_id>` | `replay/replay_run` |
| `replay_run(run_reference)` | `replay/reconstruct_replay_context` -> `run/execute_with_engine_context` -> `memory/store_run_evidence` -> `replay/classify_replay_consistency` |
| `reconstruct_replay_context(run_reference)` | `memory/retrieve_run_evidence` |
| `classify_replay_consistency(original_run_reference, replayed_run_reference)` | `memory/retrieve_run_evidence` |
| `get_replay_result(run_reference)` | - |
| `check_replay_availability(run_reference)` | `memory/retrieve_run_evidence` |

---

## Notes

- Replay reuses the governed Run path by handing the reconstructed context to `run/execute_with_engine_context`, ensuring the replay run flows through the same Native Engine selection.
- The replayed Run Record is persisted via `memory/store_run_evidence` before consistency classification so that the replay run is a first-class Memory Entry citable by Recommendations.
- `get_replay_result` is a cached lookup consumed by `orchestration/novetest inspect`; `check_replay_availability` is consumed by `orchestration/evaluate_stage_eligibility` and `orchestration/build_status_view`.
