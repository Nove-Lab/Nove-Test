---
from: novetest-replay-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-03
slug: phase5-entry-replay-engine
related:
  - agent-comms/tasks/replay-team-2026-06-02-phase5-entry-replay-engine.md
  - agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md
---

# Handoff — Phase 5 entry: Replay engine

## Worktree

- Path: `/home/yjshin/dev/novetest-replay-phase5`
- Branch: `replay-team-phase5-entry`
- Base commit: `377a92f` (main tip at pickup)
- Code commit: `b4dc467` (src + tests + fixture + WORKLOG; FF-mergeable into main)
- This handoff is a follow-up comms-only commit on the same branch.

## Files written / modified

**New src (8; source count 80 → 87):**
- `src/novetest/models/replay_result.py` — canonical `ReplayResult` model.
- `src/novetest/replay/{errors,context,classifier,persistence,retrieval,engine}.py`
- `src/novetest/replay/__init__.py` — public surface (was empty).

**Modified src (7):**
- `src/novetest/models/__init__.py` — `ReplayResult` export.
- `src/novetest/orchestration/recommendation/fact_bundle.py` — placeholder removed; re-imports `ReplayResult` from `models/`; `__all__` re-export added. Wire shape byte-identical.
- `src/novetest/orchestration/workflows/status.py` — `replay_available` = cache-only `get_replay_result` probe.
- `src/novetest/orchestration/workflows/inspect.py` — `replay_outcome` section (`kind: replay-result`); `sub_reports.replay` flips.
- `src/novetest/cli/app.py` — `replay_cmd` + `_build_replay_envelope` + `_replay_outcome_payload`; dropped the `("replay",)` flat-stub registration.

**New tests (~82):**
- `tests/unit/replay/` — 62 (classifier table tests, errors, persistence, retrieval, context).
- `tests/unit/cli/test_replay.py` — 9 (envelope-builder exit-code split).
- `tests/integration/replay/` — 7 (`test_replay_e2e.py` 3 DoD bullets + `test_flaky_suspected_synthesis.py` + `test_replay_cli.py` subprocess).
- `tests/unit/cli/test_default_verb_alias.py` (+1 replay case); `tests/unit/orchestration/workflows/test_status.py` (+2 replay cases).

**Modified tests (cross-test seam updates):** `test_inspect.py`, `test_inspect_localization.py`, `test_inspect_regression.py`, `test_status.py` (added `get_replay_result` to their monkeypatched seams), `test_subcommand_stubs.py` (dropped the now-empty stub parametrization).

