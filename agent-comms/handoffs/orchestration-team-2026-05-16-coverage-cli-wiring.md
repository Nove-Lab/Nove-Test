---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-16
slug: coverage-cli-wiring
related:
  - tasks/orchestration-team-2026-05-16-coverage-cli-wiring.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Handoff: `novetest run --coverage` wired end-to-end

## Worktree

- Path: `/home/yjshin/dev/novetest-coverage-cli-wiring`
- Branch: `worktree-coverage-cli-wiring`
- Base commit: `1c22e29` (main)

## Files written / modified

Modified:
- `src/novetest/cli/app.py` — `run_cmd` gains `coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False`; threads through to `run_target_in_store(..., collect_coverage=coverage)`; new `_coverage_outcome_payload` projects `CoverageFactSet | CoverageUnavailable` onto the envelope `data.coverage_outcome` shape (omitted when `--coverage` was not passed). New imports: `Annotated`, `Parameter`, `CoverageUnavailable`, `CoverageFactSet`.
- `src/novetest/orchestration/workflows/run.py` — `run_target_in_store` gains `collect_coverage: bool = False`; on success calls `derive_coverage_facts(store, persisted_record.run_reference)` and re-reads the Memory Entry via `retrieve_run_evidence` so `has_coverage_facts` reflects the freshly written facts file. `RunOutcome` gains an optional `coverage_outcome` field. Module docstring updated.
- `src/novetest/run/engine.py` — Option A charter-cross: `execute` and `execute_with_engine_context` both gain `collect_coverage: bool = False` kwarg, pass-through to `run_pytest(collect_coverage=...)`. Defaults False so all existing callers are byte-equivalent. Docstring on `execute` notes the new kwarg.
- `tests/integration/orchestration/conftest.py` — new `coverage_workspace` fixture (materializes `tests/fixtures/projects/pytest-coverage/`).
- `tests/integration/orchestration/test_workflows.py` — new `test_run_with_coverage_against_pytest_coverage_fixture`.
- `tests/integration/orchestration/test_cli_lifecycle.py` — new `test_run_with_coverage_flag_populates_envelope` (subprocess E2E).
- `tests/unit/run/test_engine.py` — new `test_execute_threads_collect_coverage_kwarg_into_adapter` (stubs `run_pytest` at the engine seam).

Created:
- `tests/unit/orchestration/__init__.py`, `tests/unit/orchestration/workflows/__init__.py`, `tests/unit/orchestration/recommendation/__init__.py` (test packages).
- `tests/unit/orchestration/workflows/test_run.py` — 3 cases for `run_target_in_store` coverage wiring.
- `tests/unit/cli/test_run_cmd.py` — 3 cases for envelope projection.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **267 passed** (258 baseline + 9 new), 1 syrupy snapshot.
- `uv run mypy` → **clean** (49 source files, `--strict`).
- Manual smoke (tmp copy of `tests/fixtures/projects/pytest-coverage/`):
  - `init` → engine readiness ready.
  - `run --coverage tests/` → exit 0, `data.coverage_outcome.kind == "fact-set"`, `mapping_granularity: "per-test"`, `summary.percent_covered: 86.67`.
  - `.novetest/coverage/facts/run_<id>/coverage_facts.json` lands at the contract-frozen path.
  - Subsequent `memory show <run_id>` reports `has_coverage_facts: true`.

## Worklog entry text

