---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-05-31
slug: native-result-metadata-typed-slot
related:
  - agent-comms/tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - src/novetest/run/types.py
  - src/novetest/run/normalizer.py
  - src/novetest/run/adapters/cargo_adapter.py
---

# Handoff: typed `metadata` slot on `NativeResult` — Issue 2 closed

## TL;DR

Closes Issue 2 of the 2026-05-30 cargo E2E sweep by retiring the lazy
payload-stash convention in favor of a typed `metadata: dict[str, str]`
slot on `NativeResult`. Normalizer overlays adapter metadata onto
its own `native_exit_code` with a strict-raise guard for the reserved
key. Cargo adapter migrates from `payload["nextest_version"]` to
`metadata["nextest_version"]`. pytest / jest / gotest adapters audited
— no record-bound payload-stashes found, no migration needed. **Six
files modified, +229/-15 net, zero new source modules**, full suite
**679+7** (baseline 676+7, exactly +3 new tests, no regressions).

The end-to-end smoking gun proved by reading a real
`record.json` after `novetest run` against `cargo-test-basic`:
`metadata = {"native_exit_code": 100, "nextest_version": "0.9.137"}`.
Pre-migration the same path produced `{"native_exit_code": 100}` only —
the secondary-runner version silently dropped at the normalizer seam.

## Worktree

- **Path**: `/home/yjshin/dev/novetest-native-result-metadata-typed-slot`
- **Branch**: `worktree-run-team-native-result-metadata-typed-slot`
- **Base commit**: `4a39c92` (`comms: queue parallel Coverage slice — cargo LCOV dispatch`)
- **Tip commit**: TBD-after-commit (run `git -C <worktree> rev-parse HEAD`)

## Files written / modified

