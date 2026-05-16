---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-16
slug: pytest-adapter-bin-false-portable
related:
  - history/2026-05-16-phase0-gha-attempt-red.md
---

# Task: Make `test_pytest_unavailable_raises_typed_error` cross-platform

## Scope / Mission

The unit test
`tests/unit/run/adapters/test_pytest_adapter.py::test_pytest_unavailable_raises_typed_error`
hardcodes `/bin/false` as a stand-in for "an executable that exists but
cannot run `-m pytest`". `/bin/false` is **Linux-only** — macOS ships
it at `/usr/bin/false`, Windows has no `false` binary at all. This
causes deterministic CI failures on 6 of 9 matrix cells (all macOS +
Windows × Python 3.11/3.12/3.13). Ubuntu cells pass.

This is one of two RED root causes blocking Phase 0 closure (see
`agent-comms/history/2026-05-16-phase0-gha-attempt-red.md`). Your job
is to make the test cross-platform-safe while preserving its original
intent.

Closes Phase 0 DoD #1 (9-cell CI matrix green) once the next CI run
on the merged fix shows all cells green. (PM tracks the post-merge
observation separately.)

## Current test body (for context)

```python
# tests/unit/run/adapters/test_pytest_adapter.py:80-91
async def test_pytest_unavailable_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point sys.executable at a binary that cannot run ``-m pytest``."""

    import novetest.run.adapters.pytest_adapter as adapter

    monkeypatch.setattr(adapter.sys, "executable", "/bin/false")
    target = resolve_test_target("", tmp_path)
    with pytest.raises(AdapterInvocationError):
        await run_pytest(target, artifact_dir=tmp_path, timeout=30.0)
```

**Original intent:** point `sys.executable` at a binary that exists,
executes successfully (i.e. spawns), but **fails to run `-m pytest`**
(exits non-zero without producing a JSON report). The adapter must
wrap that failure in `AdapterInvocationError`. The test does NOT care
about FileNotFoundError-on-spawn — that is a different code path.

Keep this intent. Don't substitute a non-existent path: that exercises
spawn-fail semantics, not "exec succeeded but pytest invocation
failed".

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/history/2026-05-16-phase0-gha-attempt-red.md` —
   full context on why this test is RED in CI
4. `agent-comms/tasks/run-team-2026-05-16-pytest-adapter-bin-false-portable.md`
   (this file)
5. `WORKLOG.md` top 3 entries
6. `src/novetest/run/adapters/pytest_adapter.py` — read-only;
   understand the adapter's failure-handling code path so your fix
   exercises the same code that `/bin/false` exercises today (subprocess
   exits non-zero, JSON report absent → adapter wraps in typed error)
7. `tests/unit/run/adapters/test_pytest_adapter.py` — the file you'll
   modify; pay particular attention to the conftest fixtures you can
   reuse

## Implementation options (you pick — document the choice in the handoff)

### Option A (recommended) — `tmp_path`-rooted fake executable

Create an executable file under `tmp_path` that always exits non-zero
regardless of args. Point `sys.executable` at it.

POSIX:
```python
fake = tmp_path / "always_fail"
fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
fake.chmod(0o755)
```

Windows: write a `.bat` (or `.cmd`) with `@echo off\nexit /b 1` and
point `sys.executable` at that.

Branch on `sys.platform` once at the top of the test. ~10 lines.
Pros: faithful to original intent (exec succeeds, `-m pytest` fails),
no plat-conditional skip, no dependency on system binaries that may
move between OS versions.

### Option B — `shutil.which` + `pytest.skip` on Windows

```python
import shutil
false_path = shutil.which("false")
if false_path is None:
    pytest.skip("requires a POSIX `false` binary")
monkeypatch.setattr(adapter.sys, "executable", false_path)
```

Pros: 5-line fix. Cons: skips the test on Windows entirely — loses
coverage on 1/3 of the matrix.

### Option C — extend the adapter's seam so the test doesn't need a
real executable

(Out of scope unless you find a clean seam — adapter code is yours
to evaluate.) If the adapter already has an injection point that
lets you simulate "subprocess exited non-zero without producing JSON
report" via a higher-level mock, this becomes a small mock
substitution. If no such seam exists, do NOT add one for this
test — Option A is the right shape.

**PM recommendation: Option A.** Preserves original intent, full
matrix coverage, no system-binary dependency, ~10 LOC. Document the
choice + rationale in the handoff regardless.

## Files to write / modify

- `tests/unit/run/adapters/test_pytest_adapter.py` — replace the
  body of `test_pytest_unavailable_raises_typed_error` per your
  chosen option. No other test bodies should change.

## Files NOT to touch

- `src/novetest/run/adapters/pytest_adapter.py` — adapter code is
  out of scope unless Option C explicitly requires it (and even then,
  please add a `questions/` file first to confirm scope).
- Any other unit / integration test file.
- `tests/fixtures/projects/**`.
- `pyproject.toml`.
- `.github/workflows/**` — separate Release task handles the
  release-test.yml fix in parallel.
- `agent-comms/decisions/**`, `history/**` — PM only.

## Verification commands

```sh
# Confirm the targeted test passes locally
uv run pytest -q tests/unit/run/adapters/test_pytest_adapter.py::test_pytest_unavailable_raises_typed_error

# Full unit + integration suite — baseline 267 passed
uv run pytest -q tests/unit tests/integration

# mypy --strict
uv run mypy
```

On a Linux dev box you cannot lock in macOS/Windows behavior; CI does
that after merge. Document in the handoff that the local pass is
necessary-but-not-sufficient and PM will track the post-merge CI
observation for the 9-cell green confirmation.

## DoD bullets you should claim closed

In your handoff's "DoD bullets believed closed" list, name:

- **Phase 0, bullet #1** — "`uv run pytest -q` green on all three
  OSes and three Python versions."

  Caveat for PM: this slice closes the test-side bug. Actual DoD
  tick is gated on PM observing the next CI run (post-merge) showing
  all 9 cells green. PM owns the observation pass.

## Reporting (handoff)

Write `agent-comms/handoffs/run-team-2026-05-16-pytest-adapter-bin-false-portable.md`
with the standard handoff body sections:

- Worktree path + branch + base commit.
- Files written/modified (final list).
- Chosen option (A / B / C) + 1-line rationale.
- pytest counts (new total — should stay 267 unless your fix happens
  to land an additional case) + mypy result.
- WORKLOG entry text (paste the entry you appended).
- DoD bullets believed closed (see above).
- Open items / surprises.

Append your WORKLOG entry per `WORKLOG.md`'s format. Run
`python3 tools/regen_comms_index.py` after writing the handoff.
Stage WORKLOG + handoff + INDEX alongside source per post-flight
protocol.

## Out of scope (do NOT do these in this task)

- Fix the Release `release-test.yml` PyApp wrap path bug — separate
  Release task in this same cycle.
- Modify other failing tests (none exist beyond this one — all 257
  other tests pass on every OS).
- Add new cross-platform-testing infrastructure (no `tox`, no
  `nox`, no platform-conditional pytest plugins). Surgical fix only.
- Hardware-detection or CI-detection logic. Test must work both
  locally and in CI without env-var branching.

## Why this task exists

The Phase 0 release-tooling slice (`74a6ce4`) shipped both workflows
without ever observing a real GHA CI matrix run. The Linux-local dev
loop never exposed this `/bin/false` portability assumption. CI run
`25926569296` made it visible. This task closes the bug at the source.
Once merged, the next scheduled CI run should show all 9 cells green
for the first time and PM ticks DoD #1.