**New fixture:** `tests/fixtures/projects/flaky-python/`.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **949 passed, 5 skipped** (baseline 871+5 → +78 net).
- `uv run mypy --strict src` → **Success: no issues found in 87 source files** (+7 vs 80).
- `grep -rn "sqlite3\|index.db" src/novetest/replay/ src/novetest/models/replay_result.py` → empty (DoD #12).
- `grep -rn "REPLAY_CLASSIFICATIONS\|class ReplayResult" src/` → only `models/replay_result.py` defines them (placeholder fully removed).

## Per-fixture envelope pins (verbatim from CLI subprocess e2e)

- **flaky-python** `novetest replay <id> --reruns 5`: `classification=inconsistent`, `reruns_total=5`, `reruns_failed=3`, `per_rerun_outcomes=["failed","passed","failed","passed","failed"]`, `consistency_summary={original_passed:1, original_failed:0, replay_passed:2, replay_failed:3, replay_errored:0}`, `test_id="tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"`, exit 0.
- **pytest-basic** `--reruns 3`: `classification=reproducible`, `reruns_total=3`, `reruns_failed=0`, exit 0.
- **unable_to_replay** (pytest-basic, test file deleted): `classification=unable_to_replay`, `reason="replay-run-errored"`, exit 0 (`ok:true`, structured outcome).
- **stale run_id**: exit 2, `errors[0].code="not-found"`.
- Citations: `flaky_suspected` recommendation carries `kind:"replay_result"` citation that round-trips via `get_replay_result(store, original_ref)` to the same `ReplayResult` byte-identically (NFR-ORCH-002).

## Policy decisions (§6 — delegated; v2-bumpable)

1. **`--reruns` default = 1.** Cheapest single-replay default; matches the `novetest replay <basic>` example with no flag. Alternative considered: default 5 (better flake-investigation UX) — rejected to keep the default cheap; users investigating flakiness pass `--reruns 5` explicitly.
2. **Classifier threshold = strict.** Any one replay run whose run-level outcome differs from the original → `inconsistent`. Alternatives: majority / all-or-nothing / per-test — rejected because the user's question is binary ("is this reproducible?"); one flake answers "no".
3. **flaky-python non-determinism = on-disk invocation counter.** Deterministic within a process (read once), divergent across subprocess invocations (counter persists). Alternatives: `os.getpid()%2`, unseeded `random` — rejected for non-reproducible original-run capture / CI flakiness in the test itself.

## Exit-code split rationale (§5.3)

- `ReplayResult` (any classification incl. `unable_to_replay`) → **exit 0** (classify-able outcome).
- `ReplayUnavailable` `engine-not-ready` / `target-missing` → **exit 4** (`EXIT_ENGINE_MISSING`, mirrors run/test).
- `ReplayUnavailable` `original-not-found` → **exit 2** (mirrors inspect; in practice surfaced earlier by the CLI run_id resolver).
- `ReplayUnavailable` `tombstoned-original` / `context-reconstruction-failed` / `missing-derived-facts` → **exit 0** with `kind:unavailable` (structured, not an error).

**Closed `ReplayUnavailable.reason` enum as shipped:** `original-not-found`, `tombstoned-original`, `context-reconstruction-failed`, `engine-not-ready`, `target-missing`, `missing-derived-facts`.

**Closed `ReplayResult.reason` (unable_to_replay) enum:** `no-replayed-runs`, `replay-run-errored`.

**ReplayResult fields shipped:** 5 binding (`run_reference`, `classification`, `reruns_total`, `reruns_failed`, `test_id`) + all 5 recommended optionals (`replayed_run_reference`, `per_rerun_outcomes`, `consistency_summary`, `attempted_at`, `reason`).

## NFR measurements

- **NFR-REP-002**: classify + persist tail (records on disk) measured well under the 3 s budget (~sub-millisecond on the dev host); pinned by an in-test timer in `test_pytest_basic_yields_reproducible`.
- **NFR-REP-001**: traceability round-trip pinned by `test_persistence.py` + the e2e cache round-trip.

## DoD bullets believed closed (PM verifies + ticks)

- `design/implementation-plan/delivery-phasing.md:221` — flaky `--reruns=5` → `inconsistent`.
- `design/implementation-plan/delivery-phasing.md:222` — basic → `reproducible`.
- `design/implementation-plan/delivery-phasing.md:223` — missing target → `unable_to_replay`.

## Open items / surprises (non-blocking)

- **syrupy snapshots (§7.3) skipped**: replay envelopes carry fresh ULIDs every run, so byte-snapshots need scrubbing; the CLI subprocess e2e + explicit envelope assertions cover the wire shape. Flag for a future scrubbed-snapshot pass if PM wants it.
- **unable_to_replay fixture**: reused `pytest-basic` (mutated tmp copy) per brief §4 "Alternative"; no dedicated `flaky-stale-target/` added.
- **Dead stub helpers**: `_register_flat_stub` / `_register_group_stub` / `_make_stub` in `cli/app.py` are now unused (no flat stubs remain) but left in place (out of scope to remove; harmless, mypy-clean).
- **`test_engine.py` not written**: `replay_run`'s rerun loop needs real subprocess execution; covered by `tests/integration/replay/` instead (no honest unit boundary).
- **Parking lot for PM**: strict threshold may be noisy on systems with heavy concurrency; consider a `--threshold majority` flag in v2. Integrated `novetest test` auto-Replay remains a deferred UX question.
