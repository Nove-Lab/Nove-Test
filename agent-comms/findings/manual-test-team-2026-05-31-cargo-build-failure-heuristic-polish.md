---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-31
slug: cargo-build-failure-heuristic-polish
verdict: passed
related:
  - agent-comms/verifications/2026-05-31-cargo-build-failure-heuristic-polish.md
  - agent-comms/handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md
  - agent-comms/tasks/run-team-2026-05-31-build-failure-heuristic-polish.md
  - src/novetest/run/adapters/cargo_adapter.py
  - tests/unit/run/adapters/test_cargo_adapter.py
---

# Manual Test findings — cargo build-failure heuristic polish (`misconfigured-environment` kind)

**Verdict**: **passed**.

The Run-team polish slice merged at `58bb603` (refactor `8910bf1` +
docs-correction `58bb603`) ships a narrow diagnostic UX improvement on
the cargo adapter's two `unparseable-output` raise sites: when nextest
or `cargo llvm-cov nextest` stderr contains the literal
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, the adapter now raises a specific
`misconfigured-environment` `AdapterInvocationError.kind` instead of
the generic `unparseable-output`. The generic kind would mis-frame the
symptom as a compile failure; the new kind points an AI consumer or
human straight at the env-var name and the override-diagnosis prose so
the next step is obvious. The substantive fix to the
env-var-missing case landed earlier (`1e736cc` hotfix sets the env
unconditionally in `_build_child_env`); this polish is defense-in-depth
diagnostic for any path where the hotfix is bypassed (parent process
strips the env, future nextest renames the gate, etc.).

All 8 scenarios in the verification doc + the 5 edge-case probes
passed. No source regressions. Two doc-level observations on the
verification request itself worth flagging for next-cycle PM polish
(neither is a slice defect — both are predicted-output typos in the
verification request, not behavior issues in the merged code).

## What was tested

A CEO-readable narrative:

1. **The happy path still works end-to-end.** A clean cargo run with
   coverage — `novetest init` + `novetest run --coverage` against the
   `cargo-test-basic-coverage` fixture — produces a `novetest/v1` JSON
   envelope with `data.coverage_outcome.kind: "fact-set"`, 96.0%
   statement coverage (24/25 statements), `status: "passed"`, all
   four expected `artifact_paths` keys (`cargo_events_jsonl`,
   `coverage_lcov`, `stderr`, `stdout`), and the typed metadata slot
   carrying both `native_exit_code: 0` AND `nextest_version: "0.9.137"`.
   The polish does NOT touch the happy path — pure regression
   confirmation.

2. **The new diagnostic actually fires when its trigger condition is
   met.** Two new unit tests in `tests/unit/run/adapters/test_cargo_adapter.py`
   simulate nextest exiting 95 with the env-var-literal stderr (via
   `monkeypatch.setattr(adapter, "run_subprocess", ...)`) and assert
   the adapter raises `AdapterInvocationError(kind="misconfigured-environment")`
   with a message naming the env var, the override-diagnosis prose
   ("parent process or shell hasn't pre-unset"), AND a spawn-path label
   that distinguishes the build-failure branch (`cargo nextest exited 95`)
   from the coverage branch (`cargo llvm-cov nextest exited 95`). Both
   tests pass in 0.03s; the asymmetry lock guards against the two raise
   sites accidentally sharing the same mode label.

3. **The existing generic fallback still fires when its trigger
   condition is NOT met.** Two pre-existing tests
   (`test_build_failure_shape_raises_unparseable`,
   `test_collect_coverage_missing_lcov_raises_unparseable`) exercise
   stderr that does NOT contain the env-var literal (true compile
   failure stderr, plain LCOV-write failure) and assert the adapter
   still raises `unparseable-output`. Both pass in 0.03s. The polish
   inserts the new branch BEFORE the existing raises and falls through
   cleanly when the substring check fails.

