---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: pytest-adapter-bin-false-portable
related:
  - handoffs/run-team-2026-05-16-pytest-adapter-bin-false-portable.md
  - tasks/run-team-2026-05-16-pytest-adapter-bin-false-portable.md
  - history/2026-05-16-phase0-gha-attempt-red.md
---

# Verification request: pytest adapter "unavailable" test cross-platform fix

## Merged commit

- **Hash:** `fc79209` (fast-forward from `1fddb94`; clean linear history, no merge commit).
- **Title:** `test(run): make pytest-unavailable test cross-platform (Option A)`
- **Scope:** Pure test-side change. `tests/unit/run/adapters/test_pytest_adapter.py::test_pytest_unavailable_raises_typed_error` no longer hardcodes `/bin/false` (Linux-only path). It now writes a `tmp_path`-rooted always-fail script — POSIX (`#!/bin/sh\nexit 1\n`, chmod 0o755) or Windows (`@echo off\r\nexit /b 1\r\n` as `.bat`) branched on `sys.platform` — and monkeypatches `adapter.sys.executable` at it. Spawn-succeeds-but-exit-nonzero semantics preserved verbatim. New imports: top-of-file `import sys`. **Adapter source untouched.**
- **No production code change. No CLI surface change. No envelope change. No dep change.**

## Source handoffs consumed

- `agent-comms/handoffs/run-team-2026-05-16-pytest-adapter-bin-false-portable.md` — single handoff, single commit.

## Merge notes

- **No conflicts.** Base commit (`1fddb94`) matched current main HEAD exactly; clean fast-forward.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration` → **267 passed** (unchanged baseline — this is a test substitution, not an addition), `uv run mypy --strict` → **clean** (49 source files).
- **Diff inspected before merge.** Confirmed surgical: only the targeted test body + one `import sys` + WORKLOG + handoff. Adapter source (`src/novetest/run/adapters/pytest_adapter.py`) byte-equivalent to pre-slice.
- **Unblocks Release team.** The parallel Release-team slice (`worktree-release-test-pyapp-wrap-path`, commit `4793eab`) was waiting on this merge before writing their handoff. Release can now proceed.

## What Manual Test can verify (limited scope, by slice nature)

This slice has **zero user-facing impact**. The CLI is byte-equivalent. The fix is a CI portability adjustment — making one test pass on macOS and Windows CI cells in addition to Linux. The authoritative verification gate is **PM's post-merge CI matrix observation** (the 9-cell green check that closes Phase 0 DoD #1), not Manual Test's E2E exploration.

Manual Test's spot-checks below are confidence checks on the local-Linux POSIX branch only. Do **not** spend more than ~10 minutes here.

### Spot-check 1 — Target test passes in isolation

```sh
cd /home/yjshin/dev/Nove-Test
uv run pytest -q tests/unit/run/adapters/test_pytest_adapter.py::test_pytest_unavailable_raises_typed_error
```

Assert: `1 passed`. The test creates a `tmp_path/always_fail` script, makes it executable, and points `adapter.sys.executable` at it; the adapter spawns it as `<script> -m pytest ...`, the script exits 1, the adapter sees no JSON report on disk and raises `AdapterInvocationError`.

### Spot-check 2 — Full suite unchanged

```sh
uv run pytest -q tests/unit tests/integration
```

Assert: `267 passed`. Same count as pre-merge baseline (no new cases — this is a substitution).

### Spot-check 3 — Eyeball the test body for the platform branch

Open `tests/unit/run/adapters/test_pytest_adapter.py`. In `test_pytest_unavailable_raises_typed_error`, confirm:
- Top-of-file `import sys` is present.
- Body has a `if sys.platform == "win32"` branch that writes `always_fail.bat` with `@echo off\r\nexit /b 1\r\n`.
- `else` branch writes `always_fail` (no extension) with `#!/bin/sh\nexit 1\n` and `fake.chmod(0o755)`.
- `monkeypatch.setattr(adapter.sys, "executable", str(fake))` — same seam as before, just pointing at the new path.

This is a literal sanity read, not a logic exercise.

## Critical edge cases worth probing

1. **Windows-only verification is out of Manual Test's reach in this cycle.** The Windows `.bat` branch is type-checked by mypy but only actually runs on Windows CI cells. If Manual Test runs on a non-Windows host (likely), the Windows branch is invisible. Do not attempt to fake it locally — PM owns the post-merge CI matrix observation that will exercise it.
2. **macOS branch is also CI-gated.** Same story — POSIX branch covers macOS in principle (`#!/bin/sh` is portable), but the actual macOS CI cell observation is PM's domain.
3. **No regression risk on existing CLI scenarios.** Because the adapter source is untouched, none of the previous slice's verification scenarios (coverage-cli-wiring, etc.) need re-running. The user-visible behavior of `novetest init` / `run` / `memory show` is byte-equivalent to commit `1fddb94`.

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-pytest-adapter-bin-false-portable.md` with:
- **Verdict:** likely `passed` if both spot-checks succeed; `failed` only if the specific test or full suite fails on your local POSIX host.
- **What was tested:** brief narrative of the two `pytest -q` invocations and the eyeball read.
- **Issues found:** unlikely; flag any unexpected output.
- **Recommendations for PM:** none expected from this slice — PM already owns the authoritative CI matrix observation that closes Phase 0 DoD #1. If you noticed anything during the eyeball read that suggests the Windows branch may not actually do what it claims, flag it for PM.

Keep findings short. This is a minor CI fix, not a feature slice.
