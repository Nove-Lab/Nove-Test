---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
slug: cargo-nextest-env-var-hotfix
created: 2026-05-31
related:
  - agent-comms/handoffs/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - agent-comms/findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
---

# Verification: cargo adapter hotfix — `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`

## Merged commit

`1e736cc` — `fix(run): set NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 in cargo adapter env`

Fast-forward merge from `worktree-run-team-cargo-nextest-env-var-hotfix`
onto main tip `e90f61e`. Worktree was based exactly at the current main
tip — **zero conflicts**, single linear commit ahead.

## Source handoff consumed

- `agent-comms/handoffs/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`
  (run-team, 2026-05-31).

## Scope of the slice

Closes **Issue 1** from `findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md`:
every `novetest run` against a real Rust workspace on an equipped host
was returning exit `4` with empty `data` and the runtime error
`adapter-unparseable-output`. Root cause: `cargo-nextest >= 0.9.50`
(our supported floor per `decisions/2026-05-25-supported-engine-matrix.md`)
gates `--message-format=libtest-json` behind the env var
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`. The cargo adapter was passing
the flag but not setting the env var, so nextest exited `95` with a
runtime error and wrote **zero** parseable events; the build-failure
heuristic at `cargo_adapter.py:263` then misclassified that as
`adapter-unparseable-output`.

The fix is a **two-line source change** inside `_build_child_env()`:

```python
# src/novetest/run/adapters/cargo_adapter.py:380-385  (verbatim)
env = os.environ.copy()
env["CARGO_TERM_COLOR"] = "never"
env["RUST_BACKTRACE"] = "1"
env["NO_COLOR"] = "1"
env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"   # ← NEW
return env
```

Plus one unit test pinning all four env vars
(`test_build_child_env_pins_nextest_libtest_json_gate` at
`tests/unit/run/adapters/test_cargo_adapter.py:885-906`) and a docstring
bullet on `_build_child_env()` documenting the nextest-floor rationale
and the consequence-of-omission chain
(`cargo_adapter.py:365-371`).

Nothing else touched. `cargo_adapter.py:263` build-failure heuristic
(separate low-priority polish), `normalizer.py`'s typed metadata slot
(Issue 2 — separate slice per
`decisions/2026-05-30-native-result-metadata-slot.md`), and the
Coverage-team LCOV-dispatch carry-forward are all out of scope.

## Test-gate result on the merged tip

I ran the gate on this equipped dev box (cargo-nextest 0.9.137, cargo
1.96.0, cargo-llvm-cov 0.8.7). Both gates green:

```
uv run pytest -q tests/unit tests/integration → 678 passed, 5 skipped
uv run mypy                                    → Success: no issues found in 70 source files (strict)
```

Comparison to baseline `e90f61e` (the pre-merge tip):

| | passed | skipped | net | reason |
|---|---|---|---|---|
| Baseline `e90f61e` (claimed) | 675 | 7 | 682 | env-dependent jest + cargo paths skipped |
| Handoff full-suite claim | 676 | 7 | 683 | +1 new test |
| **My gate on merged tip** | **678** | **5** | **683** | +1 new unit test, +2 cargo integration tests **RAN** (no longer skipped on equipped host) |

The 5 remaining skips are pre-existing Node / jest integration tests
that require `npm`. Both cargo integration tests
(`tests/integration/run/test_cargo_basic.py` and
`tests/integration/run/test_cargo_coverage.py`) **ran and passed**
on this host — `2 passed in 0.57s` in isolation post-merge.

The +2 passed / −2 skipped vs the handoff's headline number is the
natural consequence of running on a Rust-equipped host (the handoff
appears to have used a slightly different selection or the integration
collection skipped 2 cases that mine ran — either way the actual count
is BETTER than claimed: more tests passing, fewer skipped).

## Wire shapes pinned by running the merged code on a real cargo fixture

I exercised the merged binary against both cargo fixtures end-to-end
on this equipped host. Below is the **actual observed envelope**
post-fix, copy-paste-ready into Manual Test scenarios.

### Setup (run once)

```bash
. "$HOME/.cargo/env"  # ensure cargo + nextest on PATH

