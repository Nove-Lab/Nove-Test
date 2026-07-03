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
| `novetest init [--engine <name>]` | External | Workspace context (the current working directory — init anchors where the user stands, never a walk-up) | Project Workspace initialization result containing the created Project Store handle (`.novetest/` location, initializedAt, store state), the anchored **engine pin** (`data.pinned_engine`; decision `2026-07-03-engine-selection-policy` D1), and a native-engine readiness summary for the pinned engine surfaced from Run. Exactly one viable engine pins automatically (zero new flags for the common case). A markerless directory creates **nothing** and reports discovered sub-project candidates (`no-engine-detected`, D4 bounded discovery); an ambiguous workspace creates **nothing** and requires an explicit `--engine <name>` (`engine-ambiguous`). `--engine` is optional, wins over detection in all cases, and re-pins in place on an existing store (run history retained). (REQ-ORCH-007) |
| `report_cli_identity()` | Internal | (none) | CLI Installation entity for the running binary (installed version, command name, install location, verifiedAt). Backs `novetest -v`. |
| `describe_command_surface()` | Internal | (none) | Structured command-surface description covering onboarding and operating commands. Backs `novetest -h`. |
| `initialize_project_workspace(workspace_context, engine?)` | Internal | Project Workspace context (workspace path) plus the optional CLI-validated `(ecosystem, engine_name)` pair from `--engine` | Three-way onboarding outcome union — success (Project Store + pin + readiness of the pinned engine; store creation delegated to Memory `create_project_store`, pin persistence to Memory `set_pinned_engine`, per-engine readiness to Run `probe_engine`), `no-engine-detected` (nothing created; D4 discovery report attached), or `engine-ambiguous` (nothing created; viable candidates attached). Does not install or configure native engines. (SR-023) |
| `resolve_workspace(cwd)` | Internal | Invocation directory | THE shared verb-level workspace resolution (decision D2): upward walk to the nearest `.novetest/` via Memory (`locate_project_store` / `find_nearest_store`), plus lazy D6 migration of pre-pin stores (one unambiguous engine choice → silent pin backfill; ambiguous → `engine-ambiguous` error). Every operating verb routes through this helper; no verb scans downward or guesses an engine. |

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
- `initialize_project_workspace` orchestrates rather than implements: Project Store creation lives in Memory (`create_project_store`), pin persistence in Memory (`set_pinned_engine`), and per-engine readiness assessment in Run (`probe_engine`). Nove Test never installs or configures native engines as part of init (per `ux-goal.md`).
- Native-engine readiness reported by `novetest init` is informational - a missing or misconfigured engine does not cause init itself to fail (a single-marker workspace pins even when its engine is misconfigured), but the readiness summary must be machine-distinguishable so callers can act on it (NFR-RUN-004 from the Run contract). The `no-engine-detected` / `engine-ambiguous` failures are *selection* failures, not readiness failures — they exist so a store never carries a guessed pin.
- **Anchored-pin execution semantics (decision `2026-07-03-engine-selection-policy`).** Every operating verb resolves its workspace by upward walk to the nearest `.novetest/` (`resolve_workspace`; nearest wins, no downward scan); the store's pin decides the engine. `novetest test` / `novetest run` accept a transient `--engine <name>` override that executes one-off WITHOUT re-pinning (D3). A bare invocation is workspace-scoped (`target_expression = ""`) regardless of the invoking subdirectory; explicit target paths are normalized to anchor-relative canonical POSIX form before `run/resolve_test_target`, so the same ask from any cwd shares one baseline series. Error-code surface (D7, agents pin to these strings): `no-engine-detected` (exit 4), `engine-ambiguous` (exit 2), `uninitialized` (exit 2, existing), `invalid-flag` (exit 2, existing) — the two new codes carry `data.candidates` as `[{path, ecosystem, engine_name}]`.
- **Default verb (planned, Phase 6 activation).** `novetest test` is the canonical integrated workflow; once the workflow itself is no longer a stub, the CLI introduces a `<target>`-form alias so `novetest <target>` resolves to `novetest test <target>` (e.g. `novetest tests/test_x.py` ≡ `novetest test tests/test_x.py`). This mirrors `pytest`-style ergonomics for the entrypoint a returning user types most often, while keeping `novetest run` available as the explicit "raw evidence only" escape hatch. **Bare `novetest`** (no arguments) **remains an onboarding surface** that prints the structured help envelope (Section 1 `describe_command_surface`); it does **not** become an implicit "run all tests" trigger, because the integrated workflow can be expensive (Coverage + Regression + Localization + Replay) and silent expensive invocation is hostile to both humans and AI agents. The alias is gated on Phase 6 specifically so users do not first encounter the integrated entrypoint as a `not-implemented` stub. Sub-product verbs (`run`, `memory ...`, `inspect`, `compare`, `status`, etc.) always require explicit naming and never become the default.
