---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-30
slug: cargo-e2e-sweep
related:
  - agent-comms/tasks/manual-test-team-2026-05-30-cargo-e2e-sweep.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/history/2026-05-29-cargo-adapter-and-localization-cli-parallel-cycle.md
verdict: failed
---

# Findings: cargo adapter E2E sweep — trigger (b) re-verification

## Verdict — **failed** (one ship-blocking bug; one design-level
finding that materially changes the deferred decision input)

The headline outcome of trigger (b) (Step 1: integration tests no
longer skip → both PASS on an equipped host) **does not materialize**.
Both tests now RUN (good news), but both FAIL — and the failure mode
is the same root cause that blocks every other step in the sweep. The
cargo adapter as merged (`6d9f463`) does not work against
`cargo-nextest 0.9.137`, which is the version `scripts/dev-host-setup.md`
§4 just pinned. A single missing env-var line fixes everything; the
fix is two lines and I have proof-of-fix in this report. Steps 2-4 all
confirm the same diagnosis; Step 5 surfaces a separate, deeper finding
(the deferred-convention question is harder than the brief assumed).

## Plain-language summary for the CEO

This week the sweep was supposed to be a victory-lap re-run of the
cargo slice now that the host has Rust installed. Instead it surfaced
**one real, ship-blocking bug** in the cargo adapter and **one design
issue** worth pinning before next cargo work lands.

**The bug (Step 1-3, all the same root cause):** When the adapter
runs `cargo nextest run --message-format=libtest-json`, modern
nextest (0.9.50+, including the just-installed 0.9.137) refuses unless
the env var `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` is also set. The
adapter sets three other env vars (`CARGO_TERM_COLOR`, `RUST_BACKTRACE`,
`NO_COLOR`) but not this one — so nextest exits with a usage error
and writes zero events. The adapter then misclassifies this as
"likely build failure" and bubbles a `adapter-unparseable-output`
error with exit code 4. Every cargo run on an equipped host fails
the same way today.

I confirmed the fix by setting the env var manually:
`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 novetest run ...` produces a
perfectly clean envelope (3 tests, 2 passed, 1 failed by design, all
artifacts present, exit 3 as expected). The integration test suite
goes from 0/2 to 2/2 with the same one-line workaround.

**The design issue (Step 5):** The cargo adapter stashes
`nextest_version` in its `NativeResult.payload` so that PM can later
decide whether to make this a standard convention or amend
`NativeEngineContext`. But the normalizer that turns `NativeResult`
into the persisted `RunRecord` hardcodes
`metadata={"native_exit_code": <int>}` and drops every other payload
key. So the stashed `nextest_version` is invisible to every consumer
of the persisted run (`inspect`, `regression`, anyone reading
`record.json`). The "payload stash" pattern doesn't survive the
normalizer seam as it stands — which sharpens the deferred-convention
question PM needs to make.

## Pre-flight host check — ✅

```
cargo 1.96.0 (30a34c682 2026-05-25)
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)
cargo-llvm-cov 0.8.7
llvm-tools-x86_64-unknown-linux-gnu (rustup component installed)
```

All four toolchain components present and ≥ floor versions per
`scripts/dev-host-setup.md` §4. Host equipped per decision §3 trigger
(b) preconditions.

## Step 1 — integration tests RAN but FAILED — ❌ (headline)

```
uv run pytest tests/integration/run/test_cargo_basic.py \
              tests/integration/run/test_cargo_coverage.py -v
```

Result: **2 failed in 0.57s.** Both tests RAN (no longer SKIPPED — the
`_require_cargo_and_nextest` and `_require_cargo_nextest_and_llvm_cov`
guards correctly let them through on the equipped host). Both then
crashed at the same point with `AdapterInvocationError`:

```
novetest.run.errors.AdapterInvocationError:
cargo nextest exited 95 without starting any test (likely build failure);
stderr tail: error: libtest JSON output is an experimental feature
and must be enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1
```

The nextest error message is the smoking gun — it appears verbatim in
the adapter's error.