4. **The polish is structurally minimal.** Exactly one new
   `AdapterInvocationError.kind` literal (`misconfigured-environment`).
   The helper `_libtest_json_env_misconfigured_error` is the SINGLE
   source of both emissions (build-failure path AND coverage path),
   keyword-only args (`*, mode, returncode, stderr_tail`) so the two
   call sites can't accidentally swap integer-ish values, and a
   one-line module constant `_NEXTEST_LIBTEST_JSON_ENV_LITERAL` used
   for both substring checks. Substring-only detection (not full
   upstream error sentence) keeps the heuristic robust against benign
   nextest wording tweaks.

5. **The earlier env-var hotfix is unchanged.** `_build_child_env()`
   still sets `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` unconditionally
   at line 463. The polish is dead code in normal operation; it only
   fires if a parent process / shell strips the env var or a future
   nextest version renames the gate.

6. **Persisted records still round-trip correctly.** The
   `.novetest/memory/runs/2026/05/31/run_<ulid>/record.json` file
   from Scenario 1 carries `metadata = {"native_exit_code": 0,
   "nextest_version": "0.9.137"}` (the typed slot from the prior
   2026-05-31 cycle still works through the polish slice unchanged),
   and `novetest inspect <run_id>` flips `sub_reports.coverage` to
   `"available"` (the Coverage LCOV dispatch from the prior cycle is
   unaffected).

7. **mypy strict gate is clean at 71 source files** (same as
   baseline `061e741` — the polish adds zero source files, only a
   constant + helper inside the existing `cargo_adapter.py`).

8. **The full pytest gate is green at 714 + 5 skipped in 30.99s**
   (baseline `061e741` was 712 + 5 → +2 net = exactly the two new
   polish unit tests, matching Main Branch's pre-merge gate evidence
   line-for-line).

## Commands run (verbatim) + observed output

### Scenario 0 — full pytest gate against tip `58bb603`

```
$ . "$HOME/.cargo/env" && uv run pytest -q tests/unit tests/integration
[...]
--------------------------- snapshot report summary ----------------------------
1 snapshot passed.
714 passed, 5 skipped in 30.99s
```

Result: ✅ **714 + 5** — matches Main Branch claim.

### Scenario 0b — mypy strict

```
$ . "$HOME/.cargo/env" && uv run mypy
Success: no issues found in 71 source files
```

Result: ✅ **71 source files** — same as baseline (polish adds zero files).

### Scenario 1 — happy path: `novetest run --coverage` on `cargo-test-basic-coverage`

```
$ cd tests/manual-test-workspace/build-failure-polish/cargo-test-basic-coverage
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest init
{ ..., "ok": true, "warnings": [] }
$ PATH=$HOME/.cargo/bin:/home/yjshin/dev/Nove-Test/.venv/bin:$PATH novetest run --coverage
```

