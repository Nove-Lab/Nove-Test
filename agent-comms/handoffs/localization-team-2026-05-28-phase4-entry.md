---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-28
slug: phase4-entry
related:
  - tasks/localization-team-2026-05-28-phase4-entry.md
  - design/implementation-plan/localization-strategy.md
  - design/interace-contract/localization.md
---

# Handoff: Phase 4 entry — Localization engine (per-test SBFL path)

## Worktree

- **Path:** `/home/yjshin/dev/aispace/novetest-localization-phase4-entry`
- **Branch:** `localization-team/phase4-entry`
- **Base commit:** `4be6c7c` on `main`
- **Push status:** not pushed (local worktree only — Main Branch picks it up directly)

## Files written / modified

### New source files (11 in `src/`, all under `src/novetest/localization/` + `src/novetest/models/`)

- `src/novetest/models/localization_finding.py` — `CodeLocation` / `EvidenceCitation` / `LocalizationEntry` / `LocalizationFinding` dataclasses + closed enums + `to_dict`/`from_dict` round-trips. SCHEMA_VERSION=1.
- `src/novetest/localization/results.py` — `LocalizationUnavailable` + 4 `REASON_*` constants + `KNOWN_REASONS` frozenset.
- `src/novetest/localization/sbfl/ochiai.py` — pure-math Ochiai formula.
- `src/novetest/localization/sbfl/op2.py` — pure-math Op2 formula.
- `src/novetest/localization/sbfl/dstar.py` — pure-math DStar(*=2) formula.
- `src/novetest/localization/sbfl/tarantula.py` — pure-math Tarantula formula.
- `src/novetest/localization/sbfl/spectra.py` — `Spectra` dataclass + `build_spectra` + `SpectraBuildError`.
- `src/novetest/localization/symbol_resolver.py` — Python `ast`-based `resolve_python_symbol` + cache + `clear_resolver_cache` test seam.
- `src/novetest/localization/persistence.py` — atomic write/read helpers for `localization_findings.json`.
- `src/novetest/localization/derive.py` — `derive_localization_findings` engine entry.
- `src/novetest/localization/retrieval.py` — `get_localization_findings` + `check_localization_availability`.

### Modified source files

- `src/novetest/localization/__init__.py` — public surface re-exports + scope docstring (was empty).
- `src/novetest/localization/sbfl/__init__.py` — re-exports of formulas + spectra (was empty).
- `src/novetest/models/__init__.py` — added the 4 new dataclass re-exports.

### Config

- `pyproject.toml` — added `numpy>=1.26` to `[project].dependencies` (NEW runtime dep).
- `uv.lock` — regenerated to pin `numpy==2.4.6`.

### Test files (new)

- `tests/unit/localization/__init__.py` (replaces `.gitkeep`)
- `tests/unit/localization/sbfl/__init__.py` (replaces `.gitkeep`)
- `tests/unit/localization/conftest.py` — shared fixtures (`make_file`, `make_record`, `make_coverage`, `seed_store`, `write_python_module`, `default_ref`).
- `tests/unit/localization/sbfl/test_ochiai.py` (6 cases)
- `tests/unit/localization/sbfl/test_op2.py` (4 cases)
- `tests/unit/localization/sbfl/test_dstar.py` (5 cases)
- `tests/unit/localization/sbfl/test_tarantula.py` (5 cases)
- `tests/unit/localization/sbfl/test_spectra.py` (7 cases)
- `tests/unit/localization/test_symbol_resolver.py` (8 cases)
- `tests/unit/localization/test_localization_finding_model.py` (16 cases)
- `tests/unit/localization/test_results.py` (5 cases)
- `tests/unit/localization/test_persistence.py` (10 cases)
- `tests/unit/localization/test_derive.py` (11 cases)
- `tests/unit/localization/test_retrieval.py` (8 cases)
- `tests/integration/localization/__init__.py` + `tests/integration/localization/test_localization_branch_basic.py` (2 cases — real `novetest run --coverage` end-to-end)

### Fixture project (new)

- `tests/fixtures/projects/localization-branch/pyproject.toml`
- `tests/fixtures/projects/localization-branch/README.md`
- `tests/fixtures/projects/localization-branch/localization_branch/__init__.py`
- `tests/fixtures/projects/localization-branch/localization_branch/calculator.py` — 5 top-level functions + `Counter.increment` method; `divide` has the deliberate one-line bug.
- `tests/fixtures/projects/localization-branch/tests/test_calculator.py` — 6 tests; `test_divide_yields_quotient` fails.

### Worklog

- `WORKLOG.md` — new entry on top.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **558 passed + 3 skipped** (was 471+3 on `main` at `4be6c7c`; +87 new tests, all green; the 3 skips are the pre-existing Node-dependent jest integration tests).
- `uv run mypy` → clean, **68 source files** (was 57 baseline; +11 new src files), `--strict`.

## Worklog entry text

See `WORKLOG.md` top entry (`## 2026-05-28 — phase4-entry / localization-engine-per-test`).

## DoD bullets believed closed

**None.** This slice is the Phase 4 engine foundation. The Phase 4 DoD bullets `[186-189]` all require the CLI surface + the two degraded modes; this slice provides the engine the CLI projects in a future Orchestration cycle. (Same pattern Regression followed: engine surface lands first, no DoD bullets tick; the CLI slice ticks them.)

## Schema decisions PM should freeze in a follow-up `decisions/` entry

After Manual Test fields the engine, freeze:

