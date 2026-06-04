---
from: novetest-pm-team
to: novetest-run-team
type: task
created: 2026-06-04
slug: cargo-cli-orchestration-defect
status: blocked
blocked-by:
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
related:
  - agent-comms/findings/manual-test-team-2026-06-04-host-equip.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - design/implementation-plan/engine-adapters.md
---

# Cargo adapter — CLI orchestration path returns `adapter-unparseable-output` on the canonical fixture (P1) + build-failure heuristic misfires (P2)

## ⛔ DO NOT START UNTIL JUNIT HOTFIX CYCLE CLOSES

`status: blocked` is intentional. The JUnit hotfix
(`tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix.md`) is your
priority-1 work. When that ships and Manual Test re-passes JUnit, PM
will flip THIS brief to `status: pending` and the CEO will dispatch.
Until then, do not branch a worktree for this work.

## TL;DR

A polyglot-equipped Manual Test pass on 2026-06-04 (see
`findings/manual-test-team-2026-06-04-host-equip.md` §"Cargo adapter —
CLI vs adapter-direct discrepancy") surfaced a defect on the cargo
CLI orchestration path that was structurally invisible while the
verification host lacked Rust:

| # | Defect | Severity | Site |
|---|---|---|---|
| 1 | `novetest run .` against `cargo-test-basic` returns `adapter-unparseable-output` with stderr `Starting 0 tests across 2 binaries (3 tests skipped) ... error: no tests to run`. Direct `cargo nextest run` on the same fixture works fine (3 discovered, 2 pass, 1 fail). | P1 | target → nextest-filter plumbing |
| 2 | The build-failure heuristic at `cargo_adapter.py:344-348` emits the misleading text **"likely build failure"** when stderr actually shows `Finished test profile … target(s) in 0.17s` (compile succeeded). The heuristic's condition (`not saw_test_started and returncode != 0`) is satisfied by *any* exit-non-zero-without-events outcome, not just compile failures. | P2 | adapter heuristic |
| 3 | No CLI-level smoke under `tests/integration/run/test_cargo_*.py` — the existing two tests call `run_cargo()` directly with `target_expression=""`, bypassing the CLI orchestration → target_resolver → adapter path. Retroactive backfill required per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2. | Process | testing discipline |

These were unreachable until the 2026-05-29 cargo v1-exception's
trigger (b) fired (Rust toolchain installed on Manual Test host) on
2026-06-04. The host is now equipped — see findings file for full
posture — so the CLI orchestration path is finally exercisable end-to-
end. Defects 1 + 2 + the missing CLI smoke (3) get fixed together
in this slice.

**Estimated scope:** 1 short cycle (~½ day). Defect 1 has a clean
root cause analysis below; Defect 2 is a one-line carve-out; Defect
3 is the same CLI-smoke pattern Run team is adding in the JUnit
hotfix cycle (copy + adjust).

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-run-team.md` (your charter)
3. **`agent-comms/findings/manual-test-team-2026-06-04-host-equip.md`** §"Cargo adapter — CLI vs adapter-direct discrepancy" — the source defect report with exact stderr capture and reproducer
4. **`agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`** §2 — the CLI-level smoke template you must follow
5. `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md` — nextest-only contract; do not reintroduce plain-text fallback
6. `agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3 — closure triggers; this slice closes trigger (a) materially for the running-cargo CLI path even though the formal trigger is the CI matrix
7. `src/novetest/run/target_resolver.py` — the classifier producing `target_type="directory"` with `target_expression="."`
8. `src/novetest/run/adapters/cargo_adapter.py` lines 144-220 — argv composition where `target_expression` is appended verbatim as a nextest filter
9. `src/novetest/run/adapters/cargo_adapter.py` lines 320-348 — build-failure heuristic
10. `tests/integration/run/test_cargo_basic.py` + `test_cargo_coverage.py` — existing adapter-direct integration tests; add the CLI smoke parallel to these
11. `src/novetest/orchestration/workflows/run.py:85-88` — the same `.relative_to(store.path)` invariant the CLI smoke exercises (the cargo adapter happens to honor this already; the smoke verifies it stays that way)

---

## 1. Defect 1 root cause (binding analysis)

`src/novetest/run/target_resolver.py:10-46` classifies the user's positional
target expression as follows:

```python
def resolve_test_target(target_expression: str, workspace_context: Path) -> TestTarget:
    expression = target_expression.strip()
    if not expression:
        return TestTarget(target_expression="", target_type="workspace", ...)
    if "::" in expression:
        return TestTarget(target_expression=expression, target_type="nodeid", ...)
    candidate = workspace_context / expression
    if candidate.is_dir():
        return TestTarget(target_expression=expression, target_type="directory", ...)
    return TestTarget(target_expression=expression, target_type="file", ...)
```

For `novetest run .`:
- `expression = "."` — truthy, so empty-workspace branch is skipped
- `"::" in "."` is False, so nodeid branch is skipped
- `workspace_context / "."` IS a directory → `target_type="directory"` with
  `target_expression="."`

`src/novetest/run/adapters/cargo_adapter.py:158, 219-220`:
```python
target_expression = test_target.target_expression  # "."
...
if target_expression:  # truthy
    argv.append(target_expression)  # appends "."
```

The final invocation becomes `cargo nextest run --workspace --message-format=libtest-json .`. nextest interprets the positional argument as a **filter DSL expression**, not a filesystem path. The literal `.` is a valid filter token (it would match a test whose ID equals "."), and nextest finds no such test → "no tests to run", exit 4.

The integration tests pass because they call `run_cargo()` directly with `target_expression=""` (workspace path), so the `if target_expression:` branch is False and nothing is appended → nextest runs all tests in the workspace.

### Three viable fixes (Run team's call; recommend Fix A)

**Fix A (recommended) — adapter-side normalization.** In cargo_adapter.py, before appending the filter, normalize directory-type targets:
```python
if target_expression and test_target.target_type != "directory":
    argv.append(target_expression)
elif target_expression and test_target.target_type == "directory":
    # cargo nextest doesn't take filesystem-directory args as positional
    # filters. For directory targets, --workspace already covers the
    # workspace root; sub-crate directories would need translation to
    # cargo's -p/--package selector. v1: treat all directory targets
    # as workspace-equivalent (the user-facing `novetest run .` matches
    # the empty case). v2 may add per-crate plumbing.
    pass
```

Pros: contained to cargo_adapter, no cross-engine coupling, matches the "cargo nextest doesn't have a directory selector" reality.
Cons: cargo-test users who pass a sub-crate directory get workspace-wide execution (slightly broader than they asked for); document this in `engine-adapters.md §5`.

**Fix B — target_resolver-side carve-out.** Change `resolve_test_target` to return `target_type="workspace"` when expression resolves to the workspace root specifically. Pros: fixes the symptom at a single site for all adapters that might have the same issue. Cons: cross-cuts contract (pytest / jest / go-test already handle `.` as "current directory" via their own conventions); changing the workspace semantic affects all adapters, not just cargo.

**Fix C — translate to nextest's expression DSL.** Use nextest's `-E 'package(...)'` expression to select crates by directory. Pros: most accurate. Cons: requires nextest expression-DSL knowledge per crate path; brittle.

**PM recommendation: Fix A.** It's adapter-local, matches user expectation (`novetest run .` runs the whole workspace, same as `novetest run`), and defers the per-sub-crate complication to a future cycle if anyone actually requests it. Document the choice in `design/implementation-plan/engine-adapters.md §5` (cargo section) with a one-line note: "directory-typed targets currently resolve to workspace-wide execution; sub-crate selection is deferred until requested."

---

## 2. Defect 2 — build-failure heuristic carve-out

`cargo_adapter.py:328-348`:
```python
if not collect_coverage and not saw_test_started and result.returncode != 0:
    stderr_text = result.stderr.decode("utf-8", errors="replace")
    stdout_text = result.stdout.decode("utf-8", errors="replace")
    detail_source = stderr_text if stderr_text else stdout_text
    if _NEXTEST_LIBTEST_JSON_ENV_LITERAL in stderr_text:
        raise _libtest_json_env_misconfigured_error(...)
    raise AdapterInvocationError(
        f"cargo nextest exited {result.returncode} without starting any test "
        f"(likely build failure); stderr tail: {detail_source[-400:]}",
        kind="unparseable-output",
    )
```

Add a second carve-out symmetric to the env-var one: detect the
"no-tests-match" stderr signal and surface a distinct typed message.
The literal stderr substring is stable across nextest 0.9.50+:
`Starting 0 tests across` (the per-binary count line). Recommended
shape:

```python
_NEXTEST_NO_TESTS_LITERAL = "Starting 0 tests across"

if _NEXTEST_NO_TESTS_LITERAL in stderr_text and _NEXTEST_NO_TESTS_ERROR_LITERAL in stderr_text:
    # nextest exits 4 when its filter matches zero tests. This is NOT
    # a build failure — `Finished test profile … target(s)` appears in
    # the same stderr earlier in the run. Surface this as a distinct
    # typed error so users get accurate root-cause guidance.
    raise AdapterInvocationError(
        f"cargo nextest filter matched zero tests (target_expression="
        f"{test_target.target_expression!r}); did you mean to run the whole "
        f"workspace? stderr tail: {stderr_text[-400:]}",
        kind="unparseable-output",  # OR a new kind="no-tests-match"; Run team's call
    )
```

(Per `design/implementation-plan/engine-adapters.md §4.B`, adding a new
`AdapterInvocationError.kind` value is a model-shape question — file a
`questions/` entry if you want a new kind; otherwise keep
`unparseable-output` for v1 and document the disambiguation in the
message text.)

Once Fix A lands, the "no-tests-match" branch should rarely fire in
practice (the directory case is the main trigger). But the carve-out is
still valuable for users who supply explicit filter expressions that
happen to match zero tests — they currently get the misleading "likely
build failure" wording.

---

## 3. CLI-level smoke retrofit (per equip-and-exercise §2)

Add to `tests/integration/run/test_cargo_basic.py` (or a new
`test_cargo_cli_smoke.py` — your call):

```python
import shutil
import subprocess
import json
import pytest
from pathlib import Path

def test_cli_smoke_run_emits_envelope(cargo_workspace: Path) -> None:
    """End-to-end CLI smoke — exercises orchestration `.relative_to` invariant
    AND the target_resolver → cargo_adapter filter handling.

    Skip-gated on cargo + cargo-nextest presence so unequipped CI stays green;
    Manual Test's equipped host runs it.
    """
    if shutil.which("cargo") is None or shutil.which("cargo-nextest") is None:
        pytest.skip(
            "cargo + cargo-nextest required; install per scripts/dev-host-setup.md §4"
        )

    init = subprocess.run(
        ["uv", "run", "novetest", "init"],
        cwd=cargo_workspace, capture_output=True, text=True, timeout=60,
    )
    assert init.returncode == 0, init.stderr

    # The defect under fix: `.` positional reached the adapter as a nextest
    # filter and matched zero tests → `adapter-unparseable-output`. After
    # Fix A, this case must return a normal Run Record (exit 0 or 1).
    run = subprocess.run(
        ["uv", "run", "novetest", "run", "."],
        cwd=cargo_workspace, capture_output=True, text=True, timeout=300,
    )
    assert run.returncode in (0, 3), (
        f"unexpected cli-error: returncode={run.returncode} "
        f"stdout={run.stdout!r} stderr={run.stderr!r}"
    )
    envelope = json.loads(run.stdout)
    assert envelope["schema"] == "novetest/v1"
    if envelope["ok"]:
        assert envelope["data"]["run_record"]["engine_name"] == "cargo-test"

def test_cli_smoke_run_bare_emits_envelope(cargo_workspace: Path) -> None:
    """Same smoke without positional `.` — control case ensuring the no-arg
    path also stays green (this was the case `run_cargo()` integration tests
    already covered, but exercising via CLI verifies orchestration too)."""
    if shutil.which("cargo") is None or shutil.which("cargo-nextest") is None:
        pytest.skip("cargo + cargo-nextest required")
    subprocess.run(["uv", "run", "novetest", "init"], cwd=cargo_workspace, ...)
    run = subprocess.run(["uv", "run", "novetest", "run"], cwd=cargo_workspace, ...)
    assert run.returncode in (0, 3)
    envelope = json.loads(run.stdout)
    assert envelope["data"]["run_record"]["engine_name"] == "cargo-test"
```

Both smokes skip-gate on the toolchain. The first one (`run .`)
specifically pins the Defect-1 surface; the second (`run` bare) is the
control. Add both — they catch regressions on either path.

---

## 4. Files touched (estimated)

| File | Change |
|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | Fix A: directory-type carve-out before `argv.append(target_expression)`. Fix B: no-tests-match stderr-literal carve-out before the generic "likely build failure" branch. |
| `tests/integration/run/test_cargo_basic.py` (or `test_cargo_cli_smoke.py`) | Add two CLI-level smokes (positional `.`, bare invocation). |
| `tests/unit/run/adapters/test_cargo_adapter.py` | Unit-test the directory-type carve-out (verify `argv` does NOT contain `"."` when `target_type="directory"`); unit-test the no-tests-match heuristic carve-out (stubbed `run_subprocess` returning the literal stderr). |
| `design/implementation-plan/engine-adapters.md` §5 | One-line note: cargo's `target_type="directory"` resolves to workspace-wide execution; sub-crate selection deferred until requested. |
| `WORKLOG.md` | New entry per protocol. |

Likely diff scope: ~60-100 LOC adapter + ~80-150 LOC tests (mostly the
two CLI smokes which need fixture wiring similar to the existing cargo
integration test fixtures).

## 5. Out of scope (explicit)

- **Per-sub-crate `-p`/`--package` directory selector.** Document as
  deferred; do not implement in this slice.
- **A new `AdapterInvocationError.kind` value** (e.g. `"no-tests-match"`)
  — if you want it, file a `questions/` entry first and pause. v1
  recommended path: stay with `unparseable-output` and disambiguate via
  message text.
- **Refactor of `adapter-unparseable-output` umbrella.** History
  2026-06-04 §"Surprises" noted this kind is becoming overloaded
  (compile-failure / env-var / llvm-cov-missing / now no-tests-match).
  An umbrella split is a future `engine-adapters.md §4.B` revision; do
  NOT attempt it here.
- **Modifying `target_resolver.py`.** Fix A is adapter-local. If you
  want to touch the resolver (Fix B), file a `questions/` entry first
  — it's a cross-engine change.
- **Backfilling CLI smokes for pytest / jest / go-test** retroactively.
  The equip-and-exercise §2 binds *new* adapters; the existing three
  pre-date the policy. If you have spare cycles inside this slice you
  MAY add a CLI smoke for them too, but it's not required and not in
  the DoD.

## 6. Definition of Done bullets

Tick when ALL are true:

- [ ] `cargo_adapter.py` no longer appends a non-empty
      `target_expression` to nextest argv when `target_type ==
      "directory"`. Unit-tested.
- [ ] `cargo_adapter.py` build-failure heuristic detects the
      `"Starting 0 tests across"` stderr literal and emits a distinct
      message that does NOT include the words "likely build failure".
      Unit-tested with a stubbed `run_subprocess` returning the exact
      stderr Manual Test captured (see findings file).
- [ ] `tests/integration/run/test_cargo_*.py` includes at least one
      CLI-level smoke via `subprocess.run(["uv", "run", "novetest", "run",
      "."], …)` that asserts `returncode in (0, 3)` (per `EXIT_USER_TESTS_FAILED = 3` in `cli/output.py`; **NOT** `(0, 1)`) and envelope
      `engine_name == "cargo-test"`. Skip-gates on `shutil.which("cargo")`
      AND `shutil.which("cargo-nextest")` presence.
- [ ] A second CLI-level smoke covers the bare `novetest run`
      (no positional) case.
- [ ] `engine-adapters.md §5` carries a one-line note about
      directory-type targets resolving to workspace-wide cargo
      execution (sub-crate selection deferred).
- [ ] `uv run pytest -q tests/unit tests/integration` on equipped host:
      `9 passed, 0 failed, 2 skipped` (Gradle OR-clause skips remain;
      JUnit cases pass post-hotfix).
- [ ] `uv run mypy --strict` clean.
- [ ] Handoff includes a "before/after" capture of the CLI envelope
      for `novetest run .` on `cargo-test-basic` showing the
      `adapter-unparseable-output` is gone and a normal Run Record is
      emitted.

## 7. Re-verification (Manual Test will pass on equipped host)

After Main Branch FF-merges your handoff, Manual Test re-runs:

```sh
source ~/.local/share/novetest-toolchains.sh
cd tests/manual-test-workspace/cargo-cli-orchestration-defect-2026-XX-XX/cargo-sut

# Expected post-fix: kind=run-record, summary.{passed:2, failed:1}
uv run novetest run .

# Expected: same Run Record (control)
uv run novetest run

# Expected: still works (regression check)
uv run novetest run --coverage
```

The findings file's Evidence-B reproducer is the source of truth for
the failing baseline; the re-verification just asserts those exact
commands now succeed.

## 8. Handoff expectations

When you're ready to merge, write
`agent-comms/handoffs/run-team-2026-XX-XX-cargo-cli-orchestration-defect.md`
with:

1. **DoD bullets believed closed** — list each from §6 with a one-line
   evidence pointer (file path + test name).
2. **Before/after envelope capture** — paste the `novetest run .`
   envelope on `cargo-test-basic` showing
   `adapter-unparseable-output` is gone and a normal Run Record is
   emitted (the exact-text shape Manual Test will diff against).
3. **Fix-A vs Fix-B-vs-Fix-C choice** — declare which fix shape you
   took and why (one paragraph).
4. **Slice diff summary** — `git diff --stat`.
5. **Test counts post-fix** — pre-fix baseline 9-passed-1-failed-2-skipped
   on equipped host (the 1 failed = this defect); post-fix target
   10-passed-0-failed-2-skipped (the +1 is the new CLI smoke that now
   passes instead of being absent).

## 9. Sanity check before starting

If you find yourself wanting to:

- Modify `target_resolver.py` → STOP. Fix A is adapter-local; touching
  the resolver is Fix B and requires a `questions/` entry first.
- Add a new `AdapterInvocationError.kind` value → STOP. v1 stays with
  `unparseable-output`; disambiguate via message text. File a
  `questions/` entry if you want the new kind.
- Backfill CLI smokes for pytest / jest / go-test → optional; not
  required. Treat as extra credit if you have cycles.
- Skip the unit-test for the no-tests-match carve-out — "the
  integration test covers it" → STOP. The stubbed-subprocess unit test
  pins the literal stderr substring; future nextest version changes
  could break the literal and we need the unit gate to catch it.
- Touch the JUnit adapter — STOP. JUnit hotfix is a separate Run-team
  cycle; respect the worktree isolation.

Otherwise: branch a worktree off the post-JUnit-hotfix tip (PM will
flip this brief to `pending` and dispatch when the tip is right),
exercise Fix A first, then Fix B, then add the two CLI smokes. The
fixture `tests/fixtures/projects/cargo-test-basic/` already exists
(see Run team's 2026-05-29 work); reuse it for the smoke tests.