| File | Change | Lines (±) |
|---|---|---|
| `src/novetest/run/types.py` | Added `metadata: dict[str, str] = field(default_factory=dict)` to `NativeResult` frozen dataclass with 13-line docstring extension pinning the typed-slot contract. | +15 |
| `src/novetest/run/normalizer.py` | Added module-level `_RESERVED_METADATA_KEYS` constant; strict-raise guard inside `normalize_native_result` for reserved-key collisions; `metadata.update(native_result.metadata)` overlay; extended function docstring with "Metadata contract" paragraph; edited cargo payload-shape docstring to remove stale `nextest_version` payload key reference and note migration to typed slot. | +42 / −5 |
| `src/novetest/run/adapters/cargo_adapter.py` | Deleted `payload["nextest_version"]` stash; built local `metadata: dict[str, str] = {}` (conditional assign on probe success — typed slot's `str` forbids `None`); passed `metadata=metadata` kwarg to `NativeResult(...)`. | +15 / −1 |
| `tests/unit/run/adapters/test_cargo_adapter.py` | Migrated 2 assertions: `payload["nextest_version"]` → `metadata["nextest_version"]`. Locked migration target: `"nextest_version" not in payload`. Probe-failure path now asserts absence-not-`None`. | +20 / −3 |
| `tests/unit/run/test_normalizer.py` | Removed 5 stale `"nextest_version": "0.9.70"` keys from payload fixtures (no longer functional). Added `_native_result_with_metadata()` helper. **Added 3 new tests** pinning the overlay contract: positive (overlay), default (empty metadata → only `native_exit_code`), negative (reserved-key collision raises `ValueError`). | +138 / −5 |
| `tests/unit/run/test_engine.py` | Moved `"nextest_version": "0.9.70"` from `payload={...}` to typed `metadata={...}` kwarg in `fake_run_cargo` stub. | +5 / −1 |

## Adapter audit results (DoD §4)

Methodology: `grep -n "payload\[" src/novetest/run/adapters/*.py`
plus inspection of every `NativeResult(...)` construction site in each
adapter to verify nothing record-bound rides the raw payload dict.

| Adapter | Record-bound fields in `payload`? | Migrated? | Notes |
|---|---|---|---|
| `pytest_adapter.py` | None | No migration | `payload` is the raw `pytest-json-report` JSON object. Engine version captured separately on `NativeResult.engine_version`. No secondary runner. |
| `jest_adapter.py` | None | No migration | `payload` is the raw jest `--json` output. Engine version captured separately on `NativeResult.engine_version`. No secondary runner. |
| `gotest_adapter.py` | None | No migration | `payload = {"events", "packages", "failure_logs"}` — all three are per-test parsing state (normalizer consumes them directly). Engine version captured separately. No secondary runner. |
| `cargo_adapter.py` | `payload["nextest_version"]` | **Migrated to `metadata["nextest_version"]`** | Cargo's two-tier engine (cargo == primary, nextest == secondary runner). `engine_version` carries cargo; `nextest_version` rides typed slot. This was the unique case Issue 2 surfaced. |

Conclusion: the cargo case was indeed unique — Run team explicitly
applied the deferred lazy-extension convention from the 2026-05-29
nextest-primary decision §item 5 there, and only there. The other
three adapters never had a record-bound `payload[...]` stash to begin
with. Future engines (JUnit, dotnet, Rust slow-mode) inherit the
typed slot for free; reviewers should reject new `payload["<engine>_version"]`
patterns per the decision's binding directive.

## Pre-flight check evidence (DoD §"Pre-flight checks")

### Check #1 — Full gate green

```
$ uv run pytest -q tests/unit tests/integration
... (omitted dots for brevity)
1 snapshot passed.
679 passed, 7 skipped in 32.19s
```

Baseline at this cycle's tip (`4a39c92`) was 676+7. Delta = **+3 net = exactly the 3 new metadata-overlay tests in `test_normalizer.py`**. Zero regressions.

### Check #2 — mypy strict clean

```
$ uv run mypy
Success: no issues found in 70 source files
```

Source-file count unchanged from baseline (no new src modules added; `metadata` field rides the existing `NativeResult` type).

### Check #3 — Smoking-gun `record.json` grep

```
$ cd $(mktemp -d /tmp/novetest-metadata-smoking-gun-XXXX)
$ cp -r .../tests/fixtures/projects/cargo-test-basic/* .
$ PATH=$HOME/.cargo/bin:$PATH .venv/bin/novetest init
$ PATH=$HOME/.cargo/bin:$PATH .venv/bin/novetest run >stdout.json 2>stderr.log
$ python3 -c "import json; d=json.load(open('.novetest/memory/runs/2026/05/31/run_*/record.json')); print(d['metadata'])"
{
  "native_exit_code": 100,
  "nextest_version": "0.9.137"
}
```

`engine_name=cargo-test`, `engine_version=1.96.0` (cargo itself);
`metadata.nextest_version=0.9.137` (the secondary runner). Status
`failed` is the by-design failing test in the fixture — orthogonal to
the metadata check. **Pre-migration the same path would have produced
`metadata = {"native_exit_code": 100}` only** — exactly Issue 2's
symptom from the 2026-05-30 sweep.

### Check #4 — Cargo integration tests on equipped host (load-bearing)

```
$ cargo nextest --version
cargo-nextest 0.9.137 (75ddba7e9 2026-05-26)
$ cargo --version
cargo 1.96.0 (30a34c682 2026-05-25)
$ PATH=$HOME/.cargo/bin:$PATH uv run pytest -q \
    tests/integration/run/test_cargo_basic.py \
    tests/integration/run/test_cargo_coverage.py -v
collected 2 items
tests/integration/run/test_cargo_basic.py .       [ 50%]
tests/integration/run/test_cargo_coverage.py .    [100%]
2 passed in 0.83s
```

Both RAN AND PASSED on the equipped host — proves the metadata
migration didn't break the adapter's runtime contract.

## Verification table

| Gate | Baseline (`4a39c92`) | Tip | Delta | Status |
|---|---|---|---|---|
| Unit + integration full suite | 676 passed + 7 skipped | 679 passed + 7 skipped | **+3 / 0** | green |
| mypy `--strict` source files | 70 | 70 | 0 | green |
| Cargo integration on equipped host | 2 passed (env-var hotfix) | 2 passed | 0 | green |

## Commit message

```
refactor(run): add typed metadata slot on NativeResult; cargo migrated

Closes Issue 2 of the 2026-05-30 cargo E2E sweep
(`history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
§"Issue 2"). Per `decisions/2026-05-30-native-result-metadata-slot.md`
option (b): retire the lazy payload-stash convention in favor of a
typed `metadata: dict[str, str]` slot on the `NativeResult`
contract-layer type. Normalizer overlays adapter metadata onto its
own `native_exit_code` with a strict-raise guard for the reserved
key. Cargo adapter migrates `payload["nextest_version"]` to
`metadata["nextest_version"]`. pytest / jest / gotest adapters
audited — no record-bound payload-stashes found, no migration
needed.

End-to-end proof: `record.json.metadata` now carries
`{"native_exit_code": <int>, "nextest_version": "<version>"}`
after `novetest run` against a cargo workspace, where pre-migration
the same path silently dropped the secondary-runner version at the
normalizer seam.

