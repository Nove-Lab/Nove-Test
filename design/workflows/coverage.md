# Workflow - Coverage

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/coverage.md`](../interace-contract/coverage.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## Workflow Sequences

| Interface | Workflow Sequence |
| --- | --- |
| `novetest coverage show <run_id>` | `coverage/get_coverage_facts` -> `coverage/derive_coverage_facts` |
| `novetest coverage diff <run_id1> <run_id2>` | `coverage/compare_coverage_facts` |
| `derive_coverage_facts(run_reference)` | `memory/retrieve_run_evidence` |
| `get_coverage_facts(run_reference)` | `memory/retrieve_run_evidence` |
| `compare_coverage_facts(run_reference_1, run_reference_2)` | `coverage/get_coverage_facts` |
| `check_coverage_availability(run_reference)` | - |

---

## Notes

- `novetest coverage show` first attempts `get_coverage_facts` (cached / previously derived) and falls back to `derive_coverage_facts` when the run has not yet been processed; both paths read the underlying evidence through `memory/retrieve_run_evidence`.
- `compare_coverage_facts` is reused by `novetest compare` (Orchestration) and by `regression/compare_runs` to incorporate Coverage changes.
- `check_coverage_availability` is reused by `orchestration/evaluate_stage_eligibility`, `orchestration/build_status_view`, and `localization/check_localization_availability`.
