---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-31
slug: build-failure-heuristic-polish
related:
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Task: cargo build-failure heuristic — more specific error code on env-var-missing

## TL;DR

The cargo adapter's build-failure heuristic at
`src/novetest/run/adapters/cargo_adapter.py:263` (`if not
collect_coverage and not saw_test_started and result.returncode != 0`)
currently produces a generic `unparseable-output` error for ALL
zero-event non-zero-exit cases — including the recently-fixed
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` env-var-missing case (which
should never recur per the 2026-05-31 hotfix, but if a future
nextest version reverts the gate or a user manually overrides
the env var, the diagnostic should be surgical).

Polish: when nextest's stderr contains the literal
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON`, surface a more specific
error code so AI consumers and humans get a precise next-step
hint instead of generic "unparseable output".

Manual Test surfaced this as low-priority polish in the 2026-05-30
cargo sweep findings; carried forward through 2026-05-31 cycle
close history. **Parallel sibling to the Localization fallback-
modes slice** — zero file overlap.

## Why this slice exists (product framing)

The 2026-05-31 hotfix set the env var unconditionally in
`_build_child_env()` so the symptom should NOT surface under
normal operation. But:
- A user could manually set `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=0`
  in their shell env before invoking `novetest run` (the adapter's
  `env["..."] = "1"` overrides this — but the user might wonder
  why their override didn't work, and a specific error code helps
  diagnose).
- A future nextest version could rename or remove the env var.
  If they remove it AND start requiring something else, the same
  exit-95 + zero-events pattern recurs with a different stderr.
- The heuristic's current behavior maps multiple distinct failure
  modes to ONE error code (`unparseable-output`), making
  AI-agent root-cause analysis harder than necessary.

This is **diagnostic UX polish**, not a bug fix. The system works
correctly today; this slice improves the error story for adjacent
future scenarios.

## Scope (what this slice DOES)

### 1. Detect the env-var literal in stderr

**Where**: `src/novetest/run/adapters/cargo_adapter.py:263-273`
(the current `if not collect_coverage and not saw_test_started
and result.returncode != 0` block).

Add a stderr-text-match BEFORE the generic `AdapterInvocationError`
raise:

```python
if "NEXTEST_EXPERIMENTAL_LIBTEST_JSON" in stderr_text:
    raise AdapterInvocationError(
        f"cargo nextest exited {result.returncode} requesting the "
        f"NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 env var. The adapter "
        f"normally sets this — check that the parent process or "
        f"shell hasn't pre-unset it. stderr tail: {detail_source[-400:]}",
        kind="misconfigured-environment",
    )
```

The exact `kind` literal is **at implementer's discretion** — the
existing `kind` values in `AdapterInvocationError` should be the
reference. Pick the closest existing kind that means
"environment is configured wrong, this isn't a build failure"; if
none fits, add ONE new kind (e.g., `"misconfigured-environment"`
or `"engine-runtime-misconfigured"`). Document the choice in the
WORKLOG entry's "Gotcha" line.

Keep the existing generic `unparseable-output` fallback for
non-matching stderr (the heuristic's current behavior is still
correct for true build failures).

### 2. Symmetric coverage-path handling (optional, recommended)

The coverage path at `cargo_adapter.py:286-292` (`if collect_coverage
and not coverage_path.exists()`) has the same "exit non-zero, no
useful output" pattern. If the env var literal also appears in
stderr THERE, apply the same specific error. One-line addition.

If you implement, the coverage-path detection should come BEFORE
the existing `"cargo llvm-cov did not write {coverage_path}"`
message (env-var-missing is a more specific cause).

### 3. Unit test pinning the new behavior

**Where**: `tests/unit/run/adapters/test_cargo_adapter.py`

Add ONE test case: `test_build_failure_heuristic_surfaces_env_var_literal`.
Mock `run_subprocess` to return a fake `CompletedProcess` with:
- returncode = 95 (or any non-zero)
- stderr containing `"libtest JSON output is an experimental feature
  and must be enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1"`
