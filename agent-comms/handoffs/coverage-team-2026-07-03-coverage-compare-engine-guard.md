---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-03
slug: coverage-compare-engine-guard
worktree: /home/yjshin/dev/novetest-coverage-engine-guard
branch: coverage/coverage-compare-engine-guard
base_commit: 7c6ece6
related:
  - agent-comms/tasks/coverage-team-2026-07-03-coverage-compare-engine-guard.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Handoff: coverage-compare-engine-guard (D5 Finding A — the corruption path, closed)

## TL;DR

`compare_coverage_facts` now refuses cross-engine pairs with
`CoverageUnavailable(REASON_ENGINE_MISMATCH)` — same wire string
("engine-mismatch") and detail shape as Regression's guard. `novetest
coverage diff <pytest_run> <cargo_run>` emits the unavailable envelope
instead of a silently-meaningless `CoverageDelta`. Zero CLI changes needed
(both JSON projection and TEXT renderer are reason-generic). Envelope
decision amended additively per PM pre-authorization. Ready for FF-merge.

## Worktree details

- Path: `/home/yjshin/dev/novetest-coverage-engine-guard`
- Branch: `coverage/coverage-compare-engine-guard`
- Base: `7c6ece6` (`main` HEAD at Wave-2 dispatch)
- One commit pending (code + WORKLOG + this handoff bundled for the
  pre-commit hook gate)

## Files changed (6 + WORKLOG + handoff)

| File | Change |
|---|---|
| `src/novetest/coverage/results.py` | +`REASON_ENGINE_MISMATCH = "engine-mismatch"` constant + `KNOWN_REASONS` entry (~+13 LOC with rationale comment) |
| `src/novetest/coverage/compare.py` | Guard after both sides resolve; docstring documents D5 rationale + engine-side placement (~+27 LOC) |
| `agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md` | Additive amendment (PM pre-authorized in the brief §2): reason enum + Amendment 2026-07-03 blockquote |
| `tests/unit/coverage/conftest.py` | `seed_fact_set` forwards fact set's `engine_name`/`ecosystem` to the seeded RunRecord (was hardcoded pytest) |
| `tests/unit/coverage/test_compare.py` | `_make_fact_set` gains engine params; 4 new tests |
| `tests/integration/orchestration/test_coverage_cli.py` | 1 new subprocess E2E: cross-engine `coverage diff` refusal |

Production diff ~40 LOC; test diff ~230 LOC. (PM's estimate was ~25/~80 —
overshoot is the 2 extra ordering/symmetry pins + the in-process cargo
seeding helper for the CLI case; challenge welcome, all 4 unit tests pin
distinct contracts.)

## Task items — disposition

| # | Brief item | Disposition |
|---|---|---|
| 1 | Guard inside `compare_coverage_facts`, engine-side | DONE. Fires only after both sides resolve (ordering pinned by test — a missing side surfaces its own reason first, preserving 2026-05-16 constraint #4 semantics for single-side-missing). `run_reference` names the **baseline** side for the pair-level reason (constraint #4 tie-break extended; recorded in the amendment). Detail carries both names, mirroring `regression/compare.py:178-183`. |
| 2 | Envelope: additive reason + decision amendment | DONE. `"engine-mismatch"` appended to the `kind: "unavailable"` reason enum + Amendment 2026-07-03 blockquote citing this brief's slug. |
| 3 | Callers: verify no CLI changes needed | VERIFIED — no changes. `cli/app.py::_coverage_delta_payload` renders `outcome.reason` generically (no enum matching); TEXT mode's `cli/renderers/_outcomes.py::_reason` likewise (`unavailable (<reason>)`). New reason flows through both output modes untouched. Pinned end-to-end by the new subprocess test. |
| 4 | Regression embed: assert unreachability, no behavior change | DONE via test comment (in `test_compare_same_engine_non_pytest_pair_still_produces_delta` docstring): `_maybe_coverage_change` runs only after `compare_runs`' own engine guard passes, and folds ANY `CoverageUnavailable` to `coverage_change = None`. Zero Regression files touched. |

## Verification (all `env -u PYTHONPATH` per GOTCHAS)

- `uv run mypy` → `Success: no issues found in 114 source files` (baseline unchanged)
- `uv run pytest -q tests/unit/coverage/ tests/integration/orchestration/test_coverage_cli.py` → **158 passed**
- `uv run pytest -q tests/unit tests/integration` → **1412 passed, 13 skipped, 1 failed** — the 1 failure is the chronic dotnet host-equip miss (`test_xunit_v3_deferral_emits_envelope_warning_via_adapter`, `dotnet` not on PATH), pre-existing and unrelated
- **47 snapshots passed; `git status --porcelain | grep -i ambr` → empty** — acceptance criterion "existing same-engine snapshots byte-identical" ✓
- Acceptance criterion #1 (`coverage diff <pytest_run> <cargo_run>` → unavailable envelope, no delta) pinned by the new subprocess E2E: real CLI, real store, real pytest `--coverage` run + seeded cargo-test facts → `kind: "unavailable"`, `reason: "engine-mismatch"`, both names in `detail`, exit 0 + `ok: true` (constraint #3), no delta fields leak (constraint #1)

## Acceptance bullets believed closed (PM verifies + ticks)

1. ✓ Cross-engine `coverage diff` returns the unavailable envelope with the new reason — no `CoverageDelta` emitted
2. ✓ Existing same-engine snapshots byte-identical (47 passed, zero porcelain drift)
3. **CI-PENDING** Full suite green on the CI matrix — local full suite green (modulo chronic dotnet); 10/10 matrix cite requires post-merge `ci.yml` run (session gh identity is dispatch-restricted per the 2026-06-22 gotcha)
4. ✓ mypy clean
5. ✓ WORKLOG entry
6. ✓ Handoff at this path

## Main Branch action items

1. FF-merge `coverage/coverage-compare-engine-guard` (Wave-2 cohort; check PM's merge-order note if the parallel Localization/Orchestration slices land同cycle — no file overlap expected: this slice touches only `coverage/`, coverage tests, and the coverage envelope decision).
2. Post-merge: `gh workflow run ci.yml --ref main` → cite the 10/10 matrix run in the verification request (closes acceptance bullet #3).
3. Verification request to Manual Test: cross-engine `coverage diff` AND top-level `compare` smoke — `compare`'s `coverage_delta` half shares `compare_coverage_facts` so it surfaces the same refusal; its `regression_outcome` half already refused via Regression's own guard. Both halves of the `compare` envelope now agree on cross-engine pairs.

## Design notes / deviations

- **`run_reference` names the baseline side** for the pair-level reason.
  `CoverageUnavailable` has a single `run_reference` (vs Regression's
  two-sided independently-nullable shape); the 2026-05-16 decision's
  constraint #4 tie-break ("both sides unavailable → baseline named")
  extends naturally. Detail carries both engine names so consumers never
  need a second lookup. A two-reference unavailable shape would be an
  envelope v2 (breaking) — not this slice.
- **`seed_fact_set` fixture hygiene fix** (test-only): it hardcoded
  pytest RunRecords for any fact set; now forwards the fact set's
  `engine_name`/`ecosystem`. Behavior-neutral (compare reads engine from
  the fact set), but keeps Memory↔Coverage consistent in mixed-engine
  scenarios.
- **CLI integration case seeds cargo facts in-process** rather than
  running a real cargo toolchain — deterministic, host-independent, and
  the subprocess still exercises the identical read path
  (`_resolve_run_reference` → `compare_coverage_facts` → projection).

## Informational questions (no blockers)

- **Q1**: `coverage/__init__.py` does NOT re-export REASON constants
  (unlike `regression/__init__.py` which does). Existing pattern — callers
  import from `novetest.coverage.results` directly. Kept surgical; if PM
  wants API symmetry, that's a one-line follow-up.
- **Q2**: `REASON_INCOMPARABLE_GRANULARITY` has existed in `results.py`
  since Phase 2 but nothing emits it (granularity mismatch is allowed by
  design, both values carried on the delta). Dead constant — flag for a
  future hygiene sweep or keep as reserved.

## Suggested commit message

```
coverage: refuse cross-engine pairs in compare_coverage_facts (D5 guard)

