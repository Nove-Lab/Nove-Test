---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
slug: run-cargo-adapter
created: 2026-05-29
related:
  - agent-comms/handoffs/run-team-2026-05-29-cargo-adapter.md
  - agent-comms/tasks/run-team-2026-05-29-cargo-adapter.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
---

# Verification: cargo nextest Native Engine adapter — Phase 3 adapter #2

## Merged commit

`6d9f463` — `feat(run): add cargo nextest Native Engine adapter (Phase 3 adapter #2)` (clean ff-merge onto `3094d1e`).

## Source handoff consumed

- `agent-comms/handoffs/run-team-2026-05-29-cargo-adapter.md` (run-team, 2026-05-29).

## Scope of the slice

Adds the FOURTH native engine adapter (after pytest + jest + go-test), moving the Phase 3 backlog **3/6 → 4/6**.

- New `src/novetest/run/adapters/cargo_adapter.py` (~310 lines) — `run_cargo` resolves `cargo` via `shutil.which`, spawns `cargo nextest run --message-format=libtest-json --no-fail-fast --workspace [target]` (or the `cargo llvm-cov nextest --lcov --output-path <...> --no-fail-fast --workspace --message-format=libtest-json [target]` coverage variant), line-by-line stream-parses libtest-json NDJSON, writes per-test failure logs + canonical `events.jsonl`.
- `engine_selector.py` `_IMPLEMENTED_ECOSYSTEM_TO_ENGINE["rust"] = "cargo-test"`.
- `engine.py` `_invoke_adapter` 4th branch on `"cargo-test"`.
- `readiness.py` new `_assess_cargo_readiness` (states: engine-missing / engine-misconfigured / ready).
- `normalizer.py` `_normalize_cargo_payload` + `_CARGO_EVENT_TO_OUTCOME` map.
- 2 new fixture trees (`cargo-test-basic` + `cargo-test-basic-coverage`).
- 5 test files extended/added (+29 net unit passes + 2 cargo integration skips on no-toolchain boxes).
- `design/implementation-plan/engine-adapters.md` §5 narrowed per the Q3 decision.

**No models/, no orchestration/, no cli/, no coverage/ changes.** Adapter-only slice.

## Test-gate result on the merged tip

```
uv run pytest -q tests/unit tests/integration → 667 passed, 5 skipped (after BOTH 2026-05-29 slices merged)
uv run mypy                                    → Success: no issues found in 70 source files (strict)
```

The 5 skips: 3 pre-existing Node-dependent jest integration tests + 2 new Rust-dependent cargo integration tests (no Rust toolchain on this dev box).

## Wire shapes pinned by running the merged code

This dev box has **no Rust toolchain installed** (`cargo` absent from PATH). The probes below cover the no-toolchain readiness path; full coverage of the running-cargo paths is the integration suite's job (unit tests at the subprocess seam) PLUS your job on a real Rust box.

### Readiness no-toolchain envelope (probed)

`novetest run --output json` against `tests/fixtures/projects/cargo-test-basic` with no `cargo` on PATH:

