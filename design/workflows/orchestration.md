# Workflow - Orchestration

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/orchestration.md`](../interace-contract/orchestration.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `{ A | B | ... }` denotes alternative branches at one step.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## 1. Onboarding Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `novetest -v` / `novetest --version` | `orchestration/report_cli_identity` |
| `novetest -h` / `novetest --help` | `orchestration/describe_command_surface` |
| `novetest init` | `orchestration/initialize_project_workspace` |
| `report_cli_identity()` | - |
| `describe_command_surface()` | - |
| `initialize_project_workspace(workspace_context)` | `memory/create_project_store` -> `run/assess_engine_readiness` |

---

## 2. Operating Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `novetest test [target]` | `run/execute` -> `memory/store_run_evidence` -> `orchestration/evaluate_stage_eligibility` -> `coverage/derive_coverage_facts` -> `regression/resolve_latest_baseline` -> `regression/compare_runs` -> `localization/derive_localization_findings` -> `orchestration/synthesize_recommendation` |
| `novetest inspect <run_id>` | `memory/retrieve_run_evidence` -> `coverage/get_coverage_facts` -> `regression/resolve_latest_baseline` -> `regression/get_regression_facts` -> `localization/get_localization_findings` -> `replay/get_replay_result` |
| `novetest compare <run_id1> <run_id2>` | `regression/compare_runs` -> `coverage/compare_coverage_facts` |
| `novetest status` | `orchestration/build_status_view` |
| `synthesize_recommendation(fact_bundle)` | `orchestration/cite_recommendation_evidence` |
| `cite_recommendation_evidence(recommendation, supporting_facts)` | - |
| `evaluate_stage_eligibility(run_reference)` | `coverage/check_coverage_availability` -> `regression/check_regression_availability` -> `localization/check_localization_availability` -> `replay/check_replay_availability` |
| `build_status_view(run_history)` | `memory/list_run_history` -> `memory/get_memory_entry_availability` -> `coverage/check_coverage_availability` -> `regression/check_regression_availability` -> `localization/check_localization_availability` -> `replay/check_replay_availability` |

---

## Notes

- Section 1 onboarding flows must complete without a pre-existing Project Store. `novetest -v` and `novetest -h` are leaves (they only resolve CLI identity / command-surface state). `novetest init` is the only onboarding flow that mutates the workspace.
- `initialize_project_workspace` composes Project Store creation (`memory/create_project_store`, idempotent) and native-engine readiness assessment (`run/assess_engine_readiness`). The readiness outcome is informational - a missing or misconfigured native engine does not roll back the created Project Store.
- The `novetest test [target]` flow is the single place where Recommendations are emitted; `synthesize_recommendation` chains into `cite_recommendation_evidence` before returning.
- `novetest compare` composes Regression and Coverage outputs at the orchestration layer; `novetest regression compare` and `novetest coverage diff` remain available as fact-only sub-product surfaces.
- `evaluate_stage_eligibility` is reused only by the integrated `novetest test` flow; `build_status_view` is reused only by `novetest status`. Both fan out across all sub-products' `check_*_availability` interfaces.
- Operating flows assume an initialized Project Store; resolution of the active store happens transparently inside `memory/*` calls (see `workflows/memory.md`) and is not shown as a separate step here.
