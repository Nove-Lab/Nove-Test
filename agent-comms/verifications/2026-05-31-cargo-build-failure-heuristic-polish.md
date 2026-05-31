---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-31
slug: cargo-build-failure-heuristic-polish
related:
  - agent-comms/handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md
  - agent-comms/tasks/run-team-2026-05-31-build-failure-heuristic-polish.md
  - agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md
  - src/novetest/run/adapters/cargo_adapter.py
  - tests/unit/run/adapters/test_cargo_adapter.py
---

# Verification: cargo build-failure heuristic — `misconfigured-environment` polish

## What landed on `main` this cycle

Single-slice cycle (parallel sibling was kicked back — see "Parked work"
below).

**Merged commits** (both via FF, no conflicts):

| Commit | Author | Summary |
|---|---|---|
| `8910bf1` | run-team | refactor(run): surface misconfigured-environment kind on cargo env-var stderr |
| `58bb603` | run-team | docs(run): correct line-count bookkeeping in WORKLOG + handoff |

**Merged tip**: `58bb603` (was on main at `061e741`; baseline cycle gate
was 712+5).

**Source handoff consumed**:
- [`run-team-2026-05-31-build-failure-heuristic-polish.md`](../handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md)
  — single-handoff slice; status `ready-to-merge`.

## What the slice does

Diagnostic UX polish on the cargo adapter's `unparseable-output`
branches. When `cargo nextest`'s stderr carries the literal
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, the adapter now raises a specific
`misconfigured-environment` `AdapterInvocationError` kind (with
override-diagnosis prose pointing at the env var by name) instead of
the generic `unparseable-output` (which mis-frames the symptom as a
compile failure).

Polish applies symmetrically to **both** the build-failure path
(plain `cargo nextest`) and the coverage path (`cargo llvm-cov nextest`).
Helper `_libtest_json_env_misconfigured_error` keeps the two emissions
in sync via a single source.

**Out of scope (intentional, per task brief)**: the actual env-var
hotfix (commit `1e736cc` from 2026-05-31 morning) is unchanged — the
env var is set unconditionally in `_build_child_env()` so the polish
is **dead code in normal operation**. The polish only fires if a
parent process or future nextest version somehow surfaces the env-var
literal in stderr despite the adapter setting it. Unit tests pin the
behavior via subprocess mocking.

**No DoD bullet implications.** This is diagnostic UX polish, not a
phase-gated feature.

## Files changed (cumulative across both merged commits)

| File | Net change | Nature |
|---|---|---|
| `src/novetest/run/adapters/cargo_adapter.py` | +66 / −0 | Module-level `_NEXTEST_LIBTEST_JSON_ENV_LITERAL` constant + `_libtest_json_env_misconfigured_error` helper. Insertion BEFORE both existing `unparseable-output` raises (build-failure path line ~315, coverage path line ~342). |
| `tests/unit/run/adapters/test_cargo_adapter.py` | +111 / −0 | Two new tests: `test_build_failure_heuristic_surfaces_env_var_literal` (line 510) + `test_collect_coverage_env_var_literal_surfaces_misconfigured_environment` (line 856). One per code branch. |
| `WORKLOG.md` | +8 / −0 (refactor) + ~2 (docs) | Top entry `2026-05-31 — phase3 / cargo-build-failure-heuristic-polish`. |
| `agent-comms/handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md` | NEW | Slice handoff (159 lines after docs correction). |

**Source-file count: 71 → 71** (no new src files; only a string constant
+ helper function added inside the existing `cargo_adapter.py`).

## Pre-merge gate evidence (Main Branch, equipped host)

```
$ git merge --ff-only worktree-run-team-build-failure-heuristic-polish
Updating 061e741..58bb603
Fast-forward
 WORKLOG.md                                         |   8 ++
 ...am-2026-05-31-build-failure-heuristic-polish.md | 159 +++++++++++++++++++++
 src/novetest/run/adapters/cargo_adapter.py         |  66 +++++++++
 tests/unit/run/adapters/test_cargo_adapter.py      | 111 ++++++++++++++
 4 files changed, 344 insertions(+)

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q tests/unit tests/integration
... 714 passed, 5 skipped in 30.77s

$ uv run mypy
Success: no issues found in 71 source files

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py \
    tests/integration/coverage/test_cargo_lcov_e2e.py -v
... 3 passed in 1.30s

$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_build_failure_heuristic_surfaces_env_var_literal \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_env_var_literal_surfaces_misconfigured_environment -v
... 2 passed in 0.03s
```

