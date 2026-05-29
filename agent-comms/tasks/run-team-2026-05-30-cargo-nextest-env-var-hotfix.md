---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-30
slug: cargo-nextest-env-var-hotfix
related:
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - src/novetest/run/adapters/cargo_adapter.py
---

# Task: cargo adapter hotfix — set `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`

## TL;DR

The cargo adapter (commit `6d9f463`) **does not run** on a real
cargo-nextest 0.9.50+ host. `_build_child_env()` at
`cargo_adapter.py:373` does not set
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`, which nextest requires for
the `--message-format=libtest-json` flag the adapter passes. Every
cargo run on an equipped host fails with exit 95 + nextest's runtime
error `"libtest JSON output is an experimental feature and must be
enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1"`. The adapter
then misclassifies this as `adapter-unparseable-output` and exits 4.

Surfaced by the 2026-05-30 Manual Test cargo E2E sweep (Issue 1,
findings deleted at cycle close — reproducer inlined below for
self-containment).

Two-line source change + one unit test + docstring note.

## Scope

1. **`src/novetest/run/adapters/cargo_adapter.py:373`
   `_build_child_env()`** — add the env var assignment:

   ```python
   env = os.environ.copy()
   env["CARGO_TERM_COLOR"] = "never"
   env["RUST_BACKTRACE"] = "1"
   env["NO_COLOR"] = "1"
   env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"   # ← new
   return env
   ```

2. **Docstring note** at `_build_child_env()` explaining WHY this
   env var is required (1-2 sentences):

   - `cargo-nextest` ≥ 0.9.50 (our floor per
     `decisions/2026-05-25-supported-engine-matrix.md`) gates the
     `--message-format=libtest-json` flag behind this experimental
     env var.
   - Without it, nextest exits 95 with a runtime error and writes
     zero events; the adapter's build-failure heuristic then
     misclassifies the failure mode.

3. **Unit test** in `tests/unit/run/adapters/test_cargo_adapter.py`
   pinning the env var's presence in the dict returned by
   `_build_child_env()`. Model after the existing `CARGO_TERM_COLOR`
   / `RUST_BACKTRACE` / `NO_COLOR` assertion patterns in adjacent
   unit tests.

## Out of scope (do NOT touch)