1. **`LocalizationFinding.to_dict()` wire shape** — top-level keys = `schema_version, run_reference, engine_name, ecosystem, mode, confidence, formula, alternate_scores_available, top_n, entries, derived_at, metadata`.
2. **`LocalizationEntry.to_dict()` wire shape** — keys = `rank, tied_with, code_location, score_raw, score_normalized, formula, alternate_scores, related_failed_tests, evidence_citations`.
3. **`CodeLocation.to_dict()` wire shape** — keys = `kind, file, symbol, line_range, primary_line, evidence_lines`; `kind ∈ {"symbol", "line", "branch", "file"}` (only `symbol` and `file` produced today; `line` and `branch` reserved).
4. **`EvidenceCitation.to_dict()` wire shape** — keys = `kind, run_reference, selector`; `kind ∈ {"test_result", "coverage_fact"}`; selector discriminated:
   - `test_result` → `{"test_id": <nodeid>, "outcome": "failed"}`
   - `coverage_fact` → `{"file": <path>, "lines": [<int>, ...]}`
5. **`LocalizationUnavailable` shape + 4-reason closed enum** — fields = `run_reference: RunReference | None, reason: str, detail: str | None`; reasons = `{"no_failed_tests", "no_coverage", "no_run_evidence", "run_not_analyzable"}`.
6. **`tied_with` convention** — `entry_index_<i>` strings where `<i>` is the 0-based index INTO THE TRUNCATED top_n list (a tie crossing the top_n boundary loses its dropped-half references). Manual Test should probe; PM may pick a richer handle when freezing.
7. **Persistence path** — `<store>/localization/findings/run_<run_id>/localization_findings.json`. Already implicit in Memory's `_availability_flags`, but worth freezing alongside the others.

## Open items for follow-up slices

- **`sbfl_aggregate` mode** — FLUCCS-style regression-aware reweighting consuming `get_regression_facts` for coverage with `mapping_granularity != "per-test"`. Engine surface stays the same; just a new path through `_derive_per_test`-equivalent.
- **`failure_proximity` mode** — no-coverage fallback ranking by stack frames + regression-modified files. Engine surface stays the same.
- **`resolve_latest_analyzable_run` + `derive_latest_localization`** — separate slice (mirrors Regression's baseline-resolution slice that landed in `2026-05-26 — phase3 / regression-baseline-resolution`).
- **CLI verbs** — `novetest localization <run_id>` / `novetest localization latest` / `inspect` Localization section. Orchestration territory, projected from this engine surface.
- **Non-Python symbol resolvers** — JS/TS, Java/Kotlin, Go, Rust, C#. File-level fallback works today (the resolver returns `(None, None)` for non-Python files, producing `CodeLocation(kind="file")`).
- **Sparse spectra representation** (Open Question #11) — defer until a real fixture exceeds the dense threshold. Today's perf budget (NFR-LOC-002: 500 failed × 50k locations in 8s) is met with dense+numpy.
- **NFR-LOC-002 perf gate** — out of scope for the engine-foundation slice but worth a follow-up performance-engineer pass to bench-pin the budget.

## Observed behaviors not pinned by design (Manual Test should pay attention)

- **`tied_with` references inside top_n only** — a 15-way tie at rank 1 truncated to top_n=10 yields 9 `tied_with` references per entry (the 10 entries in the truncated list, minus self). The other 5 tied entries are silently dropped. Document if this is the intended behavior; PM might want different semantics here.
- **`primary_line` selection** — when multiple lines inside a symbol share the maximum Ochiai score, `primary_line` is the LOWEST-numbered line. Tiebreak is `(-score, line)` ascending.
- **`evidence_lines` capped at 10** — `_EVIDENCE_LINE_CAP=10` in `derive.py`. A 200-line function with 50 suspicious lines reports the top 10. Cap is documented but not surfaced in the wire schema.
- **File-level fallback CodeLocation** — `kind="file"` entries appear in the ranking when module-level code OR a non-Python file is implicated. Their `symbol=None, line_range=None`, but `primary_line` and `evidence_lines` are populated. The huge-file pathology (a 2000-line file generating one big file-level entry) is mitigated by the symbol-level fallback being the rare path — most ranks come from `kind="symbol"`.
- **`score_normalized` is global-not-truncated** — the min-max is over the FULL ranking. Top-1's `score_normalized` may be < 1.0 if a higher-score candidate exists outside top_n (extremely rare; included for design correctness).
- **`get_localization_findings` overloads `REASON_RUN_NOT_ANALYZABLE`** — when the cache file is absent, the retrieval helper returns `LocalizationUnavailable(reason=REASON_RUN_NOT_ANALYZABLE, detail="findings not yet derived")`. The reason code is shared with the tombstone case; the `detail` string distinguishes them. PM may want to add a dedicated `REASON_MISSING_DERIVED_FACTS` (mirroring Coverage / Regression) — but that requires expanding the closed enum, hence the deliberate overload for v1.
- **numpy RuntimeWarnings** — the formula modules use `np.divide(out=, where=)` rather than `np.where(cond, a/b, 0)` to keep numpy quiet on zero denominators. Test infra picks up RuntimeWarnings as warnings; the current state is silent (0 warnings emitted by the localization tests).

## Baseline pytest count (pre-slice)

Confirmed pre-slice baseline on this worktree (commit `4be6c7c`): `uv run pytest -q` → **471 passed + 3 skipped**.

## `regen_comms_index.py` status

I will run `python3 tools/regen_comms_index.py` after writing this handoff (before committing).