```
## 2026-05-16 — phase2 / coverage-cli-wiring

- Landed: `novetest run` learns `--coverage` / `-c`. CLI handler (`src/novetest/cli/app.py::run_cmd`) gains `coverage: Annotated[bool, Parameter(name=["--coverage", "-c"])] = False`, threads it into `run_target_in_store(..., collect_coverage=coverage)`, and projects the returned `CoverageFactSet | CoverageUnavailable | None` onto the envelope under `data.coverage_outcome` via a new `_coverage_outcome_payload` helper: `{kind: "fact-set", run_reference, mapping_granularity, summary}` on success and `{kind: "unavailable", run_reference, reason, detail}` on REQ-COV-004 outcomes. When `--coverage` was NOT passed, the key is omitted entirely (not `null`) so Phase 1 envelopes stay byte-equivalent for non-coverage runs. Orchestration (`src/novetest/orchestration/workflows/run.py`) grows `collect_coverage: bool = False` on `run_target_in_store`; on success it calls `coverage/derive_coverage_facts(store, persisted_record.run_reference)` and re-reads the Memory Entry via `retrieve_run_evidence` so the returned `RunOutcome.memory_entry.has_coverage_facts` reflects the just-written `coverage_facts.json`. `RunOutcome` gains an optional `coverage_outcome: CoverageFactSet | CoverageUnavailable | None = None` field. Run (`src/novetest/run/engine.py`) gets a narrow charter-cross touch authorized as Option A in the task: `execute` and `execute_with_engine_context` both gain `collect_coverage: bool = False` kwarg, pass-through to the already-extant `run_pytest(collect_coverage=...)`. Tests: `tests/unit/run/test_engine.py` gains `test_execute_threads_collect_coverage_kwarg_into_adapter` (stubs `run_pytest` at the engine seam to observe the kwarg without spawning pytest); new `tests/unit/orchestration/workflows/test_run.py` (3 cases — default omits derive, `--coverage` calls derive with the persisted RunReference, `CoverageUnavailable` forwards correctly); new `tests/unit/cli/test_run_cmd.py` (3 cases — envelope key omitted by default, `fact-set` shape, `unavailable` shape — uses capsys + monkeypatched workflow + force-JSON-mode); `tests/integration/orchestration/conftest.py` gains a `coverage_workspace` materializer; `tests/integration/orchestration/test_workflows.py` gains `test_run_with_coverage_against_pytest_coverage_fixture` (asserts `outcome.memory_entry.has_coverage_facts is True`, `coverage_facts.json` at the contract-frozen path, `get_coverage_facts` cache-read returns the same per-test set, and the fixture's deliberately uncovered line 16 of `pytest_coverage/classifier.py` lives in `missing_lines`); `tests/integration/orchestration/test_cli_lifecycle.py` gains `test_run_with_coverage_flag_populates_envelope` (subprocess E2E: `novetest run --coverage tests/` → exit 0, envelope's `data.coverage_outcome.kind == "fact-set"`, `mapping_granularity == "per-test"`).
- Verified: `uv run pytest -q tests/unit tests/integration` → 267 passed (258 baseline + 9 new); `uv run mypy` → clean (49 source files, `--strict`). Manual smoke against a tmp copy of `tests/fixtures/projects/pytest-coverage/` (`uv run --with /home/yjshin/dev/novetest-coverage-cli-wiring --with pytest-json-report --with pytest-cov --with 'coverage[toml]' novetest …`): `init` → engine_readiness ready; `run --coverage tests/` → exit 0, `data.coverage_outcome.kind == "fact-set"`, `mapping_granularity: "per-test"`, `summary.percent_covered: 86.67`; `.novetest/coverage/facts/run_<id>/coverage_facts.json` lands on disk at the contract-frozen path; subsequent `memory show <run_id>` reports `has_coverage_facts: true`.
- Left open: Phase 2 DoD bullet #1 wording in `delivery-phasing.md` mentions `novetest test --coverage`, but this slice only wires `novetest run --coverage` — the `test` verb remains a stub. PM decides during cycle cleanup whether to (a) tick with a wording adjustment to "run --coverage" or (b) wait for a follow-up slice that promotes `test` from stub to a real handler. DoD #2 (`coverage diff` verb), #3 (`inspect` Coverage section), #4 (NFR-COV-002 50k-location perf) explicitly out of scope — separate slices. The orchestration workflow's post-derive `retrieve_run_evidence` re-read is a small extra read; could be optimized to filesystem-stat the `coverage_facts.json` path if it ever shows up in a profile, but at Phase 2 reading one `record.json` is negligible.
- Gotcha: `Annotated[bool, Parameter(name=["--coverage", "-c"])]` is the right Cyclopts 4.11 way to add an alias; using `alias="-c"` on the Parameter constructor also works but the `name=[...]` form is what shows up in the help surface as a single canonical group. The manual smoke needs `--with pytest-json-report --with pytest-cov --with 'coverage[toml]'` because `uv run --with novetest` only pulls runtime deps — the dev deps that the adapter assumes are NOT in the SuT's venv when novetest is consumed as a wheel. Inside CI / `uv run pytest` this is invisible because the dev venv has all three; the only place this matters is hand-run smoke commands. Pytest fixture isolation: the per-test stubbed `run_target_in_store` in `tests/unit/cli/test_run_cmd.py` uses `capsys` instead of monkeypatching `sys.stdout` to a `StringIO` because pytest's own capture mechanism already redirects stdout, and a second monkeypatch on top of it silently fights with pytest's restore logic — first attempt failed with empty buffers despite the envelope clearly being emitted (it landed in pytest's own capture target).
- Next: Phase 2 DoD #2 — `novetest coverage show <run_id>` / `coverage diff <id1> <id2>` CLI verbs. The handler can lean on `coverage.get_coverage_facts` / `coverage.compare_coverage_facts` directly; envelope projection mirrors the `coverage_outcome` shape introduced here. Then DoD #3 — `novetest inspect <run_id>` Coverage section (composes Memory + Coverage + Regression + Localization + Replay). DoD #4 (50k-location perf) needs a perf-fixture proposal first; PM is expected to recruit `performance-engineer` for the scoping.
```

