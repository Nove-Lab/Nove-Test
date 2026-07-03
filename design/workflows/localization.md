# Workflow - Localization

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/localization.md`](../interace-contract/localization.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## Workflow Sequences

| Interface | Workflow Sequence |
| --- | --- |
| `novetest localization <run_id>` | `localization/derive_localization_findings` |
| `novetest localization latest` | `localization/derive_latest_localization` |
| `derive_localization_findings(run_reference)` | `memory/retrieve_run_evidence` -> `coverage/get_coverage_facts` -> `regression/resolve_baseline_for_run` -> `regression/get_regression_facts` |
| `resolve_latest_analyzable_run()` | `memory/find_latest_analyzable_run` |
| `derive_latest_localization()` | `localization/resolve_latest_analyzable_run` -> `localization/derive_localization_findings` |
| `get_localization_findings(run_reference)` | - |
| `check_localization_availability(run_reference)` | `coverage/check_coverage_availability` |

---

## Notes

- `derive_localization_findings` combines failed Test Results from Memory with Coverage Facts and (when available) Regression Facts; Evidence Citations are produced inside this call without delegating to orchestration's `cite_recommendation_evidence`.
- `resolve_latest_analyzable_run` is reused by `derive_latest_localization` to bind the latest-flow to the same derivation path used by direct lookups.
- `check_localization_availability` requires Coverage Facts as a minimum precondition (failed tests are always available from Memory), so it delegates to `coverage/check_coverage_availability`.
