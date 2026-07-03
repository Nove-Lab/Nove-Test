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
| `novetest reset --confirm` | `orchestration/reset_project_workspace` |
| `report_cli_identity()` | - |
| `describe_command_surface()` | - |
| `initialize_project_workspace(workspace_context)` | `memory/create_project_store` -> `run/assess_engine_readiness` |
| `reset_project_workspace(workspace_context)` | `memory/locate_project_store` -> `memory/wipe_project_store` -> `orchestration/initialize_project_workspace` |

---

## 2. Operating Workflows

| Interface | Workflow Sequence |
| --- | --- |
| `novetest test [target] [--reruns N]` | `run/execute` -> `memory/store_run_evidence` -> `orchestration/evaluate_stage_eligibility` -> `coverage/derive_coverage_facts` -> `regression/resolve_latest_baseline` -> `regression/compare_runs` -> `localization/derive_localization_findings` -> `{ --reruns N > 0 AND failed tests: replay/replay_run | else: skip }` -> `orchestration/synthesize_recommendation` |
| `novetest inspect <run_id>` | `memory/retrieve_run_evidence` -> `coverage/get_coverage_facts` -> `regression/resolve_latest_baseline` -> `regression/get_regression_facts` -> `localization/get_localization_findings` -> `replay/get_replay_result` |
| `novetest compare <run_id1> <run_id2>` | `regression/compare_runs` -> `coverage/compare_coverage_facts` |
| `novetest status` | `orchestration/build_status_view` |
| `synthesize_recommendation(fact_bundle)` | `orchestration/cite_recommendation_evidence` |
| `cite_recommendation_evidence(recommendation, supporting_facts)` | - |
| `evaluate_stage_eligibility(run_reference)` | `coverage/check_coverage_availability` -> `regression/check_regression_availability` -> `localization/check_localization_availability` -> `replay/check_replay_availability` |
| `build_status_view(run_history)` | `memory/list_run_history` -> `memory/get_memory_entry_availability` -> `coverage/check_coverage_availability` -> `regression/check_regression_availability` -> `localization/check_localization_availability` -> `replay/check_replay_availability` |

---

## Integrated replay sub-workflow (`novetest test --reruns N`)

Opt-in per decision [`2026-06-25-test-reruns-flag-and-replay-integration`](../../agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md): default `N = 0` preserves the pre-integration `novetest test` behavior byte-for-byte (no Replay call, `data.stage_eligibility.replay == "not_run"`). With `N > 0` **and** at least one failed test in the just-persisted Run Record, the integrated workflow invokes Replay after the Localization step and before synthesis:

`{ reruns > 0 AND failed tests: replay/replay_run(original_run_reference, reruns=N) -> memory/retrieve_run_evidence (availability-flag refresh) | else: skip }` -> `orchestration/build_fact_bundle(replay_results=...)` -> `orchestration/synthesize_recommendation`

**Attempt granularity (API adaptation, recorded 2026-07-03):** the Replay engine's unit of work is the **whole original run** — `replay_run` has no per-test `target` parameter and persists exactly one Replay Result per original run id. The integrated workflow therefore performs **one** whole-run attempt with `reruns=N` (every test, the failed ones included, re-executes N times); the Replay classifier performs the per-test divergence analysis internally and names the focal `test_id` when exactly one test diverges. This deviates from the task brief's per-failed-test loop sketch, which is not implementable against the shipped Replay API without engine changes the decision rules out.

**Outcome mapping:**

| `replay_run` outcome | `stage_eligibility.replay` | `per_stage_reasons.replay` | `FactBundle.replay_results` |
| --- | --- | --- | --- |
| not attempted (`N = 0` or zero failed tests) | `not_run` | `replay_not_run` | `()` |
| `ReplayResult` (any classification, incl. `unable_to_replay`) | `available` | `None` | `(result,)` |
| `ReplayUnavailable` (attempt could not start) | `unavailable` | engine reason verbatim | `()` |

A `ReplayUnavailable` outcome is best-effort like every downstream stage: the invocation still succeeds and `unavailable_analysis` explains the gap when tests failed. Exit codes are unchanged (dominated by the Run Record status; replay outcomes never affect them). Replay-execution runs persist as first-class Memory Entries and the Replay Result caches at `<store>/replay/results/run_<original_id>/replay_result.json`, exactly as the standalone `novetest replay` verb produces.