```json
{
  "command": "run",
  "data": {
    "engine_readiness": {
      "ecosystem": null,
      "engine": null,
      "engine_version": null,
      "evidence": ["Cargo.toml"],
      "issues": ["`cargo` not found on PATH; install Rust toolchain from https://rustup.rs"],
      "state": "engine-missing"
    }
  },
  "errors": [
    {
      "code": "engine-engine-missing",
      "details": {},
      "message": "engine readiness state: engine-missing (engine=(none detected))"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit code: `0` at the shell (the orchestrator treats engine readiness as a soft failure surfaced in JSON; `ok: false` is the machine signal).

Key paths to keep stable in your scenarios:
- `data.engine_readiness.state` ∈ {`engine-missing`, `engine-misconfigured`, `ready`}.
- `data.engine_readiness.evidence` carries the detection-evidence paths (`["Cargo.toml"]` when only Cargo.toml drove selection).
- `data.engine_readiness.issues` is the human-readable issue list.
- Envelope `errors[*].code` is `engine-<state>` form — i.e. `engine-engine-missing` / `engine-engine-misconfigured` on the failure paths. Don't write a scenario that asserts a bare `engine-missing` code at envelope level.

### Cargo adapter `NativeResult.payload` keys (from source — see `src/novetest/run/adapters/cargo_adapter.py`)

When the adapter completes (cargo present + at least one test event observed), it returns a `NativeResult` whose `payload` carries:

- `nextest_version: str` — stashed in `payload`, NOT in `NativeEngineContext` (the latter is a frozen dataclass with no extension slots; this is the handoff-flagged surprise — PM decides whether to codify the payload-stash convention or amend the model in a follow-up).
- The per-test events buffered for `events.jsonl` artifact emission.

### Artifact paths registered (from source)

- `events.jsonl` — canonical libtest-json NDJSON stream (always).
- `failures/<safe>.log` — per-failing-test stdout/stderr capture. Filename safety: `/ → _`, `: → _`, `\ → _` (so Rust's `::` module separator becomes `__` naturally — e.g. `my_crate::tests::test_bad` → `my_crate__tests__test_bad.log`).
- `coverage.lcov` — emitted ONLY on `--coverage` path (LCOV-only emission for v1 per Q3 decision §5).

## Verification steps for Manual Test

### 1. No-toolchain readiness probe (no cargo install required)

```bash
# Stand up an isolated SUT copy and store.
PROBE=/tmp/novetest-manual-cargo && rm -rf "$PROBE" && mkdir -p "$PROBE"
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/cargo-test-basic "$PROBE/sut"
cd "$PROBE/sut"
/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest init --output json | jq .data.store_state
# Expect: "ready"