- Gate: **714 + 5** (baseline `061e741` was **712 + 5** → +2 = the 2 new
  heuristic-polish tests, exactly as predicted in handoff §"Pre-flight #1").
- mypy: clean at **71** (no new src files).
- Cargo integration in isolation: 3/3 in 1.30s (basic + coverage + lcov_e2e).
- New polish tests in isolation: 2/2 in 0.03s.

## E2E happy-path envelope (proves polish didn't break the happy path)

Captured via `novetest run --coverage` against `cargo-test-basic-coverage`
on the freshly-merged tip (`58bb603`):

```
$ cd /tmp/run-polish-smoke/cargo-test-basic-coverage
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH \
    novetest init   # → ok: true, store_state: ready
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH \
    novetest run --coverage
```

Envelope shape (Manual Test: pinned paths — these are the ACTUAL paths
from the freshly-merged code, copy-paste them verbatim):

| Path | Observed value |
|---|---|
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` |
| `data.memory_entry.run_record.engine_version` | `"1.96.0"` |
| `data.memory_entry.run_record.metadata` | `{"native_exit_code": 0, "nextest_version": "0.9.137"}` |
| `data.memory_entry.run_record.summary_counts` | `{"passed": 4, "failed": 0, "skipped": 0, "total": 4}` |
| `data.memory_entry.run_record.status` | `"passed"` |
| `data.memory_entry.run_record.artifact_paths` keys | `["cargo_events_jsonl", "coverage_lcov", "stderr", "stdout"]` |
| `data.coverage_outcome.kind` | `"fact-set"` |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` |
| `data.coverage_outcome.summary.percent_covered` | `96.0` (24/25 statements) |
| `errors` | `[]` |
| `warnings` | `[]` |

Note: the **memory entry root** at `data.memory_entry` has these top-level
keys: `entry_id, has_coverage_facts, has_localization_findings,
has_regression_facts, has_replay_result, run_record, schema_version,
stored_at, tombstoned_at`. There is NO `data.memory_entry.run_reference`
key — the run reference is nested at `data.memory_entry.run_record.run_reference`.

This pins both the prior-cycle slices (Coverage cargo LCOV dispatch +
NativeResult typed metadata slot) AND confirms this slice didn't regress
either.

## Manual Test scope (8 scenarios)

The polish's load-bearing assertions are in the unit suite (subprocess
mocking is the only way to deterministically trigger the
`misconfigured-environment` path — the env-var hotfix prevents normal
operation from surfacing the symptom). Manual Test's job is:

1. **Confirm happy-path regression-free**.
2. **Inspect the new error message shape** (so Manual Test can recognize
   it if it ever appears in the field).
3. **Probe the existing `unparseable-output` fallback** still fires for
   non-matching stderr (compile failures).
4. **Inspect the new `kind` value** in the envelope error shape.

### Scenario 1 — Happy path: `novetest run --coverage` against `cargo-test-basic-coverage`

```bash
cd /tmp/scratch  # or any clean tmpdir
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic-coverage .
cd cargo-test-basic-coverage
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage
```

**Expected**: exit 0, envelope matches the pinned paths above (4 passed,
status: passed, coverage_outcome.kind: fact-set, mapping_granularity:
aggregate, ~96% covered). The Run polish slice does NOT change any of
this — pure regression confirmation.

### Scenario 2 — Happy path: `novetest run` (no coverage) against `cargo-test-basic`

```bash
cd /tmp/scratch
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic .
cd cargo-test-basic
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run
```

**Expected**: exit 0, `data.memory_entry.run_record.engine_name: "cargo-test"`,
`status: "passed"`, `artifact_paths` keys: `["cargo_events_jsonl",
"stderr", "stdout"]` (NO `coverage_lcov` since no `--coverage` flag),
`metadata = {"native_exit_code": 0, "nextest_version": "0.9.137"}`.

### Scenario 3 — Read the two new unit tests (this is where the slice's smoking gun lives)

```bash
cd /home/yjshin/dev/Nove-Test
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_build_failure_heuristic_surfaces_env_var_literal \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_env_var_literal_surfaces_misconfigured_environment \
    -v
```

**Expected**: 2 passed. The two tests assert:

For `test_build_failure_heuristic_surfaces_env_var_literal` (line 510):
- `exc_info.value.kind == "misconfigured-environment"` (the load-bearing assertion)
- Message contains `"NEXTEST_EXPERIMENTAL_LIBTEST_JSON"` (the env-var literal)
- Message contains `"parent process or shell hasn't pre-unset"` (override-diagnosis prose)
- Message contains `"cargo nextest exited 95"` (spawn-path label + exit code)

