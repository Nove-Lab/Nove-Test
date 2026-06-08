---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-08
slug: defect7-failure-proximity-warning-loop
related:
  - agent-comms/tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
---

# Handoff — Defect 7: `failure_proximity` mode formula-mismatch warning loop

## Worktree

- Path: `/home/yjshin/dev/aispace/novetest-localization-defect7`
- Branch: `localization-team/defect7-failure-proximity-warning-loop`
- Base commit: `4184cd1` (`comms: brief B1 polish parallel pair (defect7 + fixed-tests-spec)`)

## Files written / modified

| File | Status | Change |
|---|---|---|
| `src/novetest/cli/app.py` | Modified | Added carve-out branch inside `_rederive_if_cache_overrode_flags` + new helper `_build_localization_formula_noop_warning`. ~50 LOC inserted, 0 removed. |
| `tests/unit/cli/test_localization.py` | Modified | Extended `_make_finding(mode=...)`; added 5 new tests covering brief's full 5-case matrix. ~210 LOC inserted, 0 removed. |
| `tests/unit/cli/test_localization_latest.py` | Modified | Extended `_make_finding(mode=...)`; added 1 mirror test for the `latest` verb path. ~85 LOC inserted, 0 removed. |
| `tests/integration/cli/test_localization_e2e.py` | Modified | Added `seeded_no_coverage_workspace` module-scoped fixture + 2 new E2E tests (subprocess `novetest localization --formula op2` against `localization-no-coverage` fixture). ~145 LOC inserted, 0 removed. |
| `WORKLOG.md` | Modified | Top entry added. |
| `agent-comms/handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md` | Created | This file. |
| `agent-comms/INDEX.md` | Modified | Regenerated via `tools/regen_comms_index.py`. |

**Files NOT touched** (per task brief §"만지지 말 것"):
- `cli/output.py::EnvelopeWarning` shape — frozen 2026-06-07; reused as-is.
- `run/types.py::AdapterWarning` — Run team territory; not involved.
- `run/adapters/**` — Run team territory.
- `coverage/**` — Coverage team territory; unrelated.
- `src/novetest/localization/failure_proximity.py` — engine itself (the placeholder formula is a mode definition, NOT a bug; brief §"Out of scope" pins this).
- v1 metadata bridge keys (`coverage_unavailable_*`) — post-MVP cleanup territory.

## Verification result

### `uv run mypy --strict src/novetest`
```
Success: no issues found in 92 source files
```
Source-file count unchanged from base — this slice extends an existing function and adds one helper, no new files.

### `uv run pytest -q tests/unit tests/integration`
```
1183 passed, 26 skipped, 1 failed in 31.68s
```

The single failure is **pre-existing host-equipment dependency, NOT a regression**:
- Test: `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
- Failure: `AdapterInvocationError: dotnet not found on PATH; install .NET SDK 8.0+`
- Reproduction on base commit: `git stash + git checkout 4184cd1 -- . + uv run pytest <same test>` → **identical failure on base commit `4184cd1`**.
- Brief §"§2.5 equip-and-exercise 게이트" explicitly says §2.5 gate does NOT apply to this slice ("native 어댑터 src + 통합 테스트를 동시 터치하지 않음 → §2.5 게이트 발동 안 함. 일반 host에서 진행 가능."). The current host is intentionally non-equipped per brief.

All cycle-touching tests green:
- 5 new unit tests in `test_localization.py` (full 5-case matrix from brief).
- 1 new unit test in `test_localization_latest.py` (latest verb mirror).
- 2 new integration tests in `test_localization_e2e.py` (subprocess + cache-mtime invariant).
- All 24 pre-existing unit tests in `test_localization.py` still green.
- All 4 pre-existing integration tests in `test_localization_e2e.py` still green.
- All 23 pre-existing unit tests in `test_localization_latest.py` still green.

### CLI wire-level envelope capture

Captured via the new integration test `test_localization_failure_proximity_non_default_formula_emits_noop_warning` (real subprocess against materialized `localization-no-coverage` fixture):

```
$ NOVETEST_OUTPUT=json novetest localization <run_id> --formula op2
```

Returns (relevant fields):
```json
{
  "command": "localization",
  "ok": true,
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "failure_proximity",
      "formula": "ochiai",
      ...
    }
  },
  "warnings": [{
    "code": "localization-formula-noop-in-mode",
    "message": "requested --formula='op2' is a no-op in 'failure_proximity' mode; engine pins formula='ochiai' as a placeholder for this mode (no SBFL formula is computed). Re-running with a different --formula value will not change the result.",
    "details": {
      "requested_formula": "op2",
      "returned_formula": "ochiai",
      "mode": "failure_proximity"
    }
  }]
}
```

Exit code: 0. On-disk cache file mtime: UNCHANGED from pre-call (load-bearing no-loop evidence; pre-Defect-7 the same invocation would have unlinked + rewritten this file).

## Worklog entry text (already appended to `WORKLOG.md` top)

```
## 2026-06-08 — phase4 / defect7-failure-proximity-warning-loop (B1 polish; one half of parallel pair)