WORKSPACE=$(mktemp -d -t novetest-cargo-verify-XXXX)
cp -r tests/fixtures/projects/cargo-test-basic "$WORKSPACE/"
cd "$WORKSPACE/cargo-test-basic"
uv run --project /home/yjshin/dev/Nove-Test novetest init
```

`novetest init` envelope (`ok: true`, exit `0`) — verbatim observed:

```json
{
  "command": "init",
  "data": {
    "engine_readiness": {
      "ecosystem": "rust",
      "engine": "cargo-test",
      "engine_version": "1.96.0",
      "evidence": ["Cargo.toml"],
      "issues": [],
      "state": "ready"
    },
    "store_state": "ready",
    "store_path": "...<workspace>/.novetest"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

### Scenario 1 — `novetest run` (no coverage) — THE CORE FIX PROOF

```bash
uv run --project /home/yjshin/dev/Nove-Test novetest run
echo "exit=$?"
```

**Pre-fix behavior** (from
`findings/manual-test-team-2026-05-30-cargo-e2e-sweep.md` Issue 1):
- Exit code: `4`
- `ok: false`
- `errors[0].code: "adapter-unparseable-output"`
- `data.memory_entry.run_record.test_results: []` (empty)
- `data.memory_entry.run_record.summary_counts: {total: 0, ...}`

**Post-fix observed behavior** (real envelope, captured from this run):
- **Exit code: `3`** (= test-failures-detected per the envelope contract — the fixture has 1 intentional failing test)
- **`ok: true`** ✅
- `data.memory_entry.run_record.engine_name: "cargo-test"`
- `data.memory_entry.run_record.engine_version: "1.96.0"`
- `data.memory_entry.run_record.status: "failed"` (because 1/3 tests failed)
- `data.memory_entry.run_record.summary_counts: {failed: 1, passed: 2, skipped: 0, total: 3}` ✅
- `data.memory_entry.run_record.test_results: [3 entries]`:
  - `cargo_test_basic::integration_test$test_add_via_integration` — `passed`
  - `cargo_test_basic::cargo_test_basic$tests::test_add_passes` — `passed`
  - `cargo_test_basic::cargo_test_basic$tests::test_subtract_intentionally_fails` — `failed` (with `failure_reference` populated)
- `data.memory_entry.run_record.metadata.native_exit_code: 100` (libtest's "1 or more tests failed" code, NOT 95 which would be "experimental feature not enabled")
- `errors: []`
- `warnings: []`

### Scenario 2 — verify libtest-JSON events were actually written

```bash
RUN_ID=$(python3 -c "import json,sys; e=json.load(open('/tmp/run.json')); print(e['data']['memory_entry']['run_record']['run_reference']['run_id'])")
EVENTS=".novetest/run/artifacts/run_${RUN_ID}/native/events.jsonl"
wc -l "$EVENTS"
head -3 "$EVENTS"
```

Expected on post-fix:
- `wc -l` returns **non-zero** (I observed `10` lines for this fixture).
- First lines look like:
  ```jsonl
  {"type": "suite", "event": "started", "test_count": 1}
  {"type": "test", "event": "started", "name": "cargo_test_basic::integration_test$test_add_via_integration"}
  ```

Expected on pre-fix:
- `wc -l` returns `0` — the file exists but is empty because nextest
  exited 95 before writing any events.

This is the **smoking-gun proof** that the env var is now propagating
to the child process correctly.

### Scenario 3 — `novetest run --coverage` (LCOV path)

Use the dedicated coverage fixture:

```bash
WORKSPACE2=$(mktemp -d -t novetest-cargo-cov-verify-XXXX)
cp -r tests/fixtures/projects/cargo-test-basic-coverage "$WORKSPACE2/"
cd "$WORKSPACE2/cargo-test-basic-coverage"
uv run --project /home/yjshin/dev/Nove-Test novetest init
uv run --project /home/yjshin/dev/Nove-Test novetest run --coverage
echo "exit=$?"
```

Expected post-fix (observed verbatim):
- Exit code: `0` (all 4 tests pass in this fixture)
- `ok: true`
- `status: "passed"`
- `summary_counts: {failed: 0, passed: 4, skipped: 0, total: 4}`
- `artifact_paths` keys: `['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']`
  — note the new `coverage_lcov` key, which Manual Test should
  open and confirm contains real LCOV records (`SF:` / `DA:` / `LF:`
  / `LH:` lines). The cargo-llvm-cov path goes through the same env
  inheritance, so this stamp also proves the env var is honored on the
  coverage path.

### Scenario 4 — confirm the `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` env var is present in the merged code

Sanity grep for reviewers / Manual Test:

```bash
grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" src/novetest/run/adapters/cargo_adapter.py
# → 365:    - ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`` is the gate that
# → 384:    env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"
```

```bash
grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON\|test_build_child_env_pins" tests/unit/run/adapters/test_cargo_adapter.py
# → 885:def test_build_child_env_pins_nextest_libtest_json_gate() -> None:
# → 903:    assert env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] == "1"
```

## Critical edge cases worth probing

1. **`cargo nextest` version below 0.9.50.** Our supported floor is
   0.9.50 (per `decisions/2026-05-25-supported-engine-matrix.md`). On
   pre-0.9.50 nextest the env var is **unrecognized** but harmless —
   nextest ignores unknown env vars. However the `--message-format=libtest-json`
   flag was added in nextest 0.9.50 itself, so older nextest will fail
   on the flag regardless of the env var. The adapter's contract is
   "0.9.50+", and there is no version probe before adapter dispatch.
   If Manual Test has access to an older nextest, confirm exit `4`
   with `adapter-unparseable-output` (the SAME pre-fix symptom — older
   nextest would manifest identically to the env-var-missing case
   pre-fix). Out of scope to add a version probe; documented in the
   adapter's docstring.

2. **Coverage path verification.** The coverage path goes through
   `cargo llvm-cov nextest`. `cargo llvm-cov` forwards the parent
   env to its nextest invocation, so the new env var propagates
   transitively. Scenario 3 above stamps this. If Manual Test sees
   `coverage_lcov` artifact present + non-empty, the propagation is
   working.

3. **No-test-results scenarios still classify correctly.** The
   build-failure heuristic at `cargo_adapter.py:263` still classifies
   `exit ≠ 0 AND zero events` as `adapter-unparseable-output`. The
   FIX moves the cargo path OUT of that branch (events are now
   written). But the heuristic itself is **unchanged** — if someone
   passes a `--filter` that matches zero tests, the empty-events
   case will still surface as adapter-unparseable. This is a
   pre-existing low-priority polish item that the handoff explicitly
   left out of scope.

4. **The `metadata.native_exit_code` value.** The merged envelope
   stashes nextest's raw exit code as
   `data.memory_entry.run_record.metadata.native_exit_code`. Per
   `decisions/2026-05-30-native-result-metadata-slot.md` (b chosen),
   this is a typed slot in a follow-up slice (Issue 2). For this
   verification, simply confirm the value is **`100`** (libtest's
   "1+ tests failed" code) on Scenario 1 — NOT `95` (which would
   indicate the env var is still missing).

5. **Tests skipped on un-equipped CI cells.** CI cells WITHOUT cargo
   should still see both `test_cargo_*.py` integration tests skip
   (not error), and the test count should be `676 passed + 7 skipped`
   on those cells. Manual Test does NOT need to verify this — it's
   implicit in the existing autouse fixture skip-guard in the cargo
   test modules; documented here for awareness.

6. **Trigger-(b) closure on `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`.**
   Per §3 of that decision, trigger-(b) closes when (a) `2026-05-30-cargo-e2e-sweep`
   findings are filed AND (b) those findings demonstrate **no
   regression vs the cargo-less host**. Issue 1 from that sweep
   blocked closure. This hotfix closes Issue 1. Manual Test's
   re-execution of Scenarios 1–3 above against tip `1e736cc` (or
   `58acb74` if my push tip is the verification commit) on the
   equipped host is the final closure step. PM ticks
   `decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md` §3
   trigger-(b) as resolved during cycle close.

## End-of-Main-Branch checklist

- [x] Worktree base (`e90f61e`) equals current main tip — clean
      fast-forward merge, zero conflicts.
- [x] Both gates green on the merged tip (`1e736cc`): 678 passed + 5
      skipped, mypy strict clean across 70 source files.
- [x] Cargo integration tests re-run in isolation post-merge: 2/2
      passed in 0.57s.
- [x] End-to-end smoke against real cargo fixture: `novetest run`
      against `cargo-test-basic` returns exit 3 (test failures, NOT
      exit 4 adapter-unparseable), with all 3 test results parsed
      and `events.jsonl` containing 10 real libtest-JSON events.
- [x] End-to-end smoke against coverage fixture: `novetest run
      --coverage` against `cargo-test-basic-coverage` returns exit 0,
      4/4 passed, `coverage_lcov` artifact present.
- [x] Source handoff consumed.
- [x] Verification doc written (this file) with pre-fix vs post-fix
      delta clearly contrasted from the findings doc.
- [x] INDEX.md regenerated and consistent post-merge.
- [ ] Push to `origin/main` (per CEO authorization
      "확인해서 머지하고 푸시해" in the dispatch message).
- [ ] Worktree `/home/yjshin/dev/novetest-cargo-nextest-env-var-hotfix`
      removed and branch
      `worktree-run-team-cargo-nextest-env-var-hotfix` deleted after
      push.
