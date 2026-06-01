---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-01
slug: localization-cache-flag-invalidation-defect5
related:
  - agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md
  - agent-comms/history/2026-06-01-defect4-closed-and-defects-5-6-surfaced.md
---

# Handoff: Defect 5 — `localization` cache silently dropping explicit `--formula` / `--top-n` flags

## Worktree

- Path: `/home/yjshin/dev/novetest-localization-defect5`
- Branch: `novetest-localization-defect5`
- Base commit: `0ed8fe4` (origin/main tip, post-Defect-4 close)
- Tip: 1 commit ahead of base
- Status: ready for FF-merge

## What landed

**Source: 2 files modified, 0 new files (source-file count stays at 72).**

| File | Change |
|---|---|
| `src/novetest/cli/app.py` | Added `_rederive_if_cache_overrode_flags` helper (50-line docstring) + renamed/refit `_build_localization_cache_mismatch_warning` → `_build_localization_cache_rederived_warning`. Refactored `localization_run` + `localization_latest` to use the peek-after-call rederive pattern. New import `from novetest.localization.persistence import localization_findings_path`. |
| `src/novetest/localization/derive.py` | `derive_localization_findings` docstring extended (~10 lines) to clarify the engine's cache layer is policy-free and that orchestration owns invalidation. ZERO code change to the function body. |

**Tests: 3 files modified, 0 new files. Net test count delta: 0.**

| File | Change |
|---|---|
| `tests/unit/cli/test_localization.py` | 6 cache-warning scenarios overhauled in-place (old `_emits_warning_on_*_mismatch` → new `_rederives_on_*_mismatch`); added `_two_phase_derive` helper + `stub_cache_path` fixture. Imports updated. |
| `tests/unit/cli/test_localization_latest.py` | 3 cache-warning scenarios overhauled in-place; new `stub_cache_path` fixture. Other 5 tests untouched. Import updated. |
| `tests/integration/cli/test_localization_e2e.py` | E2E test 4 rewrote — now asserts re-derive + cache-overwrite + new warning code + follow-up read-back of fresh state. |

## DoD bullets believed closed

Per task brief §DoD:

- [x] Cache-handling code path detects flag mismatch on cache hit (in `_rederive_if_cache_overrode_flags`).
- [x] On mismatch with explicit flags, re-derive + persist new findings (Option A — cache `.unlink()` + re-invoke engine; engine writes fresh).
- [x] Cached-read regression-pin: same flags → still cached (`test_localization_run_no_warning_when_request_matches_cache` asserts engine called exactly once + cache file untouched).
- [x] 5 unit tests + 1 integration test (5 unit cases enumerated in brief §3 all covered; +1 bonus unavailable-outcome case; +1 e2e).
- [x] Decision on warning channel (§4) — documented below: Option (b) — keep slot, rename to `localization-cache-rederived`.
- [x] Full pytest suite green; mypy strict clean.
- [x] No `delivery-phasing.md` checkbox movement (per brief: "bug fix, not phase-tracked").

## Verification result

```
$ uv run pytest -q tests/unit tests/integration
757 passed, 10 skipped in 52.26s
  (baseline at 0ed8fe4: 757 + 10 → 0 net delta — existing tests
  overhauled in-place; new tests pin the new contract)

$ uv run mypy
Success: no issues found in 72 source files
  (source-file count unchanged from baseline; 0 new src files)

$ uv run pytest -q tests/unit/cli/test_localization.py \
                  tests/unit/cli/test_localization_latest.py \
                  tests/integration/cli/test_localization_e2e.py
28 passed in 2.37s
  (16 + 8 + 4 — identical to baseline)
```

## Pre-flight empirical proof (per brief §"Empirical reproduction")

Used `tests/fixtures/projects/localization-branch` (pytest-only, no
toolchain dependency) since this dev box has no cargo. The Defect-5 bug is
ecosystem-agnostic — pure CLI cache-invalidation policy — so the
`localization-branch` repro is equivalent to the brief's
`localization-aggregate-only` repro for the load-bearing assertion.

### PRE-FIX (on main checkout `0ed8fe4`, before this slice merges):

```sh
$ cp -r tests/fixtures/projects/localization-branch /tmp/d5-prefix
$ cd /tmp/d5-prefix
$ export PATH=/home/yjshin/dev/Nove-Test/.venv/bin:$PATH

$ novetest init                              # exit 0
$ novetest run --coverage                    # exit 0

$ novetest localization latest > /tmp/d5-prefix-step1.json
   formula: ochiai / top_n: 10
   warnings: []                              # baseline default state cached

$ novetest localization latest --formula op2 --top-n 3 > /tmp/d5-prefix-step2.json
   formula: ochiai / top_n: 10               # ← BUG: flags silently dropped
   warnings: ['localization-cache-args-ignored']
                                             # ← pre-Defect-5 disclosure
                                             #   warning (the bug was visible
                                             #   only via this warning; the
                                             #   actual data was still wrong)
```

### POST-FIX (this worktree):