## Step 2 — basic envelope — ❌ (same root cause, exit 4 not 3)

```
cd tests/fixtures/projects/cargo-test-basic
novetest run --output json
```

- exit `4` (expected `3`)
- `ok: false`, `data: {}`
- `errors[0].code == "adapter-unparseable-output"`
- error message ends with the same `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`
  hint from nextest's own stderr

The clean `novetest init --output json` from before this step **does**
report `engine_readiness.state == "ready"`, `engine_version: "1.96.0"`,
`ecosystem: "rust"` — so the readiness path is unaffected. The bug
is strictly on the execution path.

## Step 3 — coverage envelope — ❌ (same root cause via coverage path)

```
cd tests/fixtures/projects/cargo-test-basic-coverage
novetest run --coverage --output json
```

- exit `4`
- `ok: false`
- `errors[0].code == "adapter-unparseable-output"`
- error: `cargo llvm-cov did not write .../coverage.lcov; stderr tail:
  ... exit status: 95 ...`

The cargo-llvm-cov wrapper forwards `--message-format=libtest-json` to
its inner nextest, which then trips on the same env var requirement
and exits 95, so no LCOV is written.

## Step 4 — engine-misconfigured (no nextest) — ✅

Moved `~/.cargo/bin/cargo-nextest` → `…/cargo-nextest.bak` for one
invocation. Both `init` and `run` correctly detected the missing
binary:

- exit `4` (`EXIT_ENGINE_MISSING`)
- `data.engine_readiness.state == "engine-misconfigured"`
- `data.engine_readiness.issues[0]` contains the verbatim install hint:
  > "`cargo nextest` is not installed (required by the cargo-test
  > adapter — there is no plain-text fallback per the Q3 decision).
  > Install with: `cargo install cargo-nextest --locked` (or use
  > `cargo binstall`)"
- `errors[0].code == "engine-engine-misconfigured"` (note: doubled
  `engine-engine-` prefix is consistent with how the orchestration
  layer prefixes engine-state errors; not a typo on the adapter side)

Matches `decisions/2026-05-29-cargo-adapter-nextest-primary.md` §1
install-hint contract verbatim. The `mv` was reversed; post-recovery
`cargo nextest --version` reports `0.9.137` cleanly — host left in a
clean equipped state.

This step is the only one not blocked by the Step 1-3 bug. It is
ship-quality.

## Step 5 — `nextest_version` is NOT in the persisted Run Record — ❌

To exercise this step at all, I had to apply the env-var workaround
(`NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1`) to get a successful run.
With that workaround the run completes (exit 3, 3 tests captured),
and:

```
RUN_RECORD=$(find .novetest/memory/runs -name record.json | sort | tail -1)
grep -i nextest "$RUN_RECORD"
→ (no matches)
```

The full `record.json` `metadata` block is exactly:

```json
"metadata": { "native_exit_code": 100 }
```

Nothing else. `nextest_version` is not in `metadata`, not in
`artifact_paths`, not at any nested location. The grep returns zero
matches in the entire file.

**Tracing this in source:** the cargo adapter does compute the
version and stash it
(`cargo_adapter.py:299` → `payload["nextest_version"] = nextest_version`),
but `run/normalizer.py:72` hardcodes
`metadata={"native_exit_code": native_result.returncode}` for every
engine — discarding the rest of the payload at the normalization
seam.

This materially changes the question PM has been deferring. The
"payload-stash convention" as currently implemented isn't a working
convention — it's a sink. Any field stashed there is unobservable to
every downstream consumer. So the deferred decision PM has been
holding ("payload-stash vs amend `NativeEngineContext`") is in fact a
choice between:
- (a) **codify the convention by fixing the normalizer** to merge
  selected payload keys (e.g. a reserved `payload["metadata_for_record"]`
  dict) into `RunRecord.metadata`, OR
- (b) **amend `NativeEngineContext`** (or `NativeResult`) with a
  proper `metadata: dict[str, str]` field that the normalizer copies
  through.

