---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-07-04
slug: anchored-init-and-verb-resolution
related:
  - agent-comms/handoffs/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Verification: anchored init + verb walk-up + pin dispatch (D1–D7 — Wave 2, 3/3)

## Merged commit

- **`76a4ffb`** `orchestration: anchored init + verb walk-up resolution + pin dispatch (D1-D7)`
  (rebase of worktree commit `c6e51ae` off `7c6ece6` onto `4818642`; ONE conflict — `WORKLOG.md`, resolved incoming-on-top — zero source conflicts)
- This commit IS the Wave-2 cohort tip.

## Source handoff

- `agent-comms/handoffs/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md`

## Merge gate (tip `76a4ffb`, equipped host)

- pytest full suite → **1511 passed / 5 skipped / 0 failed**, 49 snapshots
- mypy → **Success, 116 source files**

## Empirical envelope anchors (dry-run at merged tip — ALL observed, not templated)

**A. Single-marker init (pytest-basic fixture copy) — exit 0:**
```
data.pinned_engine: {"ecosystem": "python", "engine_name": "pytest"}
```
`novetest status` in the same workspace — exit 0, identical
`data.pinned_engine` value.

**B. Markerless dir with one child candidate (`childpy/pyproject.toml`) — exit 4:**
```
ok: false
errors[0].code: "no-engine-detected"
errors[0].message: "No supported engine marker found at <dir>; no Project
  Store was created. Note: candidate projects were discovered below
  (data.candidates); cd into the one you want and run `novetest init`
  there — novetest never initializes a directory you are not standing in."
data: {"candidates": [{"ecosystem": "python", "engine_name": "pytest", "path": "childpy"}], "scan_refused": false}
```
Observed: NOTHING created (`ls -a` shows no `.novetest/`). Candidate
`path` is POSIX-form relative.

**C. Dual marker (`pyproject.toml` + `go.mod`, both READY) — exit 2:**
```
ok: false
errors[0].code: "engine-ambiguous"
errors[0].message: "Multiple viable engines detected (pytest, go-test); no
  Project Store was created. Choose one explicitly: `novetest init --engine <name>`."
data: {"candidates": [{"ecosystem": "python", "engine_name": "pytest", "path": "."}, {"ecosystem": "go", "engine_name": "go-test", "path": "."}]}
```
Follow-up `novetest init --engine pytest` in the same dir — exit 0,
`data.pinned_engine: {"ecosystem": "python", "engine_name": "pytest"}`.

Envelope error codes live at **`errors[0].code`** (array), NOT a scalar
`error` field. `data.scan_refused` appears in the no-engine-detected case
only.

## Verification steps for Manual Test

1. **Reproduce anchors A–C above** (fixture copies under /tmp; commands
   are copy-paste from the anchors — `$REPO/.venv/bin/python -m novetest …`).
2. **D2 walk-up**: init at a fixture root, `cd` into a nested subdir, run
   `novetest status` / `novetest test` — must resolve the parent store
   (git-style upward walk); `novetest run` from OUTSIDE any store →
   `uninitialized` (exit 2, existing code).
3. **D3 target semantics**: from a nested subdir, bare `novetest test` →
   workspace-scoped (`target_expression == ""` in the run record);
   explicit relative target from the subdir → normalized anchor-relative
   POSIX form (same baseline series as the same ask from the root).
4. **D3 transient override**: `novetest test --engine <other>` /
   `run --engine` executes one-off WITHOUT re-pinning (`status` afterwards
   still shows the original pin). Invalid `--engine foo` → `invalid-flag`,
   exit 2.
5. **D6 lazy migration**: strip the pin field from an existing
   `store.json` → next `novetest status` silently backfills it
   (single-marker anchor), envelope otherwise unchanged.
6. **Reset semantics (in-scope extra, flagged in handoff)**: `novetest
   reset` from a nested subdir re-inits at the store's ANCHOR (not cwd)
   and carries the pin across the wipe. On a legacy pin-less store at an
   ambiguous/markerless anchor: refuses BEFORE wiping ("the store was NOT
   wiped" guidance) — store must remain intact.
7. **E2E suite**: `env -u PYTHONPATH uv run pytest -q
   tests/integration/test_anchored_pin_e2e.py` → 6 passed (real
   subprocesses; dual-marker → ambiguous → `init --engine` → nested-subdir
   walk-up → baseline series separation).

## Critical edge cases worth probing

- **Re-pin in place**: `init --engine <other>` on an initialized store —
  run history retained, pin updated, NO second `.novetest/`.
- **D4 discovery bounds**: candidates only from depth ≤2, no symlink
  descent; `init` in `$HOME` or `/` → `scan_refused: true` path.
- **Markerless + 0 candidates**: `data.candidates: []`,
  `scan_refused: false` — message should still be actionable.
- **≥2 markers with 0 READY** → `engine-ambiguous` (not
  no-engine-detected) per D1 table.
- **`reset` success envelope**: deliberately does NOT surface
  `pinned_engine` (kept byte-stable; PM follow-up candidate — flag if this
  confuses agent consumers in practice).

## Notes from merge / for PM routing

- Orchestration handoff flags for PM ratification: exit-code mapping
  (`no-engine-detected` → 4, `engine-ambiguous` → 2) and reset-envelope
  pin parity — both listed under handoff §"Notifications".
- Run team unblock: no `execute(engine=None)` caller remains in
  orchestration; their `run/engine.py` legacy auto-detect TODO can drop.
- User-doc drift: `design/user-doc/**` "You do not pass an `--engine`
  flag" claims are now false; behavioral change — `init` on a markerless
  directory now FAILS (used to create a store). PM doc pass required.
- CI matrix cite: post-merge `gh workflow run ci.yml --ref main` (session
  gh identity dispatch-restricted).

## ADDENDUM 2026-07-04 — post-merge CI verdict

CI at `7ddfc0f` (run 28671731628): **7/10** — 3 windows jobs red on ONE
test: `test_anchor_resolution.py::test_normalize_engine_native_pattern_passes_through`
(`./...` mangled to `...` via the Win32 trailing-dot `.exists()` quirk).
Triage + kick-back:
`questions/main-branch-team-2026-07-04-windows-dotdotdot-normalization-ci-red.md`.
Treat `./...` pass-through scenarios as KNOWN-RED on Windows until the
fast-follow lands; all other scenarios in this doc are CI-green on 7/7
POSIX legs + perf.