Full suite 679+7 (baseline 676+7 → +3 new tests, no regressions).
mypy --strict clean, 70 source files.
```

## DoD bullets believed closed

All bullets from `tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md` §DoD believed closed by this slice:

- [x] `NativeResult.metadata: dict[str, str]` field added.
- [x] Normalizer overlay merges adapter metadata correctly.
- [x] `native_exit_code` reserved-key guard implemented + tested.
- [x] Cargo adapter migrated (`payload["nextest_version"]` → `metadata["nextest_version"]`).
- [x] pytest / jest / gotest adapters audited; migrations done where needed (none needed); audit results in handoff.
- [x] Unit tests for normalizer overlay + reserved-key guard.
- [x] Cargo adapter test asserts on `metadata["nextest_version"]`.
- [x] Pre-flight checks above all green.
- [x] `record.json` schema NOT bumped (confirmed by `grep` of fixture record.json files + clean full-suite run + additive nature of the field).
- [x] `mypy --strict` clean.
- [x] Full pytest suite green (676+7 baseline + 3 new tests = 679+7 tip, no regressions).

**No `delivery-phasing.md` checkbox implications** (per metadata-slot
decision §"What this decision does NOT decide" — structural refactor
of contract layer, not a phase-gated feature).

## Why these specific decisions (design rationale)

1. **Strict-raise over pop-and-warn for the reserved-key guard.** PM
   slightly preferred strict-raise at the decision; the project posture
   is visible-not-silent per `CLAUDE.md`. Strict-raise catches the
   bug at write time (adapter author sees the failure in their test
   suite, not after a Manual Test grep weeks later). Pop-and-warn
   would let a silent-data-drop bug propagate the same way the
   payload-stash convention did before this slice retired it. The
   guard is one branch + one frozenset check — cheap in steady state.

2. **`dict[str, str]`, not `dict[str, Any]`.** The decision pinned
   strict typing; this slice follows. Strings are what every adapter
   needs to stash (engine versions, configuration flags, profile
   names). Anything richer (counts, durations, structured payloads)
   either belongs on `summary_counts` / `test_results` (typed fields)
   or in `payload[...]` (per-engine catch-all). The strict typing
   forced one design choice in the cargo migration: `nextest_version`
   is `str | None` from the probe, so the assignment must be
   conditional. Absence in `metadata` now signals "probe failed" —
   richer than the historical `payload["nextest_version"] = None`
   pattern.

3. **Field placement on `NativeResult` (not `NativeEngineContext`).**
   The decision deferred placement to the implementing team. Placed
   on `NativeResult` because: (a) it's the wrapping type the
   normalizer already consumes; (b) `NativeEngineContext` is a
   pre-execution identifier (engine name + version), not a
   post-execution result; (c) `NativeResult` is already where
   per-run-instance data (returncode, timestamps, artifact paths)
   lives — `metadata` belongs in that cluster.

4. **Removed obsolete `"nextest_version": "0.9.70"` from 5 payload
   fixtures in `test_normalizer.py`** rather than leaving them
   harmless-but-misleading. Future readers of those fixtures would
   reasonably assume "nextest_version is a payload key" — exactly
   the misunderstanding this slice exists to retire. Clean is better
   than backwards-compatible for test fixtures.

## Open questions for PM

1. **Decision-doc + task-brief file path drift.** Both
   `decisions/2026-05-30-native-result-metadata-slot.md` and
   `tasks/run-team-2026-05-31-native-result-metadata-typed-slot.md`
   reference `src/novetest/models/native_result.py` as the file
   `NativeResult` lives in. The actual location is
   `src/novetest/run/types.py:80` (no `models/native_result.py`
   file exists). The cross-territory authorization in the task brief
   was therefore unnecessary — this slice was purely Run-territory.
   No corrective action requested for this slice (the implementation
   is correct and Memory team has no claim on `src/novetest/run/types.py`);
   flagging so the next decision-doc / charter-update cleanup pass
   can correct the references for future readers.

2. **No further questions blocking.** The decision was complete; the
   slice was small; the audit found exactly the cases it expected;
   the smoking gun ran cleanly. Nothing else surfaced that PM needs
   to weigh in on.

## Cross-references

- **Origin of Issue 2**:
  `agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
  §"Issue 2 — `nextest_version` payload-stash lost at normalizer seam".
- **Authoritative decision**:
  `agent-comms/decisions/2026-05-30-native-result-metadata-slot.md`
  (option (b), CEO-approved 2026-05-30 evening).
- **Dispatch-ordering predecessor (closed)**:
  `agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`
  (cargo env-var hotfix landed at `1e736cc`; this slice was binding-gated on it).
- **Cargo adapter execution-path constraints** (unchanged by this slice):
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`
  (item 5 there is now RESOLVED by the metadata-slot decision; no edit needed).
- **Parallel cycle slice (no file conflict)**:
  `agent-comms/tasks/coverage-team-2026-05-31-cargo-lcov-dispatch.md`
  (Coverage team consumes `coverage_lcov` artifact key on
  `engine_name == "cargo-test"`; this slice didn't touch any of
  Coverage's surface).