Both are tractable; both are ~10 lines of source change. But the
"do nothing — the payload stash is already a working convention" path
is not actually open, because the current state silently loses data.

**Subjective feel for an AI consumer (the prompt PM asked for):**
neither current behavior is acceptable for an agent. The payload
key invisibility means an AI trying to reason about "what nextest
version produced this run" cannot answer from the persisted
artifacts. Option (b) (proper `metadata` slot on the context, or on
`NativeResult`) is preferable for AI consumers because the type
system makes the intent legible at the contract layer — a free-form
"payload" dict that may-or-may-not contain certain keys is exactly
the kind of soft contract that AI code-gen handles badly.

## Bug — full reproducer + minimal-diff fix proof

### Reproducer

```sh
. "$HOME/.cargo/env"
cd /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic
rm -rf .novetest && novetest init --output json > /dev/null
novetest run --output json
# → exit 4, code adapter-unparseable-output, NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 hint in message
```

### Fix proof (same fixture, one env var)

```sh
. "$HOME/.cargo/env"
cd /home/yjshin/dev/Nove-Test/tests/fixtures/projects/cargo-test-basic
rm -rf .novetest && novetest init --output json > /dev/null
NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1 novetest run --output json
# → exit 3 (1 failing test by design), ok=true (transport ok), 3 tests captured,
#   engine_name="cargo-test", engine_version="1.96.0",
#   node IDs use "::" separator (e.g. cargo_test_basic::cargo_test_basic$tests::test_add_passes),
#   failure_reference points to native/failures/...log,
#   log body contains "panicked at src/lib.rs:32:9" and the assertion message
```

Integration tests with the same workaround: **2 passed in 0.90s**.

### Minimal source diff (2 lines)

In `src/novetest/run/adapters/cargo_adapter.py`, `_build_child_env()`
(line 373):

```python
env = os.environ.copy()
env["CARGO_TERM_COLOR"] = "never"
env["RUST_BACKTRACE"] = "1"
env["NO_COLOR"] = "1"
env["NEXTEST_EXPERIMENTAL_LIBTEST_JSON"] = "1"   # ← add this
return env
```

A docstring note explaining why this env var is required (nextest
requires it for `--message-format=libtest-json` as of 0.9.x) and a
unit test pinning the env-var presence would round out the slice.

## DoD checklist

- [x] Pre-flight host check — versions recorded
- [ ] Step 1 — both integration tests RAN ✅ but **FAILED** ❌ (the
      `_require_*` guards no-longer-skip is correctly observed; this
      is the trigger-(b) win as written. But the actual run fails, so
      this checkbox is half-met — calling it ❌ for clarity.)
- [ ] Step 2 — basic envelope does not contain the expected
      properties; instead surfaces `adapter-unparseable-output` with
      exit 4 (expected exit 3 with 3 tests captured)
- [ ] Step 3 — coverage envelope does not materialize; same root
      cause as Steps 1-2
- [x] Step 4 — engine-misconfigured surface verbatim, exit 4, host
      cleanly recovered after `mv` reversal
- [x] Step 5 — `nextest_version` **not present** in persisted Run
      Record; root cause traced to normalizer:72; this is a separate
      design finding that sharpens PM's deferred-convention question
- [x] Host left in a clean equipped state (re-checked
      `cargo nextest --version` → 0.9.137)

## Issues (2)

### Issue 1 — `NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1` not set in
`_build_child_env()`

- **Severity:** ship-blocker (every cargo run on a fully-equipped host
  fails)
- **Root cause:** `cargo_adapter.py:373` `_build_child_env()` omits
  the env var that nextest 0.9.x requires for the
  `--message-format=libtest-json` flag the adapter passes at
  `cargo_adapter.py:138` (coverage path) and `cargo_adapter.py:149`
  (plain path)
- **Symptom:** nextest exits 95 with stderr
  `"libtest JSON output is an experimental feature and must be
  enabled with NEXTEST_EXPERIMENTAL_LIBTEST_JSON=1"`. The adapter's
  build-failure heuristic (`cargo_adapter.py:263`) then misclassifies
  this as `unparseable-output`
