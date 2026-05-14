# Implementation Plan - Delivery Phasing

**Scope:** The phased build sequence for Nove Test. Each phase has a goal, a definition-of-done, the interfaces and workflows in scope, the engine adapter coverage, and exit criteria. Plus risks and open questions.

**Upstream**

- Foundations: `[foundations.md](./foundations.md)`
- Engine adapters: `[engine-adapters.md](./engine-adapters.md)`
- Localization strategy: `[localization-strategy.md](./localization-strategy.md)`
- Recommendation synthesis: `[recommendation-synthesis.md](./recommendation-synthesis.md)`
- Original phase plan: `[design/archive/implementation-plan.md](../archive/implementation-plan.md)`
- Roadmap: `[design/product-plans/overall-plan.md](../product-plans/overall-plan.md)`

The phase boundaries follow the original 6-phase roadmap. This doc converts each into a concrete build order with measurable exit criteria.

---

## Phase 0 - Foundations

**Goal:** make the repo buildable, runnable, releasable, and CI-green before any sub-product code lands.

**In scope:**

- Project skeleton matching `[foundations.md](./foundations.md#5-project-structure)`.
- `pyproject.toml` with `python_requires = ">=3.11"`, `uv` for dev workflow.
- `cli/app.py` with Cyclopts root and empty subapp wiring (placeholders for `test`, `run`, `memory`, `coverage`, `regression`, `localization`, `replay`, `inspect`, `compare`, `status`).
- JSON envelope (`cli/output.py`) and exit code constants.
- `utils/asyncio_subprocess.py` canonical invocation helper.
- `memory/store.py` file-only Project Store façade (path resolution + `record.json` read/write helpers). No index database in Phase 0-4 per `[foundations.md` §4](./foundations.md#4-persistence).
- `models/` core entities (`run_reference.py`, `run_record.py`, `test_result.py`, `memory_entry.py`).
- CI matrix: Linux/macOS/Windows x Python 3.11/3.12/3.13, `minimal` lane (no native engines required).
- **Onboarding bindings** (from `[design/interace-contract/orchestration.md](../interace-contract/orchestration.md)` §1):
  - `orchestration/onboarding/identity.py` (`report_cli_identity`) and `orchestration/onboarding/command_surface.py` (`describe_command_surface`).
  - `cli/app.py` dispatches `-v` / `--version` and `-h` / `--help` through these before any Project Store lookup runs.
  - Snapshot tests for `novetest --version` and `novetest --help` JSON envelopes via `syrupy`, asserting the envelope is callable on a clean machine with no `.novetest/` present anywhere.
- PyApp release pipeline that produces a binary on tag push but does not yet publish to PyPI.
- **One-line install script (`scripts/install.sh`) for Linux/macOS** (`linux-x86_64`, `linux-aarch64`, `macos-arm64`, `macos-x86_64`) per the Tier-1 path in `[foundations.md](./foundations.md#7-distribution)`. Detects OS+arch, downloads the matching PyApp binary, verifies SHA-256, installs to `~/.local/bin/novetest`, prints `PATH` hint if needed, idempotent on re-run.
- GitHub Releases workflow uploads a `*.sha256` sidecar alongside every binary so the install script can verify.
- Install script hosting (specific URL TBD - see Open Question #15). Until the final URL is wired up, the script is reachable from `https://raw.githubusercontent.com/...` for `release-test` validation.

**Definition-of-done:**

- [ ] `uv run pytest -q` green on all three OSes and three Python versions.
- [x] `novetest --output json --help` returns the standard envelope.
- [x] A no-op `novetest test --help` exits 0; the rest of the subcommands exist as stubs that exit 2 with a "not yet implemented" envelope.
- [ ] A signed binary builds on the `release-test` workflow.
- [ ] `**curl -fsSL <release_install_url> | sh` end-to-end** produces a working `novetest --version` on a clean Linux container and a clean macOS runner. Re-running the same command upgrades in place.
- [ ] The install script verifies SHA-256 and aborts loudly on mismatch; this is covered by an integration test that intentionally serves a tampered binary.
- [x] `novetest -v` and `novetest -h` return their structured envelopes in a directory tree that contains no `.novetest/` anywhere in the ancestor chain. This is the Phase 0 onboarding-readiness gate.

**Risks / mitigations:**

- *Cyclopts immaturity surfaces during Phase 0* - if blocked, swap to Click. Phase 0 is the cheapest time to make this swap; the command tree shape is identical.
- *PyApp + python-build-standalone availability for `windows-arm64`* - currently unsupported; we ship `windows-x86_64` only and document the gap.

---

## Phase 1 - Onboarding + Run + Memory Foundation

**Goal:** the minimum repeatable testing loop, entered through the documented onboarding flow. A user installs Nove Test (Phase 0), runs `novetest init` in their project, gets a `.novetest/` Project Store, sees a clear engine-readiness signal, then executes a test through one native engine and inspects / lists / deletes the result.

**Interfaces in scope** (from `[design/interace-contract/orchestration.md](../interace-contract/orchestration.md)`, `[run.md](../interace-contract/run.md)`, `[memory.md](../interace-contract/memory.md)`):

- **Onboarding (orchestration §1):**
  - `novetest init` (External) and `orchestration/initialize_project_workspace` (Internal).
- **Project Store (memory §1):**
  - `memory/create_project_store`, `memory/locate_project_store`, `memory/get_project_store_state`.
- **Engine readiness (run):**
  - `run/assess_engine_readiness`, `run/detect_engine_candidates`.
- **Run + Memory operating set:**
  - `novetest run [target]`
  - `run/execute`, `run/resolve_test_target`, `run/select_native_engine`, `run/normalize_native_result`, `run/assign_run_reference`, `run/list_supported_engine_pairs`
  - `novetest memory list`, `novetest memory show <run_id>`, `novetest memory delete <run_id>`
  - `memory/store_run_evidence`, `memory/retrieve_run_evidence`, `memory/list_run_history`, `memory/delete_run_evidence`, `memory/get_memory_entry_availability`
- **Stub fact surface:**
  - `novetest inspect <run_id>` (without coverage/regression/localization/replay - those return `null` in the aggregated view)
  - `novetest status` and `orchestration/build_status_view` (with all sub-report flags returning `unavailable`)

**Engine adapter coverage:** **pytest only.** Other ecosystems contribute only their `detect()` hooks so `assess_engine_readiness` can identify them in the workspace; their full adapters are stubs that report "not yet implemented" when invoked for execution. This intentional narrowness lets us validate the whole onboarding -> Run -> Memory -> Inspect loop end-to-end before fanning out.

**Persistence:** per-project `.novetest/` Project Store layout from `[foundations.md` §4](./foundations.md#4-persistence) finalized; `store.json` and the engine-subdirectory skeleton written by `create_project_store`. Run Records persist as `memory/runs/YYYY/MM/DD/run_<ulid>/record.json` (date path derived from the ULID timestamp prefix). Tombstone is a POSIX-atomic `rename(2)` from `memory/runs/...` to `memory/tombstones/...`; tombstoned runs remain readable to `inspect`. No index database in this phase.

**Fixture projects:** `tests/fixtures/projects/pytest-basic/`, `pytest-failing/` (the latter exercising failed-test capture), and `empty-no-engine/` (a project workspace with no detectable native engine, used to validate `engine-missing` readiness output and the corresponding init-then-no-run guidance).

**Definition-of-done:**

- [x] `novetest init` in a fresh project root creates `.novetest/` with the engine-subdirectory skeleton (`memory/runs/`, `memory/tombstones/`, `run/`, `coverage/`, `regression/`, `localization/`, `replay/`, `orchestration/`, plus `blobs/` and `store.json`). No index database is created.
- [x] Re-running `novetest init` is idempotent: existing `store.json`, run records, and tombstones are preserved (REQ-MEM-006 verified by a fixture that pre-creates evidence and re-runs init).
- [x] `novetest init` against `empty-no-engine/` returns `storeState: ready` plus `engine_readiness: engine-missing` in the envelope; the store is still created (readiness is informational), and no native engine is installed or downloaded as a side effect.
- [x] `novetest run tests/test_x.py` against `pytest-basic/` produces a Run Record stored under `.novetest/memory/runs/.../record.json` with a stable Run Reference and corresponding native artifacts under `.novetest/run/artifacts/.../`.
- [x] `novetest run` from `empty-no-engine/` returns `engine-missing` (exit code 4) before any subprocess is spawned, with the envelope distinguishing readiness failure from internal Nove Test failure (NFR-RUN-004).
- [x] `novetest memory list --output json` returns the run.
- [x] `novetest memory show <run_id> --output json` returns the run plus availability flags (all derived facts `false`).
- [x] `novetest memory delete <run_id>` tombstones; subsequent `memory show` still resolves (tombstoned).
- [x] `novetest status --output json` returns latest Run Reference and Run History readiness; all sub-reports `unavailable`.
- [ ] `novetest test tests/test_x.py` runs the integrated workflow but with empty Coverage / Regression / Localization / Replay; recommendation is `all_green` or `unavailable_analysis`.
- [x] Operating commands invoked from a directory tree with no ancestor `.novetest/` return a structured `uninitialized` envelope pointing at `novetest init` (no traceback, exit code 2).
- [x] All workflow sequences documented in `[design/workflows/orchestration.md](../workflows/orchestration.md)` §1, `[run.md](../workflows/run.md)`, and `[memory.md](../workflows/memory.md)` (Sections 1 and 2) are exercised by integration tests.

**Risks:**

- *pytest-json-report version skew on Windows* - pin a minimum minor.
- *Path normalization edge cases* in nodeids - centralize path normalization in `utils/paths.py`.
- *Project Store discovery surprises* - walking up from CWD can cross workspace boundaries on shared dev machines (multiple projects under one ancestor). Phase 1 stops at the first `.novetest/`; document the behavior and add a `--store=<path>` override for users who need to disambiguate.

---

## Phase 2 - Coverage Structuring

**Goal:** structured Coverage Facts and cross-run Coverage deltas.

**Interfaces in scope:**

- `novetest coverage show <run_id>`, `novetest coverage diff <run_id1> <run_id2>`
- `coverage/derive_coverage_facts`, `coverage/get_coverage_facts`, `coverage/compare_coverage_facts`, `coverage/check_coverage_availability`
- `novetest inspect <run_id>` extends to populate Coverage section (not just availability flag).

**Engine adapter coverage:** pytest (per-test via coverage.py contexts) plus the **first three of the remaining five** in priority order driven by user demand and adapter complexity. Recommended Phase 2 set: pytest + jest + go test. JUnit and dotnet land in Phase 2.5 (a same-phase extension); cargo lands in Phase 3 unless a user blocker surfaces.

**Schema additions:** `coverage_facts.json` written under `.novetest/coverage/facts/run_<ulid>/`, with `mapping_granularity` populated and `schema_version: 1`. No SQLite in this phase — Coverage Facts are read by loading the per-run JSON, which is sufficient for all Phase 2/3 query patterns (`coverage show`, `coverage diff`, `inspect`).

**Per-test attribution tiers:** as defined in `[engine-adapters.md](./engine-adapters.md#cross-cutting-per-test-coverage-attribution)`.

**Fixture projects:** `pytest-coverage/` (per-test), `jest-basic-coverage/` (per-file degraded), `gotest-basic-coverage/` (aggregate).

**Definition-of-done:**

- [ ] `novetest test --coverage` against pytest-coverage emits per-test coverage with `mapping_granularity: per-test`.
- [ ] `novetest coverage diff` returns structured deltas with stable Code Location identity.
- [ ] `inspect` returns the Coverage section populated.
- [ ] Performance NFR-COV-002 met on a fixture with 50k covered locations.

**Risks:**

- *Test-to-code mapping degradation surprises*. Document the per-mapping-granularity behavior loudly in the CLI text + JSON `warnings`.

---

## Phase 3 - Regression Comparison

**Goal:** factual run-to-run behavior change reports.

**Interfaces in scope:**

- `novetest regression compare <run_id1> <run_id2>`, `novetest regression latest`
- `regression/compare_runs`, `regression/resolve_latest_baseline`, `regression/derive_latest_regression`, `regression/get_regression_facts`, `regression/check_regression_availability`
- `novetest compare <run_id1> <run_id2>` (orchestration-level Regression + Coverage diff composition)
- `inspect` extends to populate Regression section.

**Engine adapter coverage:** all six landed by end of Phase 3. Cargo and JUnit/dotnet adapters from Phase 2.5/3 finalize here.

**Schema additions:** Regression Fact tables; `regression_facts.json` per run pair.

**Definition-of-done:**

- [ ] `novetest regression latest` resolves the latest pair for the resolved Test Target and returns Regression Facts (with Coverage changes when available).
- [ ] `novetest compare` returns the composed Regression + Coverage delta.
- [ ] `inspect` populates Regression section using the resolved baseline.

**Risks:**

- *Baseline resolution ambiguity* when multiple recent runs share a target. Default policy: latest two by `created_at`; document and parameterize via `--since` / `--baseline=<run_id>` overrides.

---

## Phase 4 - Localization

**Goal:** ranked suspicious Code Locations with mode-aware degradation.

**Interfaces in scope:**

- `novetest localization <run_id>`, `novetest localization latest`
- `localization/derive_localization_findings`, `localization/resolve_latest_analyzable_run`, `localization/derive_latest_localization`, `localization/get_localization_findings`, `localization/check_localization_availability`
- `inspect` extends to populate Localization section.

**Implementation:**

- All four SBFL formulas (Ochiai default, Op2, DStar(=2), Tarantula) under `localization/sbfl/`.
- Three modes (`sbfl_per_test`, `sbfl_aggregate`, `failure_proximity`) with mode-selection algorithm from `[localization-strategy.md](./localization-strategy.md#2-degradation-when-per-test-coverage-is-unavailable)`.
- Symbol resolver: Python (`ast`) ready; JS/TS, Java/Kotlin, Go, Rust, C# ship with file-level fallback to be upgraded post-MVP.

**Fixture projects:** `localization-branch/` (a deliberate single-line bug with rich coverage), `localization-aggregate-only/` (no per-test coverage), `localization-no-coverage/` (failure-proximity mode).

**Definition-of-done:**

- [ ] `novetest localization latest --output json` against `localization-branch` ranks the bug in top 3.
- [ ] Mode field populated correctly across all three fixtures.
- [ ] Performance NFR-LOC-002 met (500 failed tests + 50k covered locations within 8s).
- [ ] All four formulas computed and persisted; `--formula` flag selects which is presented as primary.

**Risks:**

- *Spectra matrix size on very large suites*. Validate at Phase 4 against the largest available fixture; introduce sparse representation if needed.
- *Symbol resolver coverage* - file-level fallback is acceptable for ecosystems where the resolver is not yet ready; document loudly.

---

## Phase 5 - Replay Validation

**Goal:** classify reproducibility via Replay Result.

**Interfaces in scope:**

- `novetest replay <run_id>`
- `replay/replay_run`, `replay/reconstruct_replay_context`, `replay/classify_replay_consistency`, `replay/get_replay_result`, `replay/check_replay_availability`
- `run/execute_with_engine_context` (used by Replay; finalized here even though contract was earlier).
- `inspect` extends to populate Replay section.

**Implementation:**

- Replay reuses `run/execute_with_engine_context` to keep the same Native Engine path as the original run.
- Multiple-run replay support (e.g. `--reruns=5`) for flake detection.
- Replay Result classification: `reproducible` / `inconsistent` / `unable_to_replay`.

**Persistence — first introduction of the derived SQLite cache:** Phase 5 is the first sub-product whose hot path is a per-test cross-run query (flakiness ratio over recent runs of a given nodeid). File-scan cost over Run History becomes prohibitive at this scale. Phase 5 introduces a derived SQLite index at `.novetest/memory/index.db` that caches `run` and `test_outcome` rows built from existing `record.json` files. The DB is a cache, not the source of truth; deleting it is always safe and a `novetest reindex` command rebuilds it from scratch. Schema is designed against the actual Phase 5 query set (per-nodeid history, latest-N joins), stamped with its own `index_schema_version = 1`. Forward-only `memory/migrations/` is created here. Settings and rationale are in `[foundations.md` §4 "Phase 5 SQLite cache"](./foundations.md#4-persistence).

**Fixture projects:** `flaky-python/` (deliberately non-deterministic test), `pytest-basic/` (reproducible).

**Definition-of-done:**

- [ ] `novetest replay <run_id_of_flaky>` with `--reruns=5` produces `inconsistent` classification.
- [ ] `novetest replay <run_id_of_basic>` produces `reproducible`.
- [ ] A run whose target no longer exists produces `unable_to_replay`.

**Risks:**

- *Environment drift between original and replay* (dependency versions, time-sensitive tests). Document explicitly that "reproducible" is "reproducible under reconstructed conditions" not "reproducible against arbitrary future state."

---

## Phase 6 - Recommendation Synthesis

**Goal:** the integrated `novetest test [target]` returns deterministic, cited recommendations.

**Interfaces in scope:**

- `orchestration/synthesize_recommendation`, `orchestration/cite_recommendation_evidence`, `orchestration/evaluate_stage_eligibility`
- The integrated `novetest test [target]` workflow as defined in `[design/workflows/orchestration.md](../workflows/orchestration.md)`.
- All seven recommendation categories from `[recommendation-synthesis.md](./recommendation-synthesis.md#2-recommendation-categories)`.

**Implementation:**

- Pure rule-based synthesis under `orchestration/recommendation/`.
- Closed taxonomy frozen at v1 of `recommendation_schema_version`.
- Golden-fixture snapshot tests pinning the recommendation output for each fixture project.

**Definition-of-done:**

- [ ] `novetest test tests/` against each fixture produces the expected category set per fixture, byte-identical across runs.
- [ ] Snapshots pinned with `syrupy`.
- [ ] Integration test demonstrates an AI agent can traverse `recommendation -> evidence_citations -> retrieve_run_evidence` round-trip end-to-end.
- [ ] **Default-verb alias activated.** `novetest <target>` resolves to `novetest test <target>` per the note in `[design/interace-contract/orchestration.md](../interace-contract/orchestration.md)` §"Notes" (Default verb). Bare `novetest` (no arguments) continues to print the structured help envelope and does **not** trigger an implicit run. Integration test asserts: (1) `novetest tests/test_x.py` is byte-equivalent in its envelope to `novetest test tests/test_x.py`; (2) `novetest` alone still returns the help envelope and exit 0; (3) `novetest run` remains reachable as the explicit raw-evidence path.

**Risks:**

- *Closed taxonomy gets restrictive*. v2 is a deliberate bump; `recommendation_schema_version` is the contract.
- *Default-verb alias is ambiguous when the first positional looks like a verb token.* Concrete failure shape: a user creates `tests/inspect/` and runs `novetest inspect` — does the CLI treat `inspect` as the existing verb or as a Test Target? Mitigation: reserve the known verb tokens (Section 2 Operating verbs + Section 1 `init`) as non-alias-eligible; route `novetest <token>` to the verb handler whenever `<token>` is in that reserved set, regardless of whether a same-named path exists. Document this disambiguation rule next to the alias.

---

## Phase 7 (post-MVP) - MCP Transport

Not part of the original 6-phase roadmap but called out in `[foundations.md](./foundations.md#5-project-structure)` as a structural concern from day one.

**Goal:** the same domain operations are available via the Model Context Protocol so AI agents that prefer MCP do not have to shell out.

**Implementation:**

- `novetest/mcp/server.py` with `mcp` Python SDK (FastMCP-style decorators).
- `novetest-mcp` console script entry point.
- All `novetest` operations exposed as MCP tools: `test`, `inspect`, `compare`, `status`, `replay`, `localize`, `regression-compare`, `regression-latest`, `coverage-show`, `coverage-diff`, `memory-list`, `memory-show`, `memory-delete`.
- Same internal modules as the CLI; MCP is a transport, not a parallel implementation.

**Definition-of-done:**

- [ ] An MCP-aware agent can invoke each tool and consume the JSON envelope identical to what the CLI emits.
- [ ] Snapshot tests cover at least one MCP tool round-trip per sub-product.

---

## Open Questions

These are tracked across phases; resolving any of them updates the relevant doc.


| #   | Question                                                                                             | Phase               | Updates                                                                |
| --- | ---------------------------------------------------------------------------------------------------- | ------------------- | ---------------------------------------------------------------------- |
| 1   | Should Run Reference uniqueness be scoped per workspace, per machine, or globally?                   | Phase 1             | `foundations.md` persistence section, domain-model open questions      |
| 2   | Branch / symbol resolution as a Code Location kind across all six ecosystems                         | Phase 4             | `localization-strategy.md` Open Items                                  |
| 3   | `cargo nextest libtest-json` graduation off nightly                                                  | Phase 2.5 / Phase 3 | `engine-adapters.md` Rust section                                      |
| 4   | Coverlet `PerTestCoverage` exact configuration key in the version we pin                             | Phase 2.5           | `engine-adapters.md` .NET section                                      |
| 5   | JUnit Platform Console Launcher: vendor vs download-on-first-use                                     | Phase 2.5           | `engine-adapters.md` Java section                                      |
| 6   | Memory Entry deletion - tombstone retention period and `vacuum` semantics                            | Phase 1             | `foundations.md` persistence section                                   |
| 7   | Vitest as alternate JS/TS adapter                                                                    | Phase 2+            | `engine-adapters.md` JS/TS section                                     |
| 8   | Static enumeration of individual Jest `it()` blocks via TS/JS AST parser                             | Phase 2+            | `engine-adapters.md` JS/TS Discovery                                   |
| 9   | Recommendation persistence per run vs re-derive on `inspect`                                         | Phase 6             | `recommendation-synthesis.md` Implementation Notes                     |
| 10  | `recommendation_schema_version` v1 freeze - exact slot keys per category                             | Phase 6 entry       | `recommendation-synthesis.md`                                          |
| 11  | Spectra matrix size limits / sparse representation threshold                                         | Phase 4             | `localization-strategy.md` Open Items                                  |
| 12  | Per-language symbol resolvers landing order post-MVP                                                 | Post-Phase 4        | `localization-strategy.md`                                             |
| 13  | Homebrew tap publishing                                                                              | Post-MVP            | `foundations.md` distribution                                          |
| 14  | `novetest self update` signing key rotation policy                                                   | Post-MVP            | `foundations.md` distribution                                          |
| 15  | Install script hosting URL (custom domain like `get.novetest.dev` vs GitHub Pages vs raw GitHub)     | Phase 0             | `foundations.md` distribution; install script in `scripts/install.sh`  |
| 16  | Windows `install.ps1` parity (post-Phase-0)                                                          | Post-MVP            | `foundations.md` distribution                                          |
| 17  | Project Store discovery scope: stop-at-first vs walk-to-VCS-root vs disallow nested `.novetest/`     | Phase 1             | `foundations.md` persistence section, `interace-contract/memory.md` §1 |
| 18  | Engine readiness probe caching: per-invocation vs cached under `.novetest/run/readiness/` with a TTL | Phase 1             | `foundations.md` persistence section, `interace-contract/run.md`       |
| 19  | Phase 5 derived SQLite index — schema for `run` + `test_outcome` tables (Phase 5 query set), and rebuild trigger (lazy on first SQL-dependent query vs explicit `novetest reindex` vs both) | Phase 5             | `foundations.md` §4 "Phase 5 SQLite cache"; new `memory/migrations/` introduced at Phase 5 |
| 20  | Marker-file filter index (`memory/by_target/`, `memory/by_engine/`) — adopt eagerly from Phase 1 vs lazily when `find_runs_for_target` perf becomes noticeable | Phase 3             | `foundations.md` §4 persistence section                                |


---

## Cross-Phase Rules (binding throughout)

- Sub-products produce facts; only Orchestration emits Recommendations.
- The Native Engine is the source of truth for discovery, execution, assertion semantics, and native reporting. We never reinvent these.
- Every Recommendation has at least one resolvable Evidence Citation (NFR-ORCH-002).
- Stored data carries `schema_version`; migrations are forward-only.
- All structured outputs are deterministic for the same inputs.
- The CLI's structured output schema (`schema: novetest/v1`) is the contract with AI agents; bumping it is a deliberate, versioned change.
- No LLM in any internal synthesis or fact-derivation path.

---

## Doc Map for Active Work

When picking up a phase:

1. Read the relevant `design/interace-contract/<engine>.md`.
2. Read the matching `design/workflows/<engine>.md`.
3. Read `[foundations.md](./foundations.md)` for cross-cutting infra.
4. Read the focused implementation doc for that phase (`[engine-adapters.md](./engine-adapters.md)`, `[localization-strategy.md](./localization-strategy.md)`, `[recommendation-synthesis.md](./recommendation-synthesis.md)`).
5. Open the matching open-questions row above; close it as the phase progresses.