- **Build-failure heuristic at `cargo_adapter.py:263`**. Manual
  Test surfaced this as a low-priority UX polish (more specific
  error code when nextest's stderr matches the env-var literal),
  but it is a separate slice, not load-bearing.
- **Issue 2 — `nextest_version` payload-stash convention** (the
  normalizer drops `payload["nextest_version"]`). RESOLVED
  2026-05-30 evening as **(b) typed-slot** — see
  `agent-comms/decisions/2026-05-30-native-result-metadata-slot.md`.
  A separate Memory/Run typed-slot slice lands AFTER this hotfix
  merges (per that decision §"Dispatch ordering" — both slices
  touch `cargo_adapter.py`, parallel would conflict). DO NOT amend
  `run/normalizer.py` or the `NativeResult` / `NativeEngineContext`
  shape in this hotfix.
- **Coverage LCOV parser dispatch on `engine_name == "cargo-test"`**.
  Coverage team carry-forward, independent slice.
- **Any change to `_build_child_env()`'s other 3 env vars** —
  surgical change only.

## Reproducer (verbatim from 2026-05-30 cargo sweep)

```sh
. "$HOME/.cargo/env"
cd /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic
rm -rf .novetest && novetest init --output json > /dev/null
novetest run --output json
echo "exit: $?"
```

**Pre-hotfix behavior:**
- exit `4`
- `ok: false`, `data: {}`
- `errors[0].code == "adapter-unparseable-output"`
- error message ends with the literal:
  `... error: libtest JSON output is an experimental feature and
  must be enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`

**Source path trace:**
- `cargo_adapter.py:138` (coverage path) and `:149` (plain path)
  pass `--message-format=libtest-json` to cargo-nextest.
- cargo-nextest 0.9.50+ rejects this flag unless
  `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` is in the child env.
- `cargo_adapter.py:373` `_build_child_env()` builds the child env
  from `CARGO_TERM_COLOR`, `RUST_BACKTRACE`, `NO_COLOR` only.
- nextest exits 95 with the stderr above.
- `cargo_adapter.py:263` build-failure heuristic misclassifies
  exit-95-with-no-events as `adapter-unparseable-output`.

## Proof-of-fix (verbatim from 2026-05-30 cargo sweep)

Same fixture, single env var injected via shell:

```sh
. "$HOME/.cargo/env"
cd /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic
rm -rf .novetest && novetest init --output json > /dev/null
NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 novetest run --output json
echo "exit: $?"
```

**Post-fix behavior (Manual Test observed):**
- exit `3` (1 failing test by design), `ok: true` (transport ok)
- 3 tests captured (matches fixture: 2 unit tests + 1 integration
  binary):
  - `cargo_test_basic::tests::test_add_passes` (passes)
  - `cargo_test_basic::tests::test_subtract_intentionally_fails`
    (fails by design)
  - `<integration_binary>::test_add_via_integration` (passes)
- `engine_name == "cargo-test"`
- `engine_version == "1.96.0"`
- Node IDs use `::` separator (libtest-json convention)
- Failure log artifact written; body contains `panicked at
  src/lib.rs:32:9` + the assertion message

**Integration tests with workaround:**
```sh
NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 uv run pytest -q \
  tests/integration/run/test_cargo_basic.py \
  tests/integration/run/test_cargo_coverage.py
# → 2 passed in 0.90s
```

The proof-of-fix demonstrates that the only missing piece is the
env var. The source change in this task brief makes the env var
unconditional inside the adapter.

## Pre-flight host check (MANDATORY before opening the handoff)

Per the load-bearing learning from this cycle's cargo sweep
(history §1): unit + integration tests on the host-absent path are
NOT a substitute for the host-present path. Before opening the
handoff:

```sh
. "$HOME/.cargo/env"
cargo nextest --version
# expected: 0.9.50 or newer (observed 0.9.137 on the equipped host)
uv run pytest -q tests/integration/run/test_cargo_basic.py tests/integration/run/test_cargo_coverage.py -v
# expected: 2 passed, 0 skipped, 0 failed
```

**Expected post-hotfix:**
- `cargo nextest --version` ≥ 0.9.50.
- Both cargo integration tests **RUN AND PASS** (not skip, not fail).
- Total runtime under ~3 min (cargo-llvm-cov path takes longer due
  to instrumentation).

**If either skips**, the host is not equipped per
`scripts/dev-host-setup.md` §4 — fix the host first; the hotfix
verification needs an equipped host.

**If either still fails** with the same
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON` error, the env var addition
didn't propagate — check the call sites that invoke
`_build_child_env()` are all routing through the modified function
(spawn paths must inherit the env).

## DoD

- [ ] `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` set in
      `_build_child_env()` at `cargo_adapter.py`.
- [ ] Docstring at `_build_child_env()` explains the requirement
      (1-2 sentences referencing nextest's libtest-json env-var
      gate).
- [ ] Unit test added pinning the env var's presence in the
      returned dict.
- [ ] `uv run pytest -q` full suite green.
- [ ] `uv run mypy` strict clean.
- [ ] Integration tests `tests/integration/run/test_cargo_*.py`
      both **RUN AND PASS** on the equipped host (pre-flight check
      above).
- [ ] No source / test file modified beyond `cargo_adapter.py` +
      the unit test.

## Handoff format

Standard handoff per your team charter at
`agent-comms/handoffs/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Pre-flight host check evidence** — record the exact `cargo
   nextest --version` line + the integration test pass output line.
3. **No `delivery-phasing.md` checkbox implications** (this is a
   bug fix to a landed adapter, not a new DoD-tracked feature).
4. **Open questions for PM** — anything you encountered that the
   freeze (`2026-05-30-localization-outcome-envelope-shape.md`) or
   convention decisions should clarify but this brief did not
   anticipate.

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md`, the new `agent-comms/` files, and `INDEX.md`
   alongside source. The PreToolUse hook will block the commit if
   any of `src/` or `tests/` is staged but `WORKLOG.md` is not.

## Cross-references

- **Cargo adapter execution-path decision**:
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
  §1 (nextest 0.9.50 floor + install hint — confirms which
  nextest version trip wire the env var fixes).
- **Polyglot host parity decision**:
  `agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md`
  §3 (closure triggers; this hotfix is what completes trigger (b)
  closure once the next Manual Test sweep verifies on the
  equipped host).
- **Cycle history with full context**:
  `agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
  §"Issues raised by the cargo sweep" + §"Cargo trigger-(b)
  status".