/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest run --output json | tee out.json
jq '.data.engine_readiness' out.json
# Expect state=engine-missing, evidence=["Cargo.toml"], issues mentioning install URL.
# Expect envelope ok=false, errors[0].code=engine-engine-missing.
```

Verify the issue message points users at https://rustup.rs verbatim — text drift here breaks adapter-install hint discipline.

### 2. With cargo + nextest installed — basic run path

If a Rust box is available, install `rustup`, `cargo nextest` (`cargo install cargo-nextest`), then:

```bash
/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest run --output json | jq '.data.memory_entry.run_record.summary, .data.memory_entry.run_record.engine_name'
# Expect: summary with failed=1 (the deliberately-failing test in cargo-test-basic) + passed≥3 + total=4ish
#         engine_name="cargo-test"
```

Then enumerate node_ids:

```bash
jq -r '.data.memory_entry.run_record.test_results[] | "\(.outcome)\t\(.node_id)"' out.json
```

Expected node_id conventions to confirm:
- Library-test node_ids use Rust's `::` module separator (e.g. `cargo_test_basic::tests::test_*`).
- Integration-test binary node_ids carry the binary name (the per-binary `--` substring convention) — this is what `test_cargo_integration_test_node_id_distinguishes_binary` locks down at the unit level; please confirm on a real box.

### 3. Coverage path (cargo-llvm-cov required)

`cargo install cargo-llvm-cov` and add the `llvm-tools-preview` rustup component, then:

```bash
cp -r /home/yjshin/dev/aispace/Nove-Test/tests/fixtures/projects/cargo-test-basic-coverage /tmp/manual-cargo-cov/sut
cd /tmp/manual-cargo-cov/sut
/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest init --output json > /dev/null
/home/yjshin/dev/aispace/Nove-Test/.venv/bin/novetest run --coverage --output json | tee covout.json
jq '.data.memory_entry.run_record.summary' covout.json
# Confirm the failing test still surfaces as failed (NOT as a typed adapter error)
# even on the coverage path. This validates the "build-failure detector
# suppressed in coverage mode" carve-out (handoff §Open items #3).
```

Then verify the LCOV artifact exists and was registered:

```bash
jq -r '.data.memory_entry.run_record.artifact_paths' covout.json
# Expect a coverage_lcov entry pointing at <artifact_dir>/coverage.lcov
ls -la /tmp/manual-cargo-cov/sut/.novetest/run/artifacts/run_*/coverage.lcov
```

### 4. Misconfigured paths (probe each readiness state)

These map to the four `_assess_cargo_readiness` branches:

- **engine-missing**: remove `cargo` from PATH (or test on a non-Rust box). Step 1 above covers this.
- **engine-misconfigured-no-Cargo.toml**: remove `Cargo.toml` from a workspace and run. State should be selection-side (`unknown-ecosystem`) — confirm what `engine_readiness` looks like in that case.
- **engine-misconfigured-no-nextest**: have `cargo` but uninstall `cargo-nextest`. State should be `engine-misconfigured`, issue mentioning nextest install hint.
- **engine-misconfigured-broken-cargo-version**: harder to reproduce; the parser test (`_parse_cargo_version`) covers it at the unit level.

### 5. `nextest_version` stash location

After a successful run with cargo+nextest, inspect:

```bash
jq -r '.data.memory_entry.run_record.artifact_paths, .data.memory_entry.run_record.engine_version' out.json
```

The handoff flagged that `nextest_version` lives in `NativeResult.payload`, NOT in `NativeEngineContext` (which is a frozen dataclass without extension slots). **PM action**: confirm via memory inspection where it actually surfaces in the persisted Run Record. If it's NOT exposed at all in the Run Record envelope, file that as a finding — downstream consumers (Coverage LCOV parser, Localization) may need it.

## Critical edge cases worth probing

1. **Coverage-mode failing-test detection (handoff §Open items #3).** Run `--coverage` with the basic fixture's failing test. Expected: Run Record `status="failed"`, `summary.failed=1`. NOT expected: a typed `unparseable-output` adapter error. If the latter, the build-failure-detector carve-out needs review.

2. **`--message-format=libtest-json` on coverage path (handoff §Open items #4).** Forwarded to nextest under llvm-cov. If your cargo-llvm-cov version rejects this flag, the run will fail with a clear nextest error in stderr → typed `unparseable-output`. Without the flag, coverage mode loses ALL TestResult rows (LCOV becomes the only output), which is strictly worse. Probe a version that DOES accept it, and a version that REJECTS it if available.

3. **Per-test failure log filenames.** Confirm the `::` → `__` Rust safety pass: `my_crate::tests::test_bad` becomes `my_crate__tests__test_bad.log` under `<artifact_dir>/native/failures/`. The handoff lists this as the safety pass; verify there's no double-encoding (no `____` or `_:_`) on a real run.

4. **Integration-test binary node_ids.** Rust integration tests live in `tests/<name>.rs` and produce a per-binary node_id. The handoff's added unit test `test_cargo_integration_test_node_id_distinguishes_binary` pins the `--`-substring convention. On a real box, verify two different integration-test files produce distinct node_id prefixes that downstream Localization can disambiguate.

5. **`--coverage` without `cargo-llvm-cov`.** Should surface as `engine-misconfigured` (not as a runtime crash). The handoff says "absence surfaces as `engine-misconfigured` via the LCOV-not-emitted check" — but that's a post-run detection, not a pre-run readiness probe. Confirm which one fires.

## PM bookkeeping drift (informational, not your job)

The handoff flags:
- **Supported-engine matrix amendment** — add a Rust row to `decisions/2026-05-25-supported-engine-matrix.md` (handoff §"Supported-engine-matrix proposal").
- **`nextest_version` convention decision** — codify payload-stash OR amend `NativeEngineContext` in a future `models/` slice.
- **CI Rust cell** — Release team adds a Rust cell when next touching CI workflows.
- **Coverage engine LCOV parser slice** — dispatched on `engine_name == "cargo-test"`; until this lands, `--coverage` produces a Run Record with `coverage_lcov` artifact but `has_coverage_facts` stays `False`. Natural next slice.

These are PM/Release follow-ons, NOT items for Manual Test to verify or chase.

## Notes from the merge

- Cargo branch base was `3094d1e` (current main tip); merge was a clean fast-forward — no conflicts.
- Cargo did not touch any file in the localization-cli slice's edit set (no content conflicts between the two parallel slices).
- The WORKLOG.md and INDEX.md conflicts that materialized during the localization-cli rebase are documented in that verification doc.