```sh
$ cp -r tests/fixtures/projects/localization-branch /tmp/d5-repro
$ cd /tmp/d5-repro
$ export PATH=/home/yjshin/dev/novetest-localization-defect5/.venv/bin:$PATH

$ novetest init                              # exit 0
$ novetest run --coverage                    # exit 0

$ novetest localization latest               # Step 1 — bake defaults
   formula: ochiai / top_n: 10
   warnings: []

$ novetest localization latest --formula op2 --top-n 3   # Step 2 — explicit
   formula: op2 / top_n: 3                   # ← FIXED: flags applied
   warnings: [{
     code: 'localization-cache-rederived',
     details: {
       previous: {formula: 'ochiai', top_n: 10},
       requested: {formula: 'op2', top_n: 3,
                   formula_explicit: True, top_n_explicit: True},
       cache_path: '.novetest/localization/findings/run_.../localization_findings.json'
     },
     message: "cached findings (--formula='ochiai' --top-n=10) were
              re-derived at requested --formula='op2' --top-n=3;
              cache overwritten at <path>"
   }]                                        # ← post-Defect-5 audit warning

$ novetest localization latest               # Step 3 — read-back, no flags
   formula: op2 / top_n: 3                   # ← cache reflects re-derive
   warnings: []                              # ← cache-as-source-of-truth
                                             #   subsequent defaulted calls
                                             #   correctly serve op2/3, NOT
                                             #   the previously-cached
                                             #   ochiai/10
```

The three-step sequence proves all three contract bullets from brief §3
integration:

1. Initial call with defaults persists `ochiai/top_n=10` ✓
2. Second call with `--formula op2 --top-n 3` re-derives and returns
   `op2/top_n=3` findings ✓ (brief used `op2`/`3`; my E2E test uses
   `dstar2` but the contract is identical)
3. Persisted file now reflects `op2/top_n=3` ✓ (Step 3 above)

## Warning channel decision (§4): Option (b) — keep slot, rename code

**Decision**: kept the envelope `warnings[]` slot active; renamed the code
from `localization-cache-args-ignored` → `localization-cache-rederived`;
flipped the details schema (`cached` → `previous`); reworded the message
to reflect the new "cache overwritten" semantics.

**Rationale**:
1. The disclosure infrastructure was already in place + tested — refitting
   the existing slot is cheaper than dropping + re-adding.
2. AI agents benefit from cost transparency — the re-derive may be
   expensive (Phase 4 §4 #3 perf NFR allows 500 failed × 50k locations in
   <8s, so the re-compute isn't free; a downstream consumer iterating on
   formulas across calls should know which calls paid the cost).
3. The new warning carries the PREVIOUS cached args, so a downstream
   consumer can audit what the cache used to be and verify they overrode
   it intentionally.

Option (a) "drop warning entirely" would have been simpler but lost the
audit signal — no way for a consumer to learn from the wire envelope that
a re-compute happened.

## Open questions for PM

1. **Envelope freeze v2 amendment**: the `localization-cache-args-ignored`
   warning was pinned by `decisions/2026-05-30-localization-outcome-envelope-shape.md`
   §"Cache-vs-request mismatch warning". Post-Defect-5 the code is
   `localization-cache-rederived` and the details schema differs
   (`previous` vs `cached`). PM may want to amend that decision OR file a
   supersede entry that pins the new code + schema. Not blocking — the
   warning is on the wire and works correctly; this is just bookkeeping
   alignment.

2. **Engine-API contract clarification**: `derive_localization_findings`'s
   docstring now reads "the cache layer is intentionally policy-free" and
   names the CLI as the policy site. If a future Replay / Orchestration
   caller wants the auto-invalidation behavior at the engine level, the
   right move is to either (a) thread the policy through as an engine
   kwarg in that future slice, or (b) have that caller use the same
   `localization_findings_path(...).unlink()` pattern. Flagged because the
   answer affects how the engine-API contract evolves.

3. **DEVIATION from brief §3 test location**: brief said
   "`tests/unit/localization/` (or `tests/unit/orchestration/` if the
   cache-handling lives there)". My implementation places the cache-
   invalidation policy in `src/novetest/cli/app.py` (the CLI layer above
   orchestration), so the unit tests live in `tests/unit/cli/`. The brief's
   intent (test where the policy lives) is satisfied; the literal path
   differs. Not blocking; flagging for the cycle-close history entry.

## Suggested next step for Main Branch

1. FF-merge `novetest-localization-defect5` onto `main` (clean — base is
   already `0ed8fe4`).
2. Run the equipped-host gate (no cargo-toolchain-specific behavior in
   this slice — the cargo-skip-guarded tests from prior cycles continue
   to skip cleanly on Rust-less hosts; the cargo path doesn't traverse
   the Defect-5 surface).
3. Write the verification doc pointing Manual Test at the brief's
   §"Empirical reproduction" sequence — either the `localization-aggregate-only`
   path (cargo, equipped host) or the `localization-branch` path (pytest,
   any host). Both surface the same fix.

The sibling Defect 6 slice (status.sub_reports staleness, orchestration-
team territory) is independent and can dispatch in parallel.