- empty events.jsonl (zero test events parsed)

Assert the raised `AdapterInvocationError`:
- has the new `kind` value
- message contains the literal `NEXTEST_EXPERIMENTAL_LIBTEST_JSON`
- message mentions the env-var-override diagnosis (the
  "check that the parent process or shell hasn't pre-unset it"
  prose)

Mirror existing test patterns in
`test_cargo_adapter.py` (`test_build_failure_heuristic_*` or
adjacent tests).

## Out of scope (do NOT touch)

- **`_build_child_env()`** — the env-var assignment landed in
  the 2026-05-31 hotfix. Don't re-edit. The polish is on the
  ERROR-DETECTION side, not the prevention side.
- **Any other adapter** (pytest / jest / gotest) — they don't
  have analogous env-var-requirement runtime contracts. Polish is
  cargo-specific.
- **Removing the generic `unparseable-output` fallback** — it's
  still correct for true build failures (compilation errors,
  missing toolchain components, etc.). Polish adds a specific
  branch BEFORE the generic; doesn't replace it.
- **Adding new `AdapterInvocationError` kinds beyond what's
  needed for this one literal match** — over-engineering. One
  new kind (or reuse existing) is the right scope.
- **Integration test for this case** — would require contriving
  a broken env that the adapter overrides anyway. Unit test is
  sufficient.

## Pre-flight checks (before opening handoff)

1. **Full gate green** on equipped host:
   `uv run pytest -q tests/unit tests/integration`
   - Baseline at `ad31b2f`: **712 + 5** on equipped host, **676 +
     7** on Rust-less.
   - Your tip = baseline + 1 new test. No regressions.
2. **mypy strict clean**.
3. **Cargo integration tests still pass on equipped host** (the
   hotfix path):
   `uv run pytest -q tests/integration/run/test_cargo_*.py -v`
   → 2 passed. The polish must NOT regress the happy path.
4. **No new fixture or src file** unless adding 1 new `kind`
   value to `AdapterInvocationError` (which is just adding a
   string constant or enum member, not a new module).

## DoD

- [ ] New error branch in `cargo_adapter.py:263-273` block
      detects `NEXTEST_EXPERIMENTAL_LIBTEST_JSON` literal in
      stderr and raises with specific `kind`.
- [ ] (Optional but recommended) symmetric branch in coverage-path
      handling at `cargo_adapter.py:286-292`.
- [ ] One unit test pinning the new behavior.
- [ ] Existing generic `unparseable-output` fallback intact for
      non-matching stderr.
- [ ] Existing cargo integration tests still pass on equipped
      host.
- [ ] Full suite green, mypy strict clean.
- [ ] No `delivery-phasing.md` checkbox implications (this is UX
      polish, not DoD-tracked).

## Handoff format

Standard handoff at
`agent-comms/handoffs/run-team-2026-05-31-build-failure-heuristic-polish.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **`kind` choice rationale** — did you reuse an existing kind
   or add a new one? If new, what's the name?
3. **Did you implement the optional symmetric coverage-path
   branch?** Yes/no + 1-line rationale.
4. **Existing test count + 1 new** = stay regression-free.

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff.
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md` + new `agent-comms/` files + `INDEX.md`
   alongside source.

## Cross-references

- **Origin of the polish suggestion**: 2026-05-30 cargo E2E sweep
  findings (deleted at 2026-05-30 cycle close; rationale carried
  forward in `history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`
  §"PM follow-up requests" item 5).
- **The 2026-05-31 hotfix that fixed the env var unconditionally**:
  `agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`.
- **Parallel sibling slice (no file overlap)**:
  `agent-comms/tasks/localization-team-2026-05-31-fallback-modes.md`
  (Localization team — `src/novetest/localization/**` territory).