For `test_collect_coverage_env_var_literal_surfaces_misconfigured_environment` (line 856):
- Same `kind = "misconfigured-environment"`
- Same env-var literal in message
- Spawn-path label says `"cargo llvm-cov nextest exited"` (NOT plain
  `"cargo nextest exited"`) — distinguishes coverage path from
  build-failure path.

Manual Test may want to **read the test source** to understand the
mocking setup (`monkeypatch.setattr(adapter, "run_subprocess", _make_stub_subprocess(returncode=95, stderr_bytes=nextest_env_missing_stderr))`)
since this is how the polish is exercised in practice — no real cargo
invocation needed.

### Scenario 4 — Inspect the helper source for the actual message shape

```bash
sed -n '80,115p' src/novetest/run/adapters/cargo_adapter.py
```

**Expected output**:

```python
# failure. Detection is substring-only on the env-var name (not the
# full upstream error sentence) so benign upstream wording tweaks do
# not break the heuristic; the env-var name itself is the load-bearing
# token nextest will keep printing as long as the gate is named that.
_NEXTEST_LIBTEST_JSON_ENV_LITERAL = "NEXTEST_EXPERIMENTAL_LIBTEST_JSON"


def _libtest_json_env_misconfigured_error(
    *, mode: str, returncode: int, stderr_tail: str
) -> AdapterInvocationError:
    """Build the ``misconfigured-environment`` error raised when
    nextest's stderr signals the libtest-json gate env var was not
    honored.
    ...
    """
    return AdapterInvocationError(
        f"cargo {mode} exited {returncode} signaling that "
        f"NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 was not honored; the "
        f"adapter sets this env var in _build_child_env() — check that "
        f"the parent process or shell hasn't pre-unset it, and that a "
        f"future nextest version hasn't renamed the gate. stderr tail: "
        f"{stderr_tail}",
        kind="misconfigured-environment",
    )
```

This is the message Manual Test would see in `envelope.errors[].message`
if the polish ever fires in the field.

### Scenario 5 — Confirm existing `unparseable-output` fallback STILL fires for non-matching stderr

```bash
cd /home/yjshin/dev/Nove-Test
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_build_failure_shape_raises_unparseable \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_missing_lcov_raises_unparseable \
    -v
```

**Expected**: 2 passed. These existing tests prove the polish doesn't
break the generic fallback — they use stderr that does NOT contain the
env-var literal, so the heuristic correctly skips the new
misconfigured-environment branch and falls through to the existing
`unparseable-output` raise. (Per handoff §DoD bullet 4.)

### Scenario 6 — Cargo integration: full Coverage + Memory pipeline

```bash
cd /home/yjshin/dev/Nove-Test
PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py \
    tests/integration/coverage/test_cargo_lcov_e2e.py \
    -v
```

**Expected**: 3 passed in ~1.3s. This pins:
- Run engine (cargo adapter happy path unchanged)
- Coverage engine (LCOV dispatch from prior cycle still working)
- Cargo end-to-end via Memory (record.json with metadata typed slot
  from prior cycle still working)

If ANY of these regress, the polish slice broke something.

### Scenario 7 — Read the WORKLOG entry to verify it accurately describes the slice

```bash
sed -n '1,25p' WORKLOG.md
```

**Expected**: Top entry dated `2026-05-31 — phase3 / cargo-build-failure-heuristic-polish`,
5-bullet format, lists both code branches (build-failure + coverage),
mentions the `misconfigured-environment` kind by name.

### Scenario 8 — Read the AdapterInvocationError class to verify the `kind` field is plain `str` (no enum)

```bash
grep -n "class AdapterInvocationError\|^[[:space:]]*kind:" src/novetest/run/errors.py | head -10
```

**Expected**: `kind: str` (plain string, no `Literal[...]` constraint).
This pins the rationale from handoff §"`kind` choice rationale" — the
new `"misconfigured-environment"` literal can land without enum
migration. If a future slice formalizes `kind` as a `StrEnum`, all six
existing literals (`missing-binary`, `missing-plugin`, `missing-engine`,
`unparseable-output`, `timed-out`, `misconfigured-environment`) live in
one place to migrate.

## Critical edge cases worth probing

