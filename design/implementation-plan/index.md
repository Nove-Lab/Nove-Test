# Implementation Plan - Index

**Audience:** Engineers building Nove Test, AI agents that need to ground their suggestions in our actual technology stack, and reviewers comparing this against the design docs upstream.

**Purpose:** Translate the planning, requirements, interface, and workflow design into concrete implementation decisions - language, libraries, project structure, native-engine integration strategy, persistence model, distribution, and delivery sequence. Reference-grade; lives long.

**Upstream design references**
- Product plans: [`design/product-plans/`](../product-plans/)
- Requirements analysis: [`design/requirements-analysis/`](../requirements-analysis/)
- Interface contracts: [`design/interace-contract/`](../interace-contract/)
- Workflow sequences: [`design/workflows/`](../workflows/)
- Project structure hint: [`CLAUDE.md`](../../CLAUDE.md)

---

## Document Map

| Document | Scope |
| --- | --- |
| [`foundations.md`](./foundations.md) | Language, runtime version, CLI framework, subprocess management, persistence, project structure, self-testing, distribution |
| [`engine-adapters.md`](./engine-adapters.md) | Per-ecosystem native engine integration: pytest, jest, JUnit, go test, cargo test, dotnet test - including coverage emission and per-test attribution feasibility |
| [`localization-strategy.md`](./localization-strategy.md) | SBFL formula choice, graceful degradation when per-test coverage is unavailable, code-location granularity, ranking output shape |
| [`recommendation-synthesis.md`](./recommendation-synthesis.md) | Recommendation categories, evidence citation schema, determinism contract, why no LLM in the synthesis path |
| [`delivery-phasing.md`](./delivery-phasing.md) | Phased build sequence, definition-of-done per phase, risks, open questions |

---

## Decisions Snapshot

A reader who needs only the headline answers should be able to stop here.

| Area | Decision | Doc |
| --- | --- | --- |
| Implementation language | Python 3.11+ (target 3.11 floor; CI on 3.11/3.12/3.13) | [`foundations.md`](./foundations.md#1-language-and-runtime) |
| CLI framework | Cyclopts (Click as the conservative fallback) | [`foundations.md`](./foundations.md#2-cli-framework-and-output-contract) |
| Subprocess primitive | `asyncio.create_subprocess_exec` with concurrent stdout/stderr drains | [`foundations.md`](./foundations.md#3-subprocess-management) |
| Persistence | Hybrid: SQLite (WAL) index + filesystem JSON / native artifacts, ULID-keyed run directories | [`foundations.md`](./foundations.md#4-persistence) |
| Domain models | `dataclasses(slots=True, frozen=True)` internally; `pydantic` v2 only at I/O edges | [`foundations.md`](./foundations.md#5-project-structure) |
| Project layout | One PyPI distribution `novetest`, single import root, sub-product submodules, adapter registry | [`foundations.md`](./foundations.md#5-project-structure) |
| Self-testing | pytest with `tmp_path`-scoped `NOVETEST_HOME`; OS x Python matrix in CI | [`foundations.md`](./foundations.md#6-self-testing) |
| Distribution | Tier-1 one-line install script (`curl -fsSL ... \| sh`) that fetches the right PyApp single binary - no system Python or any other toolchain required. Tier-2 direct binary download / Homebrew tap. Tier-3 `uv tool install` / `pipx install` for Python users. **Binding philosophy: easiest possible immediate install + immediate usability.** | [`foundations.md`](./foundations.md#7-distribution) |
| Native engine support set | Python+pytest, JS/TS+jest, Java+JUnit5 (Surefire/Gradle), Go+`go test`, Rust+`cargo test`/`cargo-nextest`, .NET+`dotnet test` over xUnit | [`engine-adapters.md`](./engine-adapters.md) |
| Per-test coverage tiering | First-class for Python (coverage.py contexts) and .NET (Coverlet PerTestCoverage); aggregate-by-default with opt-in slow per-test mode for Java / Jest / Go / Rust | [`engine-adapters.md`](./engine-adapters.md#cross-cutting-per-test-coverage-attribution) |
| SBFL formula default | Ochiai; compute Op2, DStar(\*=2), Tarantula in parallel and persist all four | [`localization-strategy.md`](./localization-strategy.md#1-formula-choice) |
| Localization granularity | Symbol-level primary, line-level retained as evidence; `max(score)` aggregation up | [`localization-strategy.md`](./localization-strategy.md#3-code-location-granularity) |
| Localization fallback when no per-test coverage | Tier the output by `mode`: `sbfl_per_test` -> `sbfl_aggregate` -> `failure_proximity` (regression-aware reweighting in the middle tier) | [`localization-strategy.md`](./localization-strategy.md#2-degradation-when-per-test-coverage-is-unavailable) |
| Recommendation synthesis | Pure rule-based, deterministic, template-driven; no LLM in the synthesis path | [`recommendation-synthesis.md`](./recommendation-synthesis.md#1-deterministic-rule-based-synthesis) |
| Delivery phasing | Six phases mirror `archive/implementation-plan.md`: Run+Memory -> Coverage -> Regression -> Localization -> Replay -> Recommendation Synthesis | [`delivery-phasing.md`](./delivery-phasing.md) |

---

## How to Use These Docs

1. **Building a sub-product?** Read the relevant interface contract under `design/interace-contract/`, then read the matching workflow in `design/workflows/`, then this plan's [`foundations.md`](./foundations.md) for cross-cutting infrastructure decisions, then the focused doc for that sub-product (engine adapters / localization / recommendation).
2. **Picking up an open question?** Open questions are tagged in [`delivery-phasing.md`](./delivery-phasing.md#open-questions). Each is paired with the doc it would update once resolved.
3. **Deviating from a decision here?** Update this index's snapshot table and the corresponding doc in the same change. Do not let drift accumulate silently.

---

## Provenance

These decisions were drafted by synthesizing three expert reviews commissioned for this plan:
- a CLI test-engine integration review covering the six native ecosystems (run/discovery/coverage/per-test attribution),
- an implementation-foundations review (language, CLI framework, subprocess, persistence, structure, self-testing, distribution),
- an SBFL and recommendation-synthesis review citing the published localization literature.

Where the experts noted uncertainty (e.g. nightly-only flags in `cargo test`, drift in Coverlet `PerTestCoverage` config keys), this plan flags it as an open question in [`delivery-phasing.md`](./delivery-phasing.md#open-questions) rather than papering over it.