- **Reproducer:** see "Bug — full reproducer" above
- **Fix:** 1-line env-var addition in `_build_child_env()` + 1 unit
  test pinning the env var's presence + docstring note. ~5 lines net
- **Verification:** with the workaround applied via shell env, exit
  3, 3 tests captured, all envelope invariants met, LCOV body has
  3 SF entries (arithmetic.rs, classifier.rs, +1 root)+3
  end_of_record + at least 1 `DA:N,0` uncovered line. Integration
  tests pass 2/2 in 0.90s

### Issue 2 — `nextest_version` payload-stash lost at normalizer seam

- **Severity:** medium (deferred-convention design finding; not a
  user-visible failure on its own, but the convention as
  implemented is broken)
- **Root cause:** `run/normalizer.py:72` hardcodes
  `metadata={"native_exit_code": native_result.returncode}` and
  drops every other `payload` key. The cargo adapter
  (`cargo_adapter.py:299`) stashes
  `payload["nextest_version"] = "0.9.137"` per the deferred
  convention but the normalizer never propagates it
- **Symptom:** `record.json.metadata` only ever contains
  `native_exit_code` — `nextest_version` is invisible to all
  downstream consumers
- **Reproducer:** Step 5 above
- **Fix candidate (a):** normalizer merges a reserved
  `payload.get("metadata_for_record", {})` dict into the `metadata`
  arg
- **Fix candidate (b):** add `NativeResult.metadata: dict[str, str]`
  (or amend `NativeEngineContext`) and have the normalizer copy it
  through

## PM follow-up requests

1. **Run team task — fix Issue 1 (cargo-nextest env-var).** Treat as
   a hotfix: 2-line source change in `_build_child_env()`, 1 unit
   test pinning the env-var assertion (mirror the existing
   `test_build_child_env_sets_*` patterns), docstring note. Re-run
   the cargo integration tests as the DoD signal. Findings here
   give the full reproducer + proof-of-fix to anchor the task.
2. **Convention decision — resolve Issue 2.** The "payload-stash vs
   amend `NativeEngineContext`" question PM has been deferring is
   now sharper: doing nothing means the data is dropped. My subjective
   read is candidate (b) (a typed `metadata: dict[str, str]` field
   on `NativeResult` or `NativeEngineContext`) is preferable for AI
   consumers, but PM's call.
3. **Coverage team carry-forward (already on the slate).** Step 3's
   `has_coverage_facts == false` finding is the documented
   carry-forward — Coverage's LCOV dispatch on `engine_name ==
   "cargo-test"` is the next slice that closes this. **No action this
   cycle**, just noting the expected-state is confirmed real.
4. **Re-run this sweep after Run team's hotfix lands.** Steps 1-3
   should flip to ✅ ✅ ✅ with no further changes; Step 5's design
   finding stays open until the convention decision is made.
5. **(Low priority) UX polish on the adapter's build-failure
   heuristic.** When nextest exits non-zero with a stderr that
   matches the literal `"NEXTEST_EXPERIMENTAL_LIBTEST_JSON"`, we
   could surface a more specific error code (e.g.
   `adapter-misconfigured-nextest`) rather than the generic
   `adapter-unparseable-output`. This is a "make the next bug
   easier to diagnose" investment, not load-bearing.

## What was tested — verbatim commands

All commands recorded above under their respective Step headings.
Setup used:
- `tests/fixtures/projects/cargo-test-basic` for Steps 2, 4, 5
- `tests/fixtures/projects/cargo-test-basic-coverage` for Step 3
- `~/.cargo/bin/cargo-nextest` ↔ `cargo-nextest.bak` toggle for
  Step 4 (reversed cleanly)

Fixture directories were left clean (`.novetest/` runtime
artifacts deleted; no source / fixture modifications). `git status`
clean post-sweep.

## Notes on protocol

Per the task brief — no handoff doc (no merge), no WORKLOG.md entry
(no source changes), only this findings doc gets committed.
