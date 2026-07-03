# Workflow - Regression

**Scope:** Workflow sequences for every interface defined in [`design/interace-contract/regression.md`](../interace-contract/regression.md).

**Conventions**
- Interfaces are referenced as `module/interface_name` to make their origin traceable across documents.
- `->` denotes sequential calls inside a workflow.
- `-` means the workflow ends inside the engine itself (no further interface call).

---

## Workflow Sequences

| Interface | Workflow Sequence |
| --- | --- |
| `novetest regression compare <run_id1> <run_id2>` | `regression/compare_runs` |
| `novetest regression latest` | `regression/derive_latest_regression` |
| `compare_runs(run_reference_1, run_reference_2)` | `memory/retrieve_run_evidence` -> `coverage/compare_coverage_facts` |
| `resolve_baseline_for_run(memory_entry)` | `memory/find_runs_for_target` |
| `resolve_latest_baseline(test_target)` | `memory/find_runs_for_target` -> `regression/resolve_baseline_for_run` |
| `derive_latest_regression()` | `regression/resolve_latest_baseline` -> `regression/compare_runs` |
| `get_regression_facts(run_reference_1, run_reference_2)` | - |
| `check_regression_availability(run_reference)` | `memory/retrieve_run_evidence` -> `memory/find_runs_for_target` |

---

## Notes

- `compare_runs` retrieves both Run Records via `memory/retrieve_run_evidence` and incorporates Coverage changes through `coverage/compare_coverage_facts` when both runs have Coverage Facts.
- `resolve_baseline_for_run` is the single engine-aware selector (`decisions/2026-07-03-engine-selection-policy.md` D5): newest strictly-older live run sharing the input run's `target_expression` AND `engine_name`. Shared by `resolve_latest_baseline` and by Orchestration's `inspect` / `status` compositions, so all baseline-selection paths agree by construction.
- `resolve_latest_baseline` is reused by `derive_latest_regression` and by `orchestration/novetest test` (to find the previous comparable run for the freshly stored run).
- `get_regression_facts` is a cached lookup consumed by `orchestration/novetest inspect` and `localization/derive_localization_findings`.
- `check_regression_availability` returns true only when `find_runs_for_target` yields a comparable prior run (same Test Target, same `engine_name` per D5) for the given Run Reference.
