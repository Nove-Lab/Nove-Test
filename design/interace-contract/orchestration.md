# Interface Contract - Orchestration

**Scope:** Top-level Nove Test orchestration product. Owns the onboarding entrypoints (CLI identity/help and project initialization), coordinates the integrated workflow across Run, Memory, Coverage, Regression, Localization, and Replay sub-products, and synthesizes recommendations with cited evidence.

**Upstream references**
- `design/product-plans/overall-plan.md`
- `design/product-plans/overall-architecture.md`
- `design/product-plans/ux-goal.md`
- `design/requirements-analysis/requirements-specification/groups/orchestration.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-001, SR-019, SR-020, SR-021, SR-022, SR-023)

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules within the tool boundary.
- Inputs and outputs are described with domain-entity vocabulary from `design/requirements-analysis/domain-model.md` (e.g. `Test Target`, `Run Reference`, `Run Record`, `Recommendation`, `Status`, `Evidence Citation`, `CLI Installation`, `Project Workspace`, `Project Store`).

---

## 1. Onboarding Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest -v` / `novetest --version` | External | (none) | CLI Installation identity view (installed version, command name, build/platform metadata). Resolves immediately after a successful install; does not require an initialized Project Workspace. (REQ-ORCH-006, NFR-ORCH-004) |
| `novetest -h` / `novetest --help` | External | (none) | Top-level command surface listing covering onboarding, orchestration, and sub-product command groups. Does not require an initialized Project Workspace. (REQ-ORCH-006, NFR-ORCH-004) |
| `novetest init` | External | Workspace context (resolved from current working directory) | Project Workspace initialization result containing the created Project Store handle (`.novetest/` location, initializedAt, store state), captured engine hints from the workspace, and a native-engine readiness summary surfaced from Run. Succeeds without manual Nove Test configuration. (REQ-ORCH-007) |
| `report_cli_identity()` | Internal | (none) | CLI Installation entity for the running binary (installed version, command name, install location, verifiedAt). Backs `novetest -v`. |
| `describe_command_surface()` | Internal | (none) | Structured command-surface description covering onboarding and operating commands. Backs `novetest -h`. |
| `initialize_project_workspace(workspace_context)` | Internal | Project Workspace context (workspace path, workspace type, engine hints) | Composed onboarding outcome - delegates Project Store creation to Memory (`create_project_store`), engine readiness inspection to Run (`assess_engine_readiness`), and returns the combined Project Workspace + Project Store + readiness result. Does not install or configure native engines. (SR-023) |

---

## 2. Operating Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest test [target]` | External | Test Target (target expression, optional workspace context) | Recommendation set with Evidence Citations, normalized Run Record summary, and per-stage availability flags for Coverage Fact / Regression Fact / Localization Finding / Replay Result |
| `novetest inspect <run_id>` | External | Run Reference | Aggregated run view composing the Memory Entry (Run Record, Test Result summary, captured-output handles) with the actual content of derived facts when available - Coverage Fact set, Regression Fact set versus prior run when resolvable, Localization Finding set, Replay Result - returned as a single top-level payload (distinct from `novetest memory show`, which returns Memory's own evidence and only availability flags) |
| `novetest compare <run_id1> <run_id2>` | External | Two Run References | Regression Fact set across the run pair, optional Coverage delta when Coverage Facts exist for both runs |
| `novetest status` | External | (none) | Status entity summarizing latest Run Reference, Run History readiness, and per-sub-report availability (Coverage / Regression / Localization / Replay) |
| `synthesize_recommendation(fact_bundle)` | Internal | Bundle of available facts (Coverage Fact set, Regression Fact set, Localization Finding set, Replay Result, Status) for a Run Reference | Recommendation set with attached Evidence Citations linking each item back to a supporting Run Reference and fact source |
| `cite_recommendation_evidence(recommendation, supporting_facts)` | Internal | Recommendation plus referenced facts (Run Reference, Coverage Fact, Regression Fact, Localization Finding, Replay Result) used to derive it | Recommendation with attached Evidence Citation set (each item resolvable to a Run Reference and fact source). Scoped to top-level Recommendations only; Localization owns citations on its own findings. |
| `evaluate_stage_eligibility(run_reference)` | Internal | Run Reference plus current Memory Entry availability state | Per-stage eligibility flags for Coverage / Regression / Localization / Replay used by the integrated workflow |
| `build_status_view(run_history)` | Internal | Run History (ordered Memory Entry collection) | Status entity with latest Run Reference, overall readiness, and sub-report availability flags |

---

## Notes

- All External CLI surfaces above must produce structured output suitable for AI-agent consumption (NFR-ORCH-001).
- The integrated `novetest test` flow is the only place where Recommendations are emitted; sub-product CLIs return facts only.
- Internal interfaces above are reused at least once by the workflow modeling step (sequence diagrams).
- Onboarding interfaces in Section 1 must remain callable without a pre-existing Project Store. `novetest -v` and `novetest -h` are usable immediately after install; `novetest init` is the command that creates the Project Store and is the only onboarding interface that mutates the workspace.
- `initialize_project_workspace` orchestrates rather than implements: Project Store creation lives in Memory (`create_project_store`), and native-engine readiness assessment lives in Run (`assess_engine_readiness`). Nove Test never installs or configures native engines as part of init (per `ux-goal.md`).
- Native-engine readiness reported by `novetest init` is informational - a missing or misconfigured engine does not cause init itself to fail, but the readiness summary must be machine-distinguishable so callers can act on it (NFR-RUN-004 from the Run contract).
- **Default verb (planned, Phase 6 activation).** `novetest test` is the canonical integrated workflow; once the workflow itself is no longer a stub, the CLI introduces a `<target>`-form alias so `novetest <target>` resolves to `novetest test <target>` (e.g. `novetest tests/test_x.py` ≡ `novetest test tests/test_x.py`). This mirrors `pytest`-style ergonomics for the entrypoint a returning user types most often, while keeping `novetest run` available as the explicit "raw evidence only" escape hatch. **Bare `novetest`** (no arguments) **remains an onboarding surface** that prints the structured help envelope (Section 1 `describe_command_surface`); it does **not** become an implicit "run all tests" trigger, because the integrated workflow can be expensive (Coverage + Regression + Localization + Replay) and silent expensive invocation is hostile to both humans and AI agents. The alias is gated on Phase 6 specifically so users do not first encounter the integrated entrypoint as a `not-implemented` stub. Sub-product verbs (`run`, `memory ...`, `inspect`, `compare`, `status`, etc.) always require explicit naming and never become the default.