Envelope projection (all paths match the verification doc's pinned table verbatim):

| Path | Observed |
|---|---|
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` ✓ |
| `data.memory_entry.run_record.engine_version` | `"1.96.0"` ✓ |
| `data.memory_entry.run_record.metadata` | `{"native_exit_code": 0, "nextest_version": "0.9.137"}` ✓ |
| `data.memory_entry.run_record.summary_counts` | `{"passed": 4, "failed": 0, "skipped": 0, "total": 4}` ✓ |
| `data.memory_entry.run_record.status` | `"passed"` ✓ |
| `data.memory_entry.run_record.artifact_paths` keys | `["cargo_events_jsonl", "coverage_lcov", "stderr", "stdout"]` ✓ |
| `data.coverage_outcome.kind` | `"fact-set"` ✓ |
| `data.coverage_outcome.mapping_granularity` | `"aggregate"` ✓ |
| `data.coverage_outcome.summary.percent_covered` | `96.0` (24/25 statements) ✓ |
| `errors` | `[]` ✓ |
| `warnings` | `[]` ✓ |
| `data.memory_entry` top-level keys | `["entry_id", "has_coverage_facts", "has_localization_findings", "has_regression_facts", "has_replay_result", "run_record", "schema_version", "stored_at", "tombstoned_at"]` ✓ |

Result: ✅ **Pinned table matches exactly**. The polish does not
regress the happy path; the Coverage dispatch + the typed metadata
slot from the prior 2026-05-31 cycle both continue working through
this merge.

### Scenario 1b (extension) — persisted record.json round-trip

```
$ python3 -c "import json, glob; ..."
persisted record.json count: 1
--- .novetest/memory/runs/2026/05/31/run_01KSZ6N4M8ZHAENE0HZ8BENV6X/record.json ---
schema_version: 1
engine_name: cargo-test
engine_version: 1.96.0
metadata: {'native_exit_code': 0, 'nextest_version': '0.9.137'}
summary_counts: {'passed': 4, 'failed': 0, 'skipped': 0, 'total': 4}
artifact_paths keys: ['cargo_events_jsonl', 'coverage_lcov', 'stderr', 'stdout']
status: passed
```

Result: ✅ **disk-level metadata round-trip confirmed**.

### Scenario 1c (extension) — `novetest inspect <run_id>`

```
$ novetest inspect 01KSZ6N4M8ZHAENE0HZ8BENV6X
ok: True
run_summary.engine_name: cargo-test
run_summary.status: passed
run_summary.summary_counts: {passed: 4, failed: 0, skipped: 0, total: 4}
sub_reports: {coverage: 'available', localization: 'unavailable', regression: 'unavailable', replay: 'unavailable'}
coverage_outcome.kind: fact-set
coverage_outcome.summary.percent_covered: 96.0
coverage_outcome.summary.num_branches: 0   # BRDA-absent (matches prior cycle Edge 4 invariant)
```

Result: ✅ **inspect verb correctly composes Coverage Facts +
Run summary; sub_reports.coverage flips to `"available"`**. Polish
does not regress cross-engine flow.

### Scenario 2 — no-coverage path: `novetest run` on `cargo-test-basic`

```
$ cd tests/manual-test-workspace/build-failure-polish/cargo-test-basic
$ novetest init
$ novetest run
```

Envelope:

| Path | Observed |
|---|---|
| `data.memory_entry.run_record.engine_name` | `"cargo-test"` ✓ |
| `data.memory_entry.run_record.engine_version` | `"1.96.0"` ✓ |
| `data.memory_entry.run_record.metadata` | `{"native_exit_code": 100, "nextest_version": "0.9.137"}` ✓ (typed slot) |
| `data.memory_entry.run_record.summary_counts` | `{"failed": 1, "passed": 2, "skipped": 0, "total": 3}` |
| `data.memory_entry.run_record.status` | `"failed"` (by-design failing test in this fixture) |
| `data.memory_entry.run_record.artifact_paths` keys | `["cargo_events_jsonl", "stderr", "stdout"]` ✓ (NO `coverage_lcov`) |
| `data.coverage_outcome` | `None` ✓ (no `--coverage` flag) |
| Shell exit code | `3` (test-failures-detected, correct mapping) |

Result: ✅ **No-coverage path correct** — typed metadata slot carries
both keys; `coverage_lcov` artifact absent; envelope status correctly
reflects the fixture's intentionally-failing test (Obs 1 below).

### Scenario 3 — the two new polish unit tests

```
$ uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_build_failure_heuristic_surfaces_env_var_literal \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_env_var_literal_surfaces_misconfigured_environment -v
collected 2 items
tests/unit/run/adapters/test_cargo_adapter.py .. [100%]
2 passed in 0.03s
```

Test source (excerpts) verified verbatim:
- `test_build_failure_heuristic_surfaces_env_var_literal` (line 510)
  asserts `kind == "misconfigured-environment"`, message contains
  `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, `"parent process or shell
  hasn't pre-unset"`, AND `"cargo nextest exited 95"`. Stub uses
  `returncode=95` + nextest's literal error sentence as stderr.
- `test_collect_coverage_env_var_literal_surfaces_misconfigured_environment`
  (line 856) asserts the same kind + same env-var literal + same
  diagnosis prose, but locks the spawn-path label as
  `"cargo llvm-cov nextest exited 95"` (NOT plain
  `"cargo nextest exited"`). Stub uses `write_coverage_lcov=False`
  so the symmetric branch fires.

Result: ✅ **Both new tests pass and the asymmetry lock (build-failure
vs coverage spawn-path label) is enforced** — wiring the wrong
`mode=` kwarg to either call site would surface immediately.

### Scenario 4 — helper source verbatim

```
$ sed -n '80,115p' src/novetest/run/adapters/cargo_adapter.py
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

    ``mode`` is either ``"nextest"`` (plain run) or
    ``"llvm-cov nextest"`` (coverage run) — embedded as the spawn-path
    identifier in the message so AI consumers and humans can tell
    which path produced the failure. Both call sites use the same
    diagnosis prose so the symptom-to-action mapping stays consistent
    across the two branches. Single helper, two callers — duplicated
    f-strings would have drifted on the next polish pass.
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

Result: ✅ **Helper source matches the verification doc verbatim.**
Keyword-only args enforced; single source of truth for both emission
sites.

### Scenario 5 — generic `unparseable-output` fallback still fires for non-matching stderr

```
$ uv run pytest -q \
    tests/unit/run/adapters/test_cargo_adapter.py::test_build_failure_shape_raises_unparseable \
    tests/unit/run/adapters/test_cargo_adapter.py::test_collect_coverage_missing_lcov_raises_unparseable -v
collected 2 items
tests/unit/run/adapters/test_cargo_adapter.py .. [100%]
2 passed in 0.03s
```

Result: ✅ **Pre-existing fallback tests still pass.** The polish
correctly skips the new branch when the env-var literal is absent
and falls through to the generic raise (true compile failures, missing
`llvm-tools-preview` rustup component, etc.).

### Scenario 6 — cargo integration trio (Run + Coverage + LCOV E2E)

```
$ . "$HOME/.cargo/env" && uv run pytest -q \
    tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py \
    tests/integration/coverage/test_cargo_lcov_e2e.py -v
collected 3 items
3 passed in 1.31s
```

Result: ✅ **All three cargo integration tests pass against the
freshly-merged tip.** Pins:
- Run engine cargo adapter happy path (basic).
- Run engine cargo coverage path (LCOV write + libtest-json events).
- Coverage engine cargo-LCOV dispatch end-to-end (prior cycle slice
  still working through the polish).

### Scenario 7 — WORKLOG entry

`WORKLOG.md` top entry, dated `2026-05-31 — phase3 / cargo-build-failure-heuristic-polish`:

- 5-bullet format ✓ (Landed / Verified / Left open / Gotcha / Next).
- Lists both code branches (build-failure path at line ~305, coverage
  path at line ~342) ✓.
- Mentions the `misconfigured-environment` kind by name ✓.
- Calls out `_NEXTEST_LIBTEST_JSON_ENV_LITERAL` constant + helper
  `_libtest_json_env_misconfigured_error` by name ✓.
- Documents the substring-only detection rationale (robustness vs
  upstream wording tweaks) ✓.
- Pinning quotes from WORKLOG verified verbatim — accurate description
  of the slice.

Result: ✅ **WORKLOG entry is accurate and complete.**

### Scenario 8 — `AdapterInvocationError.kind` is plain `str`

```
$ grep -n "class AdapterInvocationError\|^[[:space:]]*kind:" src/novetest/run/errors.py
43:class AdapterInvocationError(RunEngineError):
55:        kind: str,
```

Result: ✅ **`kind: str` plain string (no `Literal[...]` or `StrEnum`
constraint).** The new `"misconfigured-environment"` literal lands
without enum migration. If a future slice formalizes `kind` as a
`StrEnum`, all six current literals (`missing-binary`, `missing-plugin`,
`missing-engine`, `unparseable-output`, `timed-out`,
`misconfigured-environment`) live in one place for the migration.

## Edge case probes

### Edge 1 — Substring-only detection

The constant `_NEXTEST_LIBTEST_JSON_ENV_LITERAL = "NEXTEST_EXPERIMENTAL_LIBTEST_JSON"`
is the SINGLE load-bearing token. The detection sites at lines 315 and
342 use plain `in` substring containment, not full sentence match:

```python
if _NEXTEST_LIBTEST_JSON_ENV_LITERAL in stderr_text:
    raise _libtest_json_env_misconfigured_error(mode=..., returncode=..., stderr_tail=...)
```

Result: ✅ **Robust against benign nextest error-prose changes** as
long as the gate keeps that name.

### Edge 2 — Spawn-path label asymmetry

The two raise sites pass different `mode=` kwargs:
- Line 317: `mode="nextest"` (plain run)
- Line 344: `mode="llvm-cov nextest"` (coverage run)

The unit tests' fourth assertion in each test (`"cargo nextest exited 95"`
vs `"cargo llvm-cov nextest exited 95"`) is the asymmetry lock — a
future refactor that swaps the two `mode=` kwargs would pass the kind
+ env-var-literal + diagnosis-prose checks but fail the spawn-path
assertion. ✅ Already enforced by the unit suite.

### Edge 3 — Env var override behavior unchanged

```
$ grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" src/novetest/run/adapters/cargo_adapter.py
73:# ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1``. The 2026-05-31 hotfix
84:_NEXTEST_LIBTEST_JSON_ENV_LITERAL = "NEXTEST_EXPERIMENTAL_LIBTEST_JSON"
105:        f"NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 was not honored; the "
444:    - ``NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`` is the gate that
463:    env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"
```

Five literal hits (not 4 as the verification doc predicted — see Obs 3
below). The substantive invariant the verification doc cares about IS
preserved: **line 463 unconditionally sets the env var in
`_build_child_env()`** so the hotfix remains intact. The polish does
not relax this — parent-shell `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=0`
would still be overridden by the adapter.

Result: ✅ **Hotfix behavior unchanged.** The polish is dead code in
normal operation.

### Edge 4 — No new `kind` literals beyond the one needed

```
$ grep -n "kind=" src/novetest/run/adapters/cargo_adapter.py
110:        kind="misconfigured-environment",
150:            kind="missing-binary",        # cargo not on PATH
214:            kind="missing-binary",        # nextest plugin not installed
225:            kind="timed-out",
324:            kind="unparseable-output",    # build-failure fallback
351:            kind="unparseable-output",    # coverage-LCOV-write fallback
```

Six `kind=` occurrences, but only FOUR unique literals in the cargo
adapter: `misconfigured-environment` (new, ×1), `missing-binary` (×2),
`timed-out` (×1), `unparseable-output` (×2). Exactly ONE new unique
kind — slice stays minimal as Edge 4 of the verification doc demands.

Result: ✅ **Slice stays minimal.** No over-engineering to a StrEnum
or multiple env-var-related kinds.

### Edge 5 — Single helper, two callers (no f-string duplication)

```
$ grep -n "_libtest_json_env_misconfigured_error" src/novetest/run/adapters/cargo_adapter.py
87:def _libtest_json_env_misconfigured_error(
316:            raise _libtest_json_env_misconfigured_error(
343:            raise _libtest_json_env_misconfigured_error(
```

Three hits: 1 definition + 2 call sites. Both call sites use the
helper; no duplicated f-strings to drift on the next polish pass.

Result: ✅ **Single source of truth confirmed.**

## Issues found

**No source-level issues.** Three doc-level observations on the
verification request (none of which is a slice defect — all three are
predicted-output typos in the verification doc, not behavior issues
in the merged code).

### Obs 1 — Verification doc Scenario 2 expected `status: "passed"` + `native_exit_code: 0`, but `cargo-test-basic` is a by-design failing fixture

The verification doc's Scenario 2 expected table says:

> `metadata = {"native_exit_code": 0, "nextest_version": "0.9.137"}`
> ... `status: "passed"` ... exit 0

But running `novetest run` against the `cargo-test-basic` fixture
actually produces:

- `metadata = {"native_exit_code": 100, "nextest_version": "0.9.137"}`
- `status: "failed"`
- shell exit `3` (test-failures-detected)
- `summary_counts: {failed: 1, passed: 2, skipped: 0, total: 3}`

This is correct behavior — the prior cycle's WORKLOG entry
(`2026-05-31 — phase3 / native-result-metadata-typed-slot`, the
verified bullet's "Smoking-gun `record.json` grep" subsection)
explicitly says:

> read the persisted `record.json` — `metadata = {"native_exit_code":
> 100, "nextest_version": "0.9.137"}`. ... Status `failed` is the
> fixture's by-design failing test

So the verification doc's Scenario 2 expected values appear to be a
copy-paste from Scenario 1's all-passing `cargo-test-basic-coverage`
output, with the `coverage_lcov` artifact key removed but the
`status` / `native_exit_code` not adjusted for the basic fixture's
by-design failing test. **Not a slice defect.** The polish slice does
not touch this fixture's behavior; the envelope shape and typed
metadata slot are correct.

Suggested doc fix:
```diff
-`metadata = {"native_exit_code": 0, "nextest_version": "0.9.137"}`.
+`metadata = {"native_exit_code": 100, "nextest_version": "0.9.137"}`,
+`status: "failed"`, shell exit 3 (the fixture has a by-design
+failing test — see prior cycle's WORKLOG entry on the typed-slot
+smoking-gun grep).
```

### Obs 2 — Verification doc Edge 3 says grep for the literal "should show 4 hits", actual is 5

> grep -n "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" src/novetest/run/adapters/cargo_adapter.py — should show 4 hits: 1 module constant + 2 detection sites + 1 env assignment

But:
1. The two detection sites (lines 315, 342) use the CONSTANT name
   `_NEXTEST_LIBTEST_JSON_ENV_LITERAL`, not the raw literal — so they
   do NOT match a literal substring grep.
2. The actual literal-substring grep returns **5 hits**: 73 (comment),
   84 (constant value), 105 (helper f-string), 444 (`_build_child_env`
   docstring), 463 (env assignment).

The substantive invariant the verification doc actually wanted to
prove — **line 463 unconditionally sets the env var, so the hotfix
remains intact** — is preserved. Just the predicted count is off.
**Not a slice defect.**

Suggested doc fix:
```diff
-should show 4 hits: 1 module constant + 2 detection sites + 1 env assignment (line ~373 in `_build_child_env`)
+should show 5 hits of the literal substring: 1 comment (line 73),
+1 module constant value (line 84), 1 helper-message f-string
+(line 105), 1 docstring mention (line 444), and 1 env assignment
+(line 463 in `_build_child_env`). The 2 detection sites at lines
+315 and 342 use the *constant name* `_NEXTEST_LIBTEST_JSON_ENV_LITERAL`,
+so they appear under a separate grep for that identifier.
```

### Obs 3 — `AdapterInvocationError` docstring still lists only 4 kinds

`src/novetest/run/errors.py:47` says:

> `kind` is a stable machine token (`missing-plugin`, `missing-engine`,
> `unparseable-output`, `timed-out`); `install_hint` is text-only ...

Both `missing-binary` (added by the earlier cargo adapter slice) AND
the new `misconfigured-environment` (this slice) are absent from the
exhaustive list in the docstring. The WORKLOG entry's first Gotcha
explicitly acknowledges this as deliberate:

> The new `misconfigured-environment` kind is the 6th
> `AdapterInvocationError.kind` literal ... It is NOT formalized as
> an enum — `errors.py:43` keeps `kind: str` plain — but the docstring
> at `AdapterInvocationError` mentions only the first four; adding
> the new one to that docstring was deliberately skipped because (a)
> `missing-binary` is also absent from the docstring (added by this
> same cargo adapter earlier) so the docstring is already a sample
> rather than an exhaustive list, and (b) the brief's "ONE new kind"
> wording said to pick the closest existing kind first and only add
> a new one if none fits — minimizing churn over taxonomy debate.

**Not a slice defect** — the WORKLOG already calls this out as
deliberate, and the rationale is sound (minimize churn until a future
slice formalizes a StrEnum). Flagging only because if PM ever
schedules a "kind taxonomy cleanup" slice, this docstring is the
right starting point.

## Recommendations for PM

1. **Close the 2026-05-31 cargo-build-failure-polish slice as
   `passed`.** Source is clean; tests pass; mypy is green; gate
   matches Main Branch claim; all 8 scenarios + 5 edges verified.

2. **Authorize push of `58bb603`** if not already authorized — Main
   Branch is waiting per the verification doc's Next §3. The merge is
   clean, single-slice FF, zero conflicts; no commit-cleanup needed.

3. **Optionally fold Obs 1/2 doc nits into a Main Branch
   "verification-request self-validation" follow-up.** Pattern is
   recurring: in the prior cycle (cargo LCOV + typed metadata slot)
   Manual Test also flagged two predicted-path/field-name typos in
   the verification doc (Scenario 5 glob path + field name).
   Suggested mitigation: have Main Branch dry-run the verification
   doc's exact command snippets against the freshly-merged tip
   before filing, catching expected-output mismatches at the source.
   This is a quality-of-life improvement for Manual Test, not a
   process gap.

4. **Carry forward to the parallel-sibling Localization slice.** Per
   verification doc §"Parked work", the Localization fallback-modes
   slice (`a42ea87` on `novetest-localization-fallback-modes`) was
   kicked back with two defects. Two follow-up tasks already queued
   in `agent-comms/tasks/`:
   - `run-team-2026-05-31-cargo-llvm-cov-ignore-run-fail.md`
   - `localization-team-2026-05-31-aggregate-fixture-redesign.md`
   Both are independent of this polish slice; Manual Test will
   re-verify when they land.

5. **No `delivery-phasing.md` checkbox movement** — this is
   diagnostic UX polish, not a phase-gated feature (per task brief
   DoD §7 + verification doc §"What this slice does").

## Confirmation matrix

| Scenario | Subject | Verdict |
|---|---|---|
| 0  | Full pytest gate (714 + 5) | ✅ |
| 0b | mypy strict (71 files) | ✅ |
| 1  | `novetest run --coverage` happy path on cargo-test-basic-coverage | ✅ |
| 1b | Persisted `record.json` typed-slot round-trip | ✅ |
| 1c | `novetest inspect <run_id>` cross-engine flow | ✅ |
| 2  | `novetest run` (no coverage) on cargo-test-basic | ✅ (source correct; doc nit per Obs 1) |
| 3  | Two new polish unit tests | ✅ |
| 4  | Helper source matches doc verbatim | ✅ |
| 5  | Generic `unparseable-output` fallback still fires | ✅ |
| 6  | Cargo integration trio (basic + coverage + lcov-e2e) | ✅ |
| 7  | WORKLOG entry accuracy | ✅ |
| 8  | `kind: str` plain (no Literal/StrEnum) | ✅ |
| E1 | Substring-only detection | ✅ |
| E2 | Spawn-path label asymmetry lock | ✅ |
| E3 | Env-var override behavior unchanged | ✅ (source correct; doc nit per Obs 2) |
| E4 | No new `kind` literals beyond ONE | ✅ |
| E5 | Single helper, two callers | ✅ |

**Final verdict: passed.** The cargo adapter's diagnostic surface for
runtime misconfiguration is now fully covered; cargo v1 remains
feature-complete + E2E-verified through the polish.

---

Filed by: novetest-manual-test-team
Date: 2026-05-31
Cycle: 2026-05-31 single-slice (cargo build-failure heuristic polish)
       — Localization parallel sibling parked