- Landed: src/novetest/cli/app.py — new carve-out branch inside
  _rederive_if_cache_overrode_flags that recognizes the failure_proximity
  formula-placeholder noop case (...) ...
... [full text in WORKLOG.md head]
```
(See `WORKLOG.md` top entry for the verbatim text.)

## DoD bullets believed closed

All 10 bullets from task brief §"Definition of done":

- [x] **#1**: `failure_proximity` mode + non-default formula 호출 시 envelope.warnings에 noop warning code 1건 emit (단일 invocation 안에서) — pinned by unit test `test_localization_run_failure_proximity_non_default_formula_emits_noop_warning_once` (matrix #2) + integration test `test_localization_failure_proximity_non_default_formula_emits_noop_warning`.
- [x] **#2**: 동일 invocation 안에서 mismatch -> re-derive -> mismatch 무한 loop 발생 안 함 — pinned by unit test `test_localization_run_failure_proximity_non_default_formula_no_rederive_loop` (matrix #5; call-count + cache-existence invariant) + integration test's pre/post mtime assertion.
- [x] **#3**: mode != `failure_proximity` 시 기존 동작 unchanged — pinned by unit tests `test_localization_run_sbfl_default_formula_unchanged_behavior` (matrix #3) + `test_localization_run_sbfl_non_default_formula_unchanged_behavior` (matrix #4) + all 6 pre-existing cache-rederived tests in `test_localization.py` still green.
- [x] **#4**: 통합 테스트 no-coverage fixture + `--formula op2` CLI subprocess → envelope.warnings 검증 — pinned by `test_localization_failure_proximity_non_default_formula_emits_noop_warning` against `localization-no-coverage` fixture.
- [x] **#5**: 단위 테스트 매트릭스 위 5개 그린 — all 5 named in the test file `test_localization.py` + 1 mirror in `test_localization_latest.py`.
- [x] **#6**: `uv run mypy --strict src/novetest` 클린 — confirmed (92 src files).
- [x] **#7**: `uv run pytest -q tests/unit tests/integration` 그린 — 1183 passed + 26 skipped; 1 pre-existing dotnet host-equipment failure is unrelated (verified on base commit; brief §"§2.5" allows non-equipped host).
- [x] **#8**: WORKLOG.md 엔트리 추가 — done (top of file, charter-compliant format).
- [x] **#9**: Handoff 작성 — this file.
- [x] **#10**: `python3 tools/regen_comms_index.py` 실행 + INDEX 변경 스테이지 — done before commit.

## Open items / surprises

### 1. Compound case decision — PM ratification requested

The task brief is silent on the edge case `failure_proximity + formula_mismatch AND top_n_mismatch` (i.e., user passes BOTH `--formula=op2` AND `--top-n=5` against a failure_proximity cache that has `(ochiai, 10)`). I decided unilaterally to fall through to the existing cache-rederived path in this case:

```python
is_failure_proximity_formula_noop = (
    outcome.mode == "failure_proximity"
    and formula_mismatch
    and not top_n_mismatch   # ← compound case falls through
)
```

**Rationale**: `top_n` IS a meaningful parameter in failure_proximity (it controls the entry-count of the heuristic ranking), so a `top_n` mismatch SHOULD still trigger an actual re-derive. The placeholder-formula mismatch noop is the structural-noop discriminator, not a generic "skip all re-derives in failure_proximity" rule. The user's formula intent gets disclosed via the cache-rederived warning's `details.previous.formula="ochiai"` field rather than via a separate noop warning — preserving the brief's "single warning per invocation" principle.

**Trade-off**: A user passing both flags simultaneously in failure_proximity mode does NOT see the `localization-formula-noop-in-mode` code; they see `localization-cache-rederived` instead. They CAN still infer the noop from `previous.formula="ochiai" → requested.formula="op2"` in the warning's details, but the inference requires reading details rather than gating on a discrete code.

**Alternative shapes** if PM disagrees with the above:
- (A) Emit BOTH warnings (multi-warning surface — would require `_rederive_if_cache_overrode_flags` to return `tuple[..., tuple[EnvelopeWarning, ...]]` instead of `tuple[..., EnvelopeWarning | None]` — small Type API change rippling through 2 call sites in `localization_run` + `localization_latest`).
- (B) Emit noop warning only, skip re-derive even when top_n differs (compound formula-noop dominates; user must drop `--formula` to honor `--top-n` change — semantically lossy).
- (C) Current implementation (cache-rederived warning carries the formula transition in `previous` details; noop warning fires only when formula is the SOLE mismatch).

I went with (C) as the smallest surface change that satisfies the literal brief matrix. If PM ratifies a different shape, the change is localized to the `is_failure_proximity_formula_noop` predicate in `cli/app.py` + adding a new test case + (for option A) the return-type change.

### 2. Warning code naming

Used the brief's literal suggested code `localization-formula-noop-in-mode`. Considered shorter alternatives (`localization-formula-noop`, `localization-noop-formula`) but kept the literal because:
- "in-mode" disambiguates from any future "formula doesn't exist" or "formula deprecated" surfaces (the noop is mode-specific, not formula-specific).
- The literal is greppable + matches the brief's recommendation exactly.
- AI agents may have been trained / pinned on the literal name in user-facing documentation.

If PM prefers a shorter code, the rename is mechanical: one string constant in `_build_localization_formula_noop_warning` + 4 string-literal updates across test files.

### 3. Warning emit location — kept in `cli/app.py`

Brief §"Emit 위치 — orchestration 선호" recommended orchestration-layer emit but allowed engine emit "if more natural". Current `_rederive_if_cache_overrode_flags` lives in `cli/app.py` (mismatch detection is a CLI-flag-explicitness concern, not an engine concern — the engine has no notion of "user explicitly passed `--formula`"). Adding the carve-out as a sibling branch inside the same function is the minimal-surface choice.

Brief allows this: "정확한 emit 위치는 코드 inspect 후 Localization팀이 결정. engine 내부에서 emit하는 게 더 자연스럽다면 그 판단을 존중함 (handoff에 근거 명시 요청)." — recording the rationale here.

### 4. `_make_finding` helper duplication

Both `tests/unit/cli/test_localization.py` and `tests/unit/cli/test_localization_latest.py` carry independent copies of `_make_finding`. Both gained the same `mode=...` parameter + same `if mode == "failure_proximity":` branch. The two helpers stay independent (not a shared import — the existing pattern, predating this slice).

Future cleanup option: consolidate into `tests/unit/cli/_localization_finding_fixtures.py` if and only if the duplication ever causes drift. Not blocking; flagged for visibility.

### 5. Pre-existing `dotnet` host-equipment test failure

`tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` fails on this host (no `.NET SDK 8.0+`). Reproduced on base commit `4184cd1` via stash + checkout — failure is environmental, NOT a regression caused by this slice. Brief §"§2.5 equip-and-exercise 게이트" explicitly waives the §2.5 binding gate for this slice. Main Branch's merge gate should expect this test to skip / fail on equally non-equipped hosts; on an equipped host, it should pass (slice change does not touch dotnet code paths).

## Pre-merge checklist for Main Branch

- [ ] Verify worktree builds: `uv sync` + `uv run pytest -q tests/unit tests/integration -k "localization or dotnet_warnings"` (the localization tests must all pass; dotnet_warnings may skip/fail per host).
- [ ] Verify mypy: `uv run mypy --strict src/novetest` → 92 src files, clean.
- [ ] FF-merge order per brief: `localization → regression` (alphabetic; Regression team's `fixed-tests-spec` is the parallel cycle pair).
- [ ] File-disjoint verification: this slice touches `src/novetest/cli/app.py` + 3 test files; Regression team's slice should touch only `src/novetest/regression/` + its tests. WORKLOG.md is the only file both teams touch — standard top-entry-merge resolution.
- [ ] Write verification doc at `agent-comms/verifications/2026-06-08-defect7-failure-proximity-warning-loop.md` for Manual Test. Key probe paths:
  - `data.localization_outcome.mode == "failure_proximity"`
  - `data.localization_outcome.formula == "ochiai"` (placeholder, NOT the user's `--formula=op2`)
  - `warnings[0].code == "localization-formula-noop-in-mode"`
  - `warnings[0].details = {requested_formula: "op2", returned_formula: "ochiai", mode: "failure_proximity"}`
  - On-disk cache file mtime: unchanged across the call (this is the wire-level no-loop proof — recommend Manual Test capture mtime pre/post explicitly).

## Files written / modified — final tally

| Category | Count | LOC delta |
|---|---|---|
| `src/` modified | 1 | +50 |
| `tests/unit/` modified | 2 | +295 |
| `tests/integration/` modified | 1 | +145 |
| `tests/fixtures/` modified | 0 | 0 (no new fixture needed; `localization-no-coverage` reused) |
| `WORKLOG.md` | 1 | +13 (one entry) |
| `agent-comms/handoffs/` | 1 | new file (this) |
| `agent-comms/INDEX.md` | 1 | regenerated |

Brief estimate was ~20-40 LOC src + ~30-50 LOC test. Actual src landed at +50 (helper docstring + carve-out docstring make the bulk of the difference; the load-bearing logic is ~10 lines). Test LOC significantly above estimate (+440) because the 5-case matrix + latest mirror + integration's 2-test fixture suite each contributed; each test is well-justified by the DoD requirement to pin a discrete invariant. Recommendation: future briefs with explicit test matrices specify ~50 LOC per pinned matrix case as a rough sizing guideline.