D5 audit Finding A: `compare_coverage_facts` computed set-difference
deltas across engine boundaries with zero validation — `novetest
coverage diff <pytest_run> <cargo_run>` silently emitted a meaningless
CoverageDelta. Guard added engine-side (not caller-side) so every
present and future consumer is protected by construction.

- New REASON_ENGINE_MISMATCH ("engine-mismatch" — same wire string as
  Regression's constant so agents match one string across engines)
- Detail carries both engine names, mirroring regression/compare.py's
  guard shape; run_reference names the baseline side per the
  2026-05-16 envelope decision's constraint-#4 tie-break
- Envelope decision amended additively (PM pre-authorized)
- Zero CLI changes: JSON projection + TEXT renderer are reason-generic
- Zero Regression changes: its coverage embed runs only after its own
  engine guard, and folds any unavailable to None (unreachability
  asserted via test comment)

Policy: decisions/2026-07-03-engine-selection-policy.md D5.
Brief: tasks/coverage-team-2026-07-03-coverage-compare-engine-guard.md

Verification: mypy 114 files clean; full suite 1412 passed / 13
skipped / 1 chronic dotnet host-equip failure (pre-existing); 47
snapshots byte-identical; new subprocess E2E pins the CLI refusal
end-to-end. CI 10/10 cite deferred to post-merge run.
```
