---
from: novetest-localization-team
to: novetest-main-branch-team
type: handoff
status: pending
created: 2026-07-04
slug: engine-scoped-regression-prior
related:
  - agent-comms/tasks/localization-team-2026-07-03-engine-scoped-regression-prior.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Handoff: Localization — engine-scoped regression-prior lookup (D5, Finding B)

## Worktree

- **Path**: `/home/yjshin/dev/novetest-localization-regression-prior`
- **Branch**: `localization/engine-scoped-regression-prior`
- **Base**: main `7c6ece6`
- **Commit**: `a09208c` (single commit; NOT pushed, NOT self-merged)

## Files written / modified

- `src/novetest/localization/derive.py` — `try_get_latest_regression_facts`
  delegates prior-pair selection to Regression's shared engine-aware
  selector `resolve_baseline_for_run(store, entry)` (D5); the local
  engine-blind `find_runs_for_target` + newest-strictly-older scan is
  deleted, the import dropped. **Signature change**: second param
  `record: RunRecord` → `entry: MemoryEntry` — the selector's contract;
  the sole production caller (`derive_localization_findings`, same file)
  already holds the `MemoryEntry`, so no re-lookup and no synthetic
  wrapper. Best-effort posture preserved verbatim (never raises, never
  derives, cache-only `get_regression_facts` read, `None` on any failure).
- `src/novetest/localization/__init__.py` — module blurb for the export
  updated ("comparable" now spelled out as same-target + same-engine per D5).
- `tests/unit/localization/test_regression_prior.py` — NEW, 6 tests
  (details below).
- `design/interace-contract/localization.md` — Notes bullet: Regression
  dependency now `resolve_baseline_for_run` + `get_regression_facts`,
  citing D5.
- `design/workflows/localization.md` — `derive_localization_findings`
  workflow chain gains `regression/resolve_baseline_for_run` before
  `regression/get_regression_facts`.
- `WORKLOG.md` — entry prepended (pasted below).

## Verification result

All commands `env -u PYTHONPATH`, run in the worktree:

1. `uv run mypy` (exact CI gate, strict) → **Success, 114 source files**.
2. `uv run pytest -q tests/unit tests/integration` → **1413 passed /
   13 skipped / 1 failed, 47 snapshots passed, zero `.ambr` drift**.
   The 1 failure is
   `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
   — `dotnet` not found on PATH — **reproduced identically on unmodified
   main in the shared checkout** (`which dotnet` → not found). Host
   toolchain drift vs. the 2026-07-03 sessions (which recorded 1418/3/0
   on an equipped host), NOT this slice. Post-merge CI matrix is the
   binding green gate.
3. Targeted `uv run pytest -q tests/unit/localization
   tests/integration/localization tests/unit/regression
   tests/unit/orchestration` → **410 passed**.
4. **Pre-fix proof** (acceptance criterion "pre-fix it degrades"): with
   the `derive.py` change stashed, the acceptance test fails with
   `regression_reweighted=False` — exactly the silent degradation the
   task describes. Note: the direct-probe tests also fail pre-fix but
   for an artifact reason (old signature swallows the
   `MemoryEntry.target_expression` AttributeError in its try/except);
   cite the engine-boundary acceptance test as the behavioral proof.

## Acceptance criteria → evidence

- **New test, series [pytest, cargo, pytest] with pytest-pair cache →
  aggregate-mode reweighting activates**:
  `test_mixed_engine_store_applies_fluccs_reweighting` drives the full
  `derive_localization_findings` path on a real store — asserts
  `mode == "sbfl_aggregate"`, `metadata["regression_reweighted"] is True`,
  boosted changed-file at rank 1. Plus 5 supporting tests: direct-probe
  mixed-engine pair one step back; single-engine unchanged (pre-D5
  behavior pinned); no-prior → None; cross-engine-only priors → None;
  same-engine prior without cache → None.
- **Full suite green on CI matrix** — pending post-merge run (local full
  suite green modulo the pre-existing host-toolchain dotnet failure
  documented above); **mypy clean** — yes; **WORKLOG entry** — yes;
  **this handoff** — yes.

## Task scope items 2 & 3 (report-backs)

- **§2 test-seam migration**: **NO-OP** — grep-verified that no
  localization test (unit or integration) stubs/monkeypatches
  `find_runs_for_target`; the per-mode tests inject `regression_facts`
  directly at the helper boundary. Nothing hard-fails from the removed
  import. (The Regression handoff's seam-swap pattern applied to
  orchestration test files in wave 1; Localization had no such seams.)
- **§3 no other cross-run selection in Localization**: **CONFIRMED** —
  post-change grep shows the only remaining multi-run walk is
  `resolve_latest_analyzable_run` (`list_run_history`, derive.py), which
  is single-run head resolution ("which run to analyze"), not
  baseline/candidate pairing — engine-agnostic by the same rule as
  `resolve_latest_baseline`'s target selection. All three SBFL modes
  remain strictly single-run otherwise.

## Worklog entry text

(As committed in `a09208c`; see `WORKLOG.md` top entry
"2026-07-04 — anchored-pin-cycle / localization-team engine-scoped
regression-prior (D5 Finding B, wave 2)".)

## DoD bullets believed closed

None — no unchecked `- [ ]` bullet in
`design/implementation-plan/delivery-phasing.md` maps to this follow-up
slice (it closes D5 audit Finding B, routed via the 2026-07-03 question).

## Open items / surprises

- **Signature change is API-visible**: `try_get_latest_regression_facts`
  is exported from `novetest.localization.__all__`; second param is now
  `MemoryEntry`. Zero external callers today (grep: only
  `derive_localization_findings` + the package re-export). Flagging for
  the merge gate in case a parallel wave-2 slice grows a caller.
- **Host-toolchain drift**: `dotnet` is gone from this host's PATH since
  the 2026-07-03 sessions → 1 pre-existing integration failure + extra
  skips in full-suite counts. Reproduced on unmodified main; re-equip per
  `scripts/dev-host-setup.md` or rely on CI.
- **Karpathy-guidelines Skill**: no Skill tool in this session's toolset
  (third documented occurrence); principles applied manually — no
  deliverable impact.
- **Isolation-guard fallback**: comms-file writes in the shared checkout
  (this file, task status flip) used the GOTCHAS.md-sanctioned Bash
  heredoc/sed fallback after `Edit` was blocked by the worktree-isolation
  handshake — no deliverable impact.
- Specialist recruiting: slice executed directly (≈15 LOC production
  swap + one test file); briefing a subagent would have exceeded the work
  itself — judgment call per charter's "delegate the focused work" spirit.