## DoD bullets believed closed

- **Phase 2, bullet #1** — "`novetest test --coverage` against `pytest-coverage` emits per-test coverage with `mapping_granularity: per-test`."

  Caveat per task spec: this slice only wires `novetest run --coverage`; `novetest test` remains a stub. The fact-set produced and persisted matches DoD #1 exactly (per-test granularity against the named fixture). PM decides whether to (a) tick this with a `delivery-phasing.md` wording adjustment ("run --coverage") or (b) leave unticked pending a follow-up slice that promotes `test` to a real handler. Not my call.

NOT claimed: DoD #2 (`coverage diff` verb), DoD #3 (`inspect` Coverage section), DoD #4 (50k-location perf).

## Envelope-schema implications

- `novetest run` JSON envelope grows an optional `data.coverage_outcome` block, present ONLY when `--coverage` is passed. The block is discriminated by `kind: "fact-set" | "unavailable"`:
  - `fact-set` carries `{run_reference, mapping_granularity, summary}` — the summary mirrors `CoverageSummary.to_dict()`.
  - `unavailable` carries `{run_reference, reason, detail}` — `reason` is one of the known REASON_* constants from `coverage/results.py`.
- The `schema: novetest/v1` envelope version is **unchanged** — this is an additive extension to `data` on the `run` command and does not affect any other command's wire shape. No `decisions/` entry needed.
- Non-coverage runs are byte-equivalent to Phase 1: the `coverage_outcome` key is omitted entirely (not emitted as `null`).

## Open items / surprises

- **Option A cross-charter touch.** `src/novetest/run/engine.py` belongs to Run team's charter, not mine; the task explicitly authorized Option A (the narrow signature extension to add `collect_coverage` to `execute` / `execute_with_engine_context`). I treated it as authorized and added one unit test on the Run side to lock the wiring. PM owns the charter coordination with Run team if it matters; from the code-shape side this is a pure pass-through of an already-existing kwarg one layer up.
- **`novetest test` still a stub.** The DoD text mentions the integrated verb, but my slice deliberately wired only `novetest run --coverage`. Promoting `test` from stub to a real handler is a separate follow-up slice (recommendation synthesis + `test` → `run --coverage` wiring sized together per the task spec).
- **Smoke command dependencies.** The manual smoke requires `--with pytest-json-report --with pytest-cov --with 'coverage[toml]'` on top of `--with novetest` when `uv run`-ing the CLI against a SuT venv that doesn't already have novetest's dev deps. Inside CI and `uv run pytest` this is invisible because the dev venv has all three. Worth a note in any user-facing install/getting-started doc when one gets written.
- **Workflow post-derive re-read.** After `derive_coverage_facts`, I re-read the Memory Entry via `retrieve_run_evidence` so `has_coverage_facts` reflects the just-written file. That's one extra `record.json` parse; negligible at Phase 2 but worth flagging if the orchestration workflow ever shows up in a profile.
- **No `pyproject.toml` touch.** Confirmed no new deps needed — `pytest-cov` and `coverage[toml]` were already landed by Run team's slice.
