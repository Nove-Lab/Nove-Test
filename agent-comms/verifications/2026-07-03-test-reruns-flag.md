---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-07-03
slug: test-reruns-flag
related:
  - agent-comms/handoffs/orchestration-team-2026-06-25-test-reruns-flag.md
  - agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md
  - agent-comms/questions/orchestration-team-2026-07-03-reruns-replay-api-mismatch.md
---

# Verification request: `novetest test --reruns N` + Replay integration

## Merged

- **Commits**: `0a6cddf` (code) + `c81a0f7` (comms) — FF-merged as slice 1/4
  of the 2026-07-03 batch (final batch HEAD carries all four slices).
- **Source handoff**: `orchestration-team-2026-06-25-test-reruns-flag.md`.
- **Merge mechanics**: pure FF off main `5e7d5b5` (branch base = main tip).
  Zero conflicts. Zero source overlap with the other three slices.

## Gate (on the merged tree)

- `env -u PYTHONPATH uv run mypy` → Success, 114 source files.
- `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` →
  slice gate 1373 passed / 47 snapshots; final batch tree **1418 passed /
  3 deselected / 47 snapshots** (the 3 deselects are the exonerated
  jest/Node-12 host-pollution trio, 2026-06-22 baseline; CI Ubuntu is
  binding).
- Pre-merge review (code-reviewer): **MERGE-OK, zero blocking findings.**
  Rename `FactBundle.replay_result` → `replay_results` grep-verified
  complete; default-0 path provably identical.

## Verification steps (all paths below observed live on the merged tree)

Setup for S1–S3 (flaky fixture; counter parity: even invocation passes,
odd fails; each native run increments the counter):

```bash
REPO=/home/yjshin/dev/aispace/Nove-Test
WS=$(mktemp -d)/ws && mkdir -p $WS
cp -r $REPO/tests/fixtures/projects/flaky-python/. $WS/
printf '1' > $WS/.flaky_invocations   # next run is odd -> original FAILS
cd $WS
env -u PYTHONPATH uv run --project $REPO novetest init
```

### S1 — flaky_suspected fires end-to-end (observed)

```bash
env -u PYTHONPATH uv run --project $REPO novetest test --reruns 2
```

Observed: **exit 3** (run outcome, NOT replay classification — the flag
only triggers on failed runs, so the happy flaky path always exits 3),
`ok: true`, `command: "test"`, and:

- `data.stage_eligibility.replay == "available"` (bare runs read `"not_run"`)
- exactly ONE `data.recommendations[]` entry with
  `category == "flaky_suspected"`:
  - `summary`: ``Test `tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation` flaky: 1/2 reruns failed.``
  - `slots` keys: `reruns_failed` (1), `reruns_total` (2), `run_reference`,
    `test_id`
  - `evidence_citations[].kind`: `["replay_result", "test_result"]`
- on disk: `.novetest/replay/results/run_<original_run_id>/replay_result.json`

### S2 — negative flag rejected, no native run (observed)

```bash
env -u PYTHONPATH uv run --project $REPO novetest test --reruns -1; echo $?
cat .flaky_invocations
```

Observed: **exit 2**, `ok: false`,
`errors[0].code == "invalid-flag"`, message
`Invalid --reruns=-1; expected a non-negative integer`. The counter file
is untouched (no native run executed; workflow never called).

### S3 — default-path identity

```bash
env -u PYTHONPATH uv run --project $REPO novetest test        # no flag
```

Observed on an all-pass workspace: exit 0,
`data.stage_eligibility.replay == "not_run"`. Bare vs `--reruns 0`
byte-identity is snapshot-pinned in
`tests/unit/cli/test_test_cmd_reruns_flag.py` (fixed seams); zero
pre-existing `.ambr` files were modified by the slice (2 new files,
3 snapshot entries).

### S4 — round-trip parity

`novetest inspect <run_id>` after S1 should fold the cached replay result
back in (re-derive path uses `replay/get_replay_result`), and
`novetest memory list` should show the replay reruns as first-class
entries (e2e pins count 3 for `--reruns 2`).

## Critical edge cases worth probing

1. **Whole-run granularity (deliberate deviation, PM question open):** one
   Replay attempt per invocation — NOT per failed test. Even if multiple
   tests diverge, at most ONE `flaky_suspected` hit naming one focal
   `test_id`. The brief's per-test loop was unimplementable against the
   shipped Replay API (`replay_run` has no `target=` param;
   `ReplayUnavailableError` does not exist; persistence is keyed by
   original run id). See the open ratification question.
2. **`--reruns N` on a fully passing run**: replay is skipped
   (`record_has_failed_tests` gate) — eligibility must byte-match the
   no-flag run, no replay dir entry.
3. **ReplayUnavailable path** (e.g. store/context not reconstructable):
   best-effort — `stage_eligibility.replay == "unavailable"` with reason;
   the test envelope still succeeds.
4. **Cross-team file**: `tests/integration/replay/test_flaky_suspected_synthesis.py`
   got a mechanical kwarg swap (`replay_result=result` →
   `replay_results=(result,)`) — Replay-team eyes welcome, assertions
   unchanged (reviewer-confirmed no weakening).
5. Reviewer note: handoff claimed "+3 NEW .ambr" — actually 2 new files
   carrying 3 snapshot entries; the merge-safety half (zero pre-existing
   snapshots modified) is confirmed.

## PM carry-forwards (not Manual Test scope)

- Ratify or kick back the whole-run adaptation
  (`questions/orchestration-team-2026-07-03-reruns-replay-api-mismatch.md`).
- e2e placement `tests/integration/cli/` vs brief's root — same carry-over
  as the reset cycle.
- User-doc pass for the new flag (envelope diffs in the handoff).