**FactBundle shape:** this cycle renamed `FactBundle.replay_result: ReplayResult | None` to `replay_results: tuple[ReplayResult, ...]` (brief §3). `match_flaky_suspected` emits one hit per result classified `inconsistent`, in tuple order; each hit's `replay_result` evidence citation references the result it was emitted from. Today the tuple holds 0 or 1 elements (one whole-run attempt); the list shape is forward-compatible with per-test replay scoping.

**Error paths** (decision §"Error paths"):

| Trigger | Exit | `errors[0].code` |
| --- | --- | --- |
| `--reruns` negative | 2 | `invalid-flag` |
| Replay attempt cannot start (`ReplayUnavailable`) | 0 or 3 (dominated by Run) | none — surfaced via `stage_eligibility.replay = "unavailable"` |

---

## Reset

`novetest reset --confirm` replaces the previously documented `rm -rf .novetest && novetest init` "start over" pattern with a first-class, envelope-emitting verb, per decision [`2026-06-24-reset-verb-and-store-wipe-primitive`](../../agent-comms/decisions/2026-06-24-reset-verb-and-store-wipe-primitive.md). It wipes the active Project Store and re-initializes in one operation. It is a setup-class verb, enumerated in the `--help` envelope's `data.onboarding[]` beside `init`.

**Workflow** (`orchestration/reset_project_workspace`):

`memory/locate_project_store` -> `{ found: memory/wipe_project_store -> orchestration/initialize_project_workspace | none: raise ProjectStoreNotFoundError }`

The wipe is atomic per the decision's §"Atomicity guarantee": the live `.novetest/` is renamed to a `.novetest.deleting.<ulid>/` staging path (single `rename(2)`) before removal, then `create_project_store` rebuilds the skeleton and `assess_engine_readiness` re-probes. A crash mid-wipe leaves an "uninitialized" workspace recoverable by a fresh `novetest init`. The destructive `memory/wipe_project_store` primitive is owned by the Memory engine; orchestration only composes it.

**Happy-path envelope** (`command: "reset"`, exit 0):

```json
{
  "schema": "novetest/v1",
  "command": "reset",
  "ok": true,
  "data": {
    "store_path": "/abs/path/.novetest",
    "store_state": "ready",
    "previous_initialized_at": 1717939496000,
    "initialized_at": 1719215123000,
    "items_removed": { "runs": 12, "tombstones": 1, "coverage_facts": 12, "regression_pairs": 7, "localization_findings": 8, "replay_results": 2 },
    "engine_readiness": { "...": "identical shape to init's engine_readiness" }
  },
  "errors": [],
  "warnings": []
}
```

**Error paths:**

| Trigger | Exit | `errors[0].code` |
| --- | --- | --- |
| `--confirm` missing | 2 | `confirm-required` |
| No `.novetest/` in walk-up | 2 | `uninitialized` |
| `store.json` unreadable — reset deliberately refuses to wipe a corrupt store | 5 | `store-corrupt` |
| Filesystem error during wipe (atomic-rename guard leaves the original intact) | 5 | `store-wipe-failed` |

`--confirm` is mandatory: the CLI is agent-first, so an interactive confirmation prompt would break agent invocation; a required flag is the agent-friendly equivalent.

---

## Notes

- Section 1 onboarding flows must complete without a pre-existing Project Store. `novetest -v` and `novetest -h` are leaves (they only resolve CLI identity / command-surface state). `novetest init` is the only onboarding flow that mutates the workspace.
- `initialize_project_workspace` composes Project Store creation (`memory/create_project_store`, idempotent) and native-engine readiness assessment (`run/assess_engine_readiness`). The readiness outcome is informational - a missing or misconfigured native engine does not roll back the created Project Store.
- The `novetest test [target]` flow is the single place where Recommendations are emitted; `synthesize_recommendation` chains into `cite_recommendation_evidence` before returning.
- `novetest compare` composes Regression and Coverage outputs at the orchestration layer; `novetest regression compare` and `novetest coverage diff` remain available as fact-only sub-product surfaces.
- `evaluate_stage_eligibility` is reused only by the integrated `novetest test` flow; `build_status_view` is reused only by `novetest status`. Both fan out across all sub-products' `check_*_availability` interfaces.
- Operating flows assume an initialized Project Store; resolution of the active store happens transparently inside `memory/*` calls (see `workflows/memory.md`) and is not shown as a separate step here.