| Edge case | Why it matters | How to probe |
|---|---|---|
| **Polish only on substring match, not full sentence match** | Future nextest may tweak the surrounding error prose without renaming the env var. The polish must still fire. | Read `_NEXTEST_LIBTEST_JSON_ENV_LITERAL = "NEXTEST_EXPERIMENTAL_LIBTEST_JSON"` at line 84 of `cargo_adapter.py`. Detection is substring-only on this literal. |
| **Spawn-path label distinguishes branches** | If someone swaps the call sites, the coverage-path test would falsely pass with the build-failure label. | Scenario 3's second test asserts `"cargo llvm-cov nextest exited"` specifically (not the bare `"cargo nextest exited"`). |
| **Env var override behavior unchanged** | The 2026-05-31 hotfix sets `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` in `_build_child_env()`. A parent shell pre-setting it to `"0"` would be OVERRIDDEN by the adapter. The polish does NOT relax this. | Run `grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" src/novetest/run/adapters/cargo_adapter.py` — should show 4 hits: 1 module constant + 2 detection sites + 1 env assignment (line ~373 in `_build_child_env`). |
| **No new `AdapterInvocationError` kinds beyond the one needed** | Over-engineering would be adding a `StrEnum` or multiple kinds for "different env-var failures". The slice stays minimal: exactly ONE new kind. | `grep -n "kind=" src/novetest/run/adapters/cargo_adapter.py` should show the new `"misconfigured-environment"` literal only at the new helper, with all other kinds (`unparseable-output`, `missing-binary`, `missing-plugin`, `timed-out`) unchanged. |
| **Helper is a single source for two emissions** | If the helper drifts on one branch but not the other, the symptom-to-action mapping diverges. The slice deliberately uses one helper for both call sites. | Confirm `_libtest_json_env_misconfigured_error(mode="nextest", ...)` and `_libtest_json_env_misconfigured_error(mode="llvm-cov nextest", ...)` are the only call sites (line ~316 and ~343). |

## Parked work — Localization fallback-modes slice (NOT merged this cycle)

The cycle's parallel sibling slice (Localization `sbfl_aggregate` +
`failure_proximity` modes, worktree
`novetest-localization-fallback-modes`, tip `a42ea87`) was **kicked
back** to PM with two defects identified:

1. **Run-adapter gap**: `cargo llvm-cov` bails without writing LCOV
   when inner `cargo nextest` exits non-zero. The new
   `localization-aggregate-only` fixture has an intentionally-failing
   test, so the aggregate-e2e test fails on equipped hosts.
2. **Fixture design defect**: Cargo's `assert_eq!` panic trace points
   to the assertion site (`lib.rs:35`), not the bug site
   (`arithmetic.rs::divide`). The test's `endswith("arithmetic.rs")`
   assertion is unreachable with this fixture as-is.

Full analysis + reproduction + suggested fix paths in:
`agent-comms/questions/main-branch-team-2026-05-31-localization-aggregate-e2e-equipped-host-defect.md`

The Localization worktree remains in `/home/yjshin/dev/novetest-localization-fallback-modes`
and the branch `novetest-localization-fallback-modes` was NOT deleted.
PM owns the next step.

**Manual Test scope for THIS cycle is the Run polish slice only.** Do
NOT probe Localization paths — they didn't land. The `localization`
verb's existing pytest path (`sbfl_per_test` mode) continues working
as before; no regression from this cycle (no Localization src changes
landed).

## Notes from merging

- **Single-slice FF, zero conflicts**. The Run worktree was based on
  `061e741` (current main tip) so `git merge --ff-only` cleanly
  fast-forwarded both commits (`8910bf1` refactor + `58bb603` docs
  correction).
- **No WORKLOG conflict** (the parallel Localization slice would have
  caused one, but it was withheld).
- **Worktree cleanup deferred** — the `worktree-run-team-build-failure-heuristic-polish`
  worktree will be removed AFTER push authorization. Localization
  worktree retained pending the parked-work resolution.

## Next steps

1. **Manual Test**: run the 8 scenarios above; file `findings/` per
   the usual cadence.
2. **PM**: triage the parked Localization slice per the linked
   question doc. The Localization handoff itself remains valid
   pre-defect-fix — only the e2e test + fixture (and Run adapter)
   need surgery.
3. **CEO**: decide whether to authorize push of `058bb603` to origin.
   If yes, Main Branch will push and clean up the Run worktree. If
   not, the merged work stays local until authorization.

---

Filed by: novetest-main-branch-team
Date: 2026-05-31
Cycle: parallel cycle 2026-05-31 (Localization fallback-modes +
       cargo build-failure heuristic polish) — Run slice merged, Loc slice parked
