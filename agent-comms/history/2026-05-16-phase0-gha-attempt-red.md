---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-16
slug: phase0-gha-attempt-red
---

# History: Phase 0 GHA observation attempt — RED, two root causes diagnosed

Single-deliverable cycle: Release team performed the live-GHA observation
pass to close Phase 0 DoD #1, #2, #3. Both workflows came back RED.
Release team's handoff carried a precise root-cause diagnosis for each
failure, scoped to two different teams. No DoD ticked; follow-up
slices dispatched in the next cycle.

## Cycle summary

| Workflow | Run | Verdict |
|---|---|---|
| `ci.yml` on `017eb04` | `25926569296` | 6/9 cells FAIL (all macOS + Windows), 3/9 PASS (all Ubuntu); same single test fails on every red cell. Same red pattern observed on the prior CI run `25905297606` (`3e06be0`) — steady-state RED, not a flake. |
| `release-test.yml` on `017eb04` (workflow_dispatch) | `25954755663` | 4/4 PyApp build jobs FAIL at "Wrap wheel with PyApp" step. `install-script-e2e` job auto-SKIPPED (depends on `build`). |

## Two root causes — sharply isolated, different team ownership

### 1. `tests/unit/run/adapters/test_pytest_adapter.py::test_pytest_unavailable_raises_typed_error` hardcodes `/bin/false` (Run team)

```python
# tests/unit/run/adapters/test_pytest_adapter.py:87
monkeypatch.setattr(adapter.sys, "executable", "/bin/false")
```

`/bin/false` is Linux-only. macOS ships it at `/usr/bin/false`; Windows
has no `false` binary. The test was Linux-developed and committed
without a CI verification pass on the other matrix cells (because no
CI matrix run was previously observed). 6 of 9 cells fail
deterministically; Ubuntu cells pass.

Owned by Run team. Fixed by the follow-up task at
`tasks/run-team-2026-05-16-pytest-adapter-bin-false-portable.md`.

### 2. `release-test.yml` "Wrap wheel with PyApp" uses a relative path that gets invalidated by a subsequent `cd` (Release team)

```yaml
# .github/workflows/release-test.yml lines 109–127
wheel="$(ls dist/novetest-*-py3-none-any.whl | head -n1)"   # ← relative
export PYAPP_PROJECT_PATH="$wheel"
cd pyapp-src                                                # ← invalidates `dist/...`
cargo build --release                                       # PyApp's build.rs looks for `dist/...` from inside pyapp-src/
```

Fails at `pyapp v0.22.0`'s `build.rs:434:13` with
`Project path is not a file: dist/novetest-0.0.0-py3-none-any.whl`.
All 4 PyApp build targets fail identically. `install-script-e2e` job
auto-skips via `needs: build`.

Owned by Release team (own workflow YAML). Fixed by the follow-up task
at `tasks/release-team-2026-05-16-release-test-pyapp-wrap-path.md`.

## DoD bullets attempted vs result

| DoD bullet (Phase 0) | Attempted | Result |
|---|---|---|
| #1 9-cell CI matrix green | yes | FAIL — needs Run team fix |
| #2 Signed binary builds on release-test | yes | FAIL — needs Release team workflow fix |
| #3 curl-pipe-sh end-to-end | yes | SKIPPED — depends on #2 fix |

All three remain `- [ ]` unticked in `delivery-phasing.md`.

## Load-bearing learnings

### 1. Local YAML parsing is not a substitute for GHA execution

Release team's prior slice (`74a6ce4`, last cycle) shipped both
workflows after verifying that `yaml.safe_load` parsed them cleanly.
Neither the 9-cell matrix nor the PyApp wrap was ever executed on
real GHA before this observation cycle. Both bugs are the kind that
only surface at execution time — `/bin/false` portability requires
a non-Linux runner; the PyApp `cd`-invalidates-relative-path bug
requires the actual `pyapp v0.22.0` `build.rs` to run.

**Principle for any future CI/release workflow author:** observation
of the live workflow on the live target is the only valid
verification. Local YAML parsing + local logic tests prove the script
parses; they do not prove the workflow runs.

### 2. GHA run-level `cancelled` masks individual job failures

`ci.yml` run `25926569296` was force-cancelled by concurrency policy
when the next push landed. Run-level conclusion: `cancelled`. But 8
of 9 cells had already completed with their own conclusions and
retained them (the only true `cancelled` cell was windows/py3.13).

**Principle for future GHA observation passes:** treat per-job
conclusions as ground truth; run-level conclusion can be misleading
when concurrency cancellation is in play. The query is
`gh run view <id> --json jobs` not `--json conclusion`.

### 3. PyApp 0.22.0 cargo wrap iteration cost (~60s/target)

A quick PyApp build-script failure still pays the full Rust compile
cost (~60s per target on Linux runners). If the Release-team
follow-up requires more than one workflow-fix iteration,
`actions/cache` on `~/.cargo` + `pyapp-src/target/` is worth adding
to shorten the cycle. Flagged for the follow-up Release task as an
optional optimization.

### 4. Observation tasks have an asymmetric "success" definition

Release team's task spec explicitly permitted
`status: blocked / verdict: failed` as a valid outcome — the mission
was *observe and report*, not *cause green*. The team produced a
sharp, sourced, root-cause-isolated handoff that points to two
distinct fixes in two distinct teams' territories. From the
delivery-process perspective, this cycle was a clean success: the
observation pass executed cleanly, the report is actionable, no PM
ambiguity remains. From the DoD-progress perspective, the cycle was
a deliberate "diagnose before acting" step — and it found two real
bugs that would have blocked Phase 0 closure indefinitely if not
caught.

## Process notes

- **No code committed, no `WORKLOG.md` entry.** Observation-only task
  per spec; the `check-worklog-before-commit.sh` hook does not apply.
  Cycle artifacts are entirely in `agent-comms/`.
- **Two follow-up tasks dispatched in the next cycle.** Run team's
  fix and Release team's fix are independent (different files,
  different code areas) and can run in parallel. Release's fix is
  inherently serial with its own observation re-pass (fix → re-trigger
  release-test.yml → observe green). Run's fix is closed by the next
  scheduled CI run after merge — no manual re-trigger needed.
- **`history/2026-05-16-coverage-cli-wiring.md` (the prior cycle's
  history) said "Release GHA observation cycle still in flight".**
  That was true at the moment of writing; this cycle closed shortly
  after. The prior entry stays as-is; this entry continues the
  narrative.

## Follow-ups (next cycle dispatched)

1. **`tasks/run-team-2026-05-16-pytest-adapter-bin-false-portable.md`** —
   make `test_pytest_unavailable_raises_typed_error` cross-platform.
   Closes Phase 0 DoD #1 once the next post-merge CI run shows 9 green
   cells.
2. **`tasks/release-team-2026-05-16-release-test-pyapp-wrap-path.md`** —
   fix the relative-path bug in `release-test.yml` Wrap-wheel step;
   re-trigger; observe. Closes Phase 0 DoD #2 and #3 in one task.

## References

Transient comms files (Release task + RED handoff) deleted in the same
commit as this entry. No `verifications/`, `findings/` files — this is
an observation-only flow.

Permanent items touched or created this cycle: none. (Two new tasks
created in the *next* cycle's dispatch commit; they reference this
history entry.)
