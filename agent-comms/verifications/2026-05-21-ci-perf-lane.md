---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-05-21
slug: ci-perf-lane
source-handoffs:
  - handoffs/release-team-2026-05-21-ci-perf-lane.md
---

# Verification: non-blocking `tests/perf` CI lane + install-script encoding hardening

## Merged commit

- `12cf04d` — `ci: add non-blocking tests/perf lane + harden install-script test encoding`
- Merged fast-forward onto `main` (was `c598eb3`). No conflict.

## Source handoff consumed

- `handoffs/release-team-2026-05-21-ci-perf-lane.md` (Release team, status
  `ready-to-merge`). This is the re-dispatch of the deferred Slice B from
  the earlier ci-maintenance task.

## What changed

- `.github/workflows/ci.yml` — Slice A: a new top-level `perf` job
  (`ubuntu-latest`, Python 3.13, `continue-on-error: true`) running
  `uv run pytest tests/perf`. NOT a cell of the existing 9-cell `test`
  matrix — a separate job.
- `tests/release/test_install_script.py` — Slice B: one `encoding="utf-8"`
  kwarg added to the install-script `subprocess.run(...)` call (the same
  latent `text=True`-without-`encoding=` pattern fixed in the CLI conftests
  this cycle). Pre-emptive hardening — `tests/release/` runs only on POSIX
  CI cells today.
- `WORKLOG.md` — entry appended (Slice B touches `tests/release/`).

No `src/`, no `pyproject.toml`, no `tests/perf/**` edit.

## Verification steps for Manual Test

1. CI workflow parses and the `perf` job is non-blocking:
   ```
   python3 -c "import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); print(list(d['jobs'].keys()), d['jobs']['perf'].get('continue-on-error'))"
   ```
   Expect: `['test', 'perf'] True`.

2. The exact command the new lane runs:
   ```
   uv run pytest tests/perf -q
   ```
   Expect: `3 passed` (observed `median=0.023s` at merge).

3. Install-script test still green after the encoding kwarg (POSIX):
   ```
   uv run pytest -q tests/release
   ```
   Expect: `3 passed` — the change is behaviour-preserving on a POSIX host.

4. Default gate unchanged:
   ```
   uv run pytest -q tests/unit tests/integration
   ```
   Expect: `337 passed, 3 skipped` — `tests/perf` still not collected by
   the default run.

5. **Definitive signal — post-merge GHA CI run:** the `perf` job appears,
   runs, and is non-blocking — even if the benchmark exceeds budget the
   workflow run conclusion stays `success`. The 9-cell `test` job is
   unchanged.

## Critical edge cases worth probing

- **Non-blocking is the headline requirement.** Two independent
  guarantees: (a) `perf` is a brand-new separate job, never auto-added to
  branch-protection required checks; (b) `continue-on-error: true` keeps
  the workflow run `success` even on perf failure. A slow run on a noisy
  shared runner must never gate a PR merge — confirm this holds if the
  perf job ever reports a failed step.
- The `perf` job has no `setup-node` step — the benchmark is pure-Python,
  so that is deliberate, not an omission.
- Slice B is pre-emptive: `tests/release/` is POSIX-only CI today, so the
  encoding fix has no observable behaviour change now — it forecloses the
  same Windows `charmap` failure mode if a Windows release cell is ever
  added.

## Notes from the merge

- Clean fast-forward, no conflict.
- No `delivery-phasing.md` DoD bullet closes — Slice A is CI tooling,
  Slice B is hardening. Phase 2 DoD #4 was already closed by `5489c7e`.
