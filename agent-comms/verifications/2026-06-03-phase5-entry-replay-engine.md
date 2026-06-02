---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-06-03
slug: phase5-entry-replay-engine
related:
  - agent-comms/tasks/replay-team-2026-06-02-phase5-entry-replay-engine.md
  - agent-comms/handoffs/replay-team-2026-06-02-phase5-entry-replay-engine.md
  - agent-comms/decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md
---

# Verification — Phase 5 entry: Replay engine

## Merged commits

- **`4e81d53`** — `feat(replay): Phase 5 entry — Replay engine + ReplayResult model + novetest replay verb` (rebased onto `b62554a`; was `b4dc467` on worktree).
- **`904ee0d`** — `comms: handoff for Phase 5 entry — Replay engine (worktree ready for FF-merge)` (rebased; was `171cf1f`).

FF-merged into `main` cleanly. Rebase was 1-commit-ahead (only `b62554a` marketing docs in between — zero overlap with `src/`, `tests/`, or fixtures). Pushed to `origin/main`.

## Source handoff

`agent-comms/handoffs/replay-team-2026-06-02-phase5-entry-replay-engine.md` — Replay team, 2026-06-03. Reports 949 passed + 5 skipped (baseline 871+5 → +78 net), mypy strict on 87 source files (+7 vs 80).

**Re-verified post-rebase on merged tip `904ee0d`:** I re-ran the gate after rebasing onto main; same counts (949 passed + 5 skipped, mypy 87 source files clean, 2 syrupy snapshots passed). The team's numbers held byte-identically through the rebase.

## What landed (slice scope)

**Phase 5 → 100% complete** (PM verifies + ticks `delivery-phasing.md:221-223`):

- **5 internal Replay APIs implemented**: `replay_run`, `reconstruct_replay_context`, `classify_replay_consistency`, `get_replay_result`, `check_replay_availability`.
- **`ReplayResult` model promoted** to `src/novetest/models/replay_result.py` (canonical, `dataclass(slots=True, frozen=True)`, `schema_version=1`, `to_dict`/`from_dict`). The transient placeholder in `fact_bundle.py` is removed and replaced by a re-import; wire shape byte-identical so existing `from ...fact_bundle import ReplayResult` keeps working.
- **`novetest replay <run_id>` CLI verb** lands (replaces the flat stub at the old `cli/app.py:1182`).
- **`flaky-python/` fixture** added (on-disk invocation-counter flakiness; deterministic within a process, divergent across subprocess invocations).
- **`flaky_suspected` recommendation category activated for real** (was mock-only); end-to-end synthesizer round-trip pinned by `tests/integration/replay/test_flaky_suspected_synthesis.py`.
- **Status / inspect surfaces flip**: `status.sub_reports.replay` becomes `"available"` when the latest run carries a replay_result.json; `inspect.replay_outcome` carries the discriminated `kind: "replay-result"` block.
- **Memory Entry availability flag** `has_replay_result` flips true for runs with a persisted `replay_result.json`.

**Out of scope, deliberately not done** (verifiers should NOT expect these):

- **NO SQLite anything** — no `index.db`, no `memory/migrations/`, no `import sqlite3` anywhere. Deferred per `decisions/2026-06-02-phase5-sqlite-deferred-until-cross-run-verb.md`.
- **NO `novetest reindex` verb.**
- **NO integrated `novetest test` Replay invocation** — `workflows/test.py` keeps `replay_result=None`; thus `novetest test` against `flaky-python/` produces `all_green` (verified: see Scenario E), NOT `flaky_suspected`. The `flaky_suspected` category fires only when something puts a real `ReplayResult` into a `FactBundle` (the integration test does this directly via the Python synthesizer API).
- **NO syrupy envelope snapshot** for `novetest replay` (replay envelopes carry fresh ULIDs per run, so byte-snapshots need scrubbing; the CLI subprocess e2e + explicit envelope assertions cover the wire shape).

**Replay team's three §6 policy decisions** (v2-bumpable, recorded in handoff for the future):

1. **`--reruns` default = 1** (cheap single replay; `--reruns 5` is the explicit flake-investigation idiom).
2. **Classifier threshold = strict** (any divergent rerun → `inconsistent`).
3. **`flaky-python` non-determinism source = on-disk invocation counter** (`.flaky_invocations` at project root; read once per subprocess, persisted across subprocesses).

---

## Verification scenarios

All scenarios assume `uv run novetest ...` unless noted. Replace `<run_id>` literals with ULIDs captured from your earlier `novetest run` outputs; each command emits a fresh ULID. Envelope literals below are **verbatim captures from merged tip `904ee0d` against fresh tmp workspaces**; the `run_id`, `created_at`, and `attempted_at` values will differ per execution but the structural shape MUST match.

### Scenario A — Gates (mandatory)

```bash
uv run pytest -q tests/unit tests/integration
uv run mypy --strict src
```

Expected:
- pytest: `949 passed, 5 skipped`. The 5 skipped are pre-existing (4 marked `s` near tail + 1 mid-run); none should be NEW skips introduced by this slice.
- mypy: `Success: no issues found in 87 source files`.

If either fails, **stop here and file a finding** — do not proceed to E2E scenarios.

### Scenario B — DoD bullet 1 (`delivery-phasing.md:221`): flaky-python `--reruns 5` → `inconsistent`

Materializes a deliberately-flaky fixture, captures the original (invocation 0 = even = pass), then replays 5×; the on-disk counter flips parity each subprocess so reruns alternate.

```bash
WS=$(mktemp -d)
cp -r tests/fixtures/projects/flaky-python "$WS/flaky-python"
cd "$WS/flaky-python"

uv run --project /home/yjshin/dev/Nove-Test novetest init
ORIG=$(uv run --project /home/yjshin/dev/Nove-Test novetest run tests/ | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['memory_entry']['run_record']['run_reference']['run_id'])")
echo "original run_id=$ORIG"

uv run --project /home/yjshin/dev/Nove-Test novetest replay "$ORIG" --reruns 5
```

**Empirical envelope on merged tip** (verbatim from probe; `run_id` / `created_at` / `attempted_at` will differ for you):

```json
{
  "command": "replay",
  "data": {
    "original_run_reference": {
      "created_at": 1780415641531,
      "run_id": "01KT4GNDXVD7Y1DHCQ58GEXC1R",
      "schema_version": 1
    },
    "replay_outcome": {
      "attempted_at": 1780415649772,
      "classification": "inconsistent",
      "consistency_summary": {
        "original_failed": 0,
        "original_passed": 1,
        "replay_errored": 0,
        "replay_failed": 3,
        "replay_passed": 2
      },
      "kind": "replay-result",
      "per_rerun_outcomes": [
        "failed", "passed", "failed", "passed", "failed"
      ],
      "reason": null,
      "replayed_run_reference": {
        "created_at": 1780415649012,
        "run_id": "01KT4GNN7MY0Y7QZWN286B0NCP",
        "schema_version": 1
      },
      "reruns_failed": 3,
      "reruns_total": 5,
      "test_id": "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit 0. Structural pins:
- `data.replay_outcome.kind == "replay-result"`
- `data.replay_outcome.classification == "inconsistent"`
- `data.replay_outcome.reruns_total == 5`
- `data.replay_outcome.reruns_failed >= 1` (typically 3 with starting parity; can be 2/3 depending on where the counter starts if you re-use a workspace)
- `data.replay_outcome.test_id == "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"` (the focal divergent test)
- `data.replay_outcome.reason is null` (reason is non-null only for `unable_to_replay`)
- `len(data.replay_outcome.per_rerun_outcomes) == 5` and outcomes are from `{"passed","failed","errored"}`
- `data.replay_outcome.replayed_run_reference.run_id` is a fresh ULID (the FIRST replay run's ref; per REQ-REP-004)

### Scenario C — DoD bullet 2 (`delivery-phasing.md:222`): pytest-basic `--reruns 3` → `reproducible`

A clean fixture with 3 always-passing tests; reruns must all pass.

```bash
WS=$(mktemp -d)
cp -r tests/fixtures/projects/pytest-basic "$WS/pytest-basic"
cd "$WS/pytest-basic"

uv run --project /home/yjshin/dev/Nove-Test novetest init
ORIG=$(uv run --project /home/yjshin/dev/Nove-Test novetest run tests/ | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['memory_entry']['run_record']['run_reference']['run_id'])")
uv run --project /home/yjshin/dev/Nove-Test novetest replay "$ORIG" --reruns 3
```

**Empirical envelope on merged tip:**

```json
{
  "command": "replay",
  "data": {
    "original_run_reference": {
      "created_at": 1780415619605,
      "run_id": "01KT4GMRGNTG2HRDVSK036CWNP",
      "schema_version": 1
    },
    "replay_outcome": {
      "attempted_at": 1780415625735,
      "classification": "reproducible",
      "consistency_summary": {
        "original_failed": 0,
        "original_passed": 1,
        "replay_errored": 0,
        "replay_failed": 0,
        "replay_passed": 3
      },
      "kind": "replay-result",
      "per_rerun_outcomes": ["passed", "passed", "passed"],
      "reason": null,
      "replayed_run_reference": {
        "created_at": 1780415625257,
        "run_id": "01KT4GMY193T5FE67TWBKN2BP6",
        "schema_version": 1
      },
      "reruns_failed": 0,
      "reruns_total": 3,
      "test_id": null
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit 0. Structural pins:
- `data.replay_outcome.classification == "reproducible"`
- `data.replay_outcome.reruns_failed == 0`
- `data.replay_outcome.test_id is null` (no focal divergent test)
- `data.replay_outcome.per_rerun_outcomes == ["passed", "passed", "passed"]`

### Scenario D — DoD bullet 3 (`delivery-phasing.md:223`): vanished target → `unable_to_replay`

Captures pytest-basic, then deletes the test files BEFORE replay; the workspace can no longer collect any tests (pytest exits 5, "no tests collected"), so each rerun errors and the classifier maps the all-errored aggregate to `unable_to_replay` (NOT `inconsistent`; NOT `ReplayUnavailable` — see the §1.1 spec note that `unable_to_replay` is a VALID classification at exit 0, not an error).

```bash
WS=$(mktemp -d)
cp -r tests/fixtures/projects/pytest-basic "$WS/pytest-basic"
cd "$WS/pytest-basic"

uv run --project /home/yjshin/dev/Nove-Test novetest init
ORIG=$(uv run --project /home/yjshin/dev/Nove-Test novetest run tests/ | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['memory_entry']['run_record']['run_reference']['run_id'])")

# Mutate AFTER capture: delete the test files.
rm tests/test_*.py

uv run --project /home/yjshin/dev/Nove-Test novetest replay "$ORIG" --reruns 3
```

**Empirical envelope on merged tip:**

```json
{
  "command": "replay",
  "data": {
    "original_run_reference": {
      "created_at": 1780415678566,
      "run_id": "01KT4GPJ36J1GSTWYWZ2YX3D92",
      "schema_version": 1
    },
    "replay_outcome": {
      "attempted_at": 1780415679645,
      "classification": "unable_to_replay",
      "consistency_summary": {
        "original_failed": 0,
        "original_passed": 1,
        "replay_errored": 3,
        "replay_failed": 0,
        "replay_passed": 0
      },
      "kind": "replay-result",
      "per_rerun_outcomes": ["errored", "errored", "errored"],
      "reason": "replay-run-errored",
      "replayed_run_reference": {
        "created_at": 1780415679207,
        "run_id": "01KT4GPJQ7EQX8EB39ZRYAGEH4",
        "schema_version": 1
      },
      "reruns_failed": 0,
      "reruns_total": 3,
      "test_id": null
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit **0** (not 1, not 2, not 4 — `unable_to_replay` is a VALID classification per REQ-REP-003). Structural pins:
- `data.replay_outcome.classification == "unable_to_replay"`
- `data.replay_outcome.reason == "replay-run-errored"` (closed enum: `{"no-replayed-runs","replay-run-errored"}` — `unable_to_replay` reasons, distinct from `ReplayUnavailable` reasons)
- `data.replay_outcome.per_rerun_outcomes == ["errored", "errored", "errored"]`
- `data.replay_outcome.reruns_failed == 0` — note the design: errored ≠ "failed-divergence", so the failed-count is 0 even though all reruns errored. The `replay_errored` counter in `consistency_summary` carries the count of errored reruns instead.

### Scenario E — Integrated `novetest test` against flaky-python does NOT trigger flaky_suspected (out-of-scope confirmation)

Confirms the brief's "out of scope" statement: integrated `novetest test` keeps `replay_result=None`, so flaky_suspected can only fire when a real `ReplayResult` is fed into the synthesizer's Python API.

```bash
# Continue from Scenario B's $WS (or re-stage a fresh flaky-python and `init`)
cd "$WS/flaky-python"
uv run --project /home/yjshin/dev/Nove-Test novetest test tests/
```

Expected (within `data.recommendations`):
- Exactly **1** recommendation with `category: "all_green"` (NOT `flaky_suspected`).
- This is correct behavior: the original test run passed (invocation 0 is even); without a Replay step in the workflow, the synthesizer has no `ReplayResult` to act on.

If you see `flaky_suspected` from `novetest test`, that's a defect — file it (the integrated workflow should NOT be running Replay yet; that's a deferred UX question per the brief §9 and Replay team's parking lot in the handoff).

### Scenario F — flaky_suspected fires via the Python synthesizer (real round-trip)

This is the "for real" activation of the `flaky_suspected` category. Phase 6 entry's mock-based unit tests for `match_flaky_suspected` continue passing unchanged; this scenario reaches the same trigger via a REAL `ReplayResult` produced by the merged Replay engine, then asserts the NFR-ORCH-002 citation round-trip.

The dedicated integration test that pins this end-to-end is:

```bash
uv run pytest -v tests/integration/replay/test_flaky_suspected_synthesis.py
```

Expected:
- 1 test passes: `test_flaky_suspected_fires_when_replay_result_inconsistent`.
- The test asserts: (i) `flaky_suspected` recommendation present, (ii) carries exactly one `kind: "replay_result"` citation, (iii) `get_replay_result(store, original_ref).to_dict() == result.to_dict()` byte-identically.

If you want to exercise it manually via the Python REPL, the workflow is in the test body — flaky-python → `run_target_in_store` → `replay_run(reruns=5)` → `build_fact_bundle(replay_result=<that>)` → `synthesize_recommendation(bundle)` → assert one rec has `category == "flaky_suspected"`.

### Scenario G — status / inspect / memory list surfaces

**inspect on the ORIGINAL run** (which has the cached replay_result):

```bash
# After Scenario B; $ORIG is still set to the flaky-python original.
cd "$WS/flaky-python"
uv run --project /home/yjshin/dev/Nove-Test novetest inspect "$ORIG"
```

Expected (within `data`):
- `data.replay_outcome.kind == "replay-result"` (the discriminated block from `inspect.py::_replay_outcome_section`; identical wire shape to `novetest replay`'s `data.replay_outcome`)
- `data.replay_outcome.classification == "inconsistent"`
- `data.replay_outcome.reruns_total == 5`
- `data.replay_outcome.test_id == "tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation"`
- `data.sub_reports.replay == "available"`
- `data.sub_reports` has 4 keys: `{"coverage", "localization", "regression", "replay"}`

**status against a workspace whose latest run has a replay_result.json:**

The `status.sub_reports.replay` field reports availability against the LATEST run (the workspace's most recent Memory Entry). Important subtlety: when you've just done `novetest replay`, the LATEST run in Memory is the LAST replay rerun (not the original); that rerun has NO `replay_result.json` of its own. So in the typical replay flow, `status.sub_reports.replay == "unavailable"` even though the ORIGINAL run shows replay-available via `inspect`.

Captured envelope on merged tip (after 5 replay reruns; status reflects the latest rerun, which lacks its own replay_result):

```json
{
  "command": "status",
  "data": {
    "latest_run_reference": {
      "created_at": 1780415649627,
      "run_id": "01KT4GNNTVFHFQC6CW4XS956S4",
      "schema_version": 1
    },
    "run_history_size": 6,
    "sub_reports": {
      "coverage": "unavailable",
      "localization": "unavailable",
      "regression": "unavailable",
      "replay": "unavailable"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

If you want to see `status.sub_reports.replay == "available"`, you need a workspace where the LATEST run is one that has its own `replay_result.json`. Easiest path: after `novetest replay`, run **nothing else** — the latest entry will be the last rerun. To get the original back to "latest", you'd have to engineer a workspace where the original is the only entry AND a replay_result has been written for it (i.e. `replay_run` was called but no further `run` happened). One way: build the `replay_result.json` manually via the Python API (`replay.persistence.write_replay_result`). Outside of that, the typical `replay` flow naturally leaves status "unavailable" — pin this as the working behavior, not a defect.

**memory list shows the replay reruns as first-class entries:**

```bash
cd "$WS/flaky-python"
uv run --project /home/yjshin/dev/Nove-Test novetest memory list
```

Expected:
- `data.count == 6` (1 original + 5 replay reruns; if you ran `novetest test` after Scenario E, count is 7).
- Each entry has `entry_id`, `run_record`, `has_coverage_facts`, `has_localization_findings`, `has_regression_facts`, `has_replay_result`.
- The ORIGINAL entry (oldest) has `has_replay_result: true`; every replay rerun (newer) has `has_replay_result: false`.
- The replay reruns' `status` alternates `"failed"` / `"passed"` matching `per_rerun_outcomes`.

Captured digest from probe (latest first):
```
  [0] id=<test run from Scenario E>  status=passed  has_replay_result=False
  [1] id=01KT4GNNTVFHFQC6CW4XS956S4  status=failed  has_replay_result=False  <- 5th rerun (latest)
  [2] id=01KT4GNNPQ3WABADKYA08YCENA  status=passed  has_replay_result=False  <- 4th rerun
  [3] id=01KT4GNNJAKQYPPPZT8VSZHSNG  status=failed  has_replay_result=False  <- 3rd rerun
  [4] id=01KT4GNNDW9RR0AQJWEFY9GYEV  status=passed  has_replay_result=False  <- 2nd rerun
  [5] id=01KT4GNN7MY0Y7QZWN286B0NCP  status=failed  has_replay_result=False  <- 1st rerun
  [6] id=01KT4GNDXVD7Y1DHCQ58GEXC1R  status=passed  has_replay_result=True   <- ORIGINAL
```

### Scenario H — Stale `run_id` → exit 2 not-found error

```bash
cd "$WS/pytest-basic"  # or any inited workspace
uv run --project /home/yjshin/dev/Nove-Test novetest replay 01STALEFAKE00000000000000NX
```

**Empirical envelope:**

```json
{
  "command": "replay",
  "data": {},
  "errors": [
    {
      "code": "not-found",
      "details": {},
      "message": "No Memory Entry for run_id='01STALEFAKE00000000000000NX'"
    }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

Exit **2** (`EXIT_USAGE`, mirroring `inspect`'s not-found path). Structural pins:
- `ok == false`
- `errors[0].code == "not-found"`
- `errors[0].message` contains the bad run_id literal.

### Scenario I — Default-verb alias does NOT eat `replay <run_id>`

`replay` is in the reserved verb set (`cli/app.py::_SUBCOMMAND_TOKENS`). The default-verb alias only kicks in for tokens NOT in that set (per Phase 6 entry slice). Sanity-pin that `novetest replay <run_id>` routes to the replay verb, NOT `test`.

```bash
cd "$WS/pytest-basic"
# These should produce a 'replay' command envelope (NOT 'test').
uv run --project /home/yjshin/dev/Nove-Test novetest replay 01STALEFAKE00000000000000NX 2>&1 | python3 -c "import json,sys;print('command=',json.load(sys.stdin)['command'])"
```

Expected: `command= replay`. If it prints `command= test`, the alias is mis-broken — file a defect.

Bare `novetest replay` (no run_id) is a Cyclopts usage error, NOT a default-verb-alias bug — it prints a framework error to stderr ("Command \"replay\" parameter \"--run-id\" requires an argument.") and exits non-zero. That's correct: `replay <run_id>` is a required-positional.

---

## Critical edge cases worth probing

1. **`--reruns 1` is the default — confirm cheap-default semantics.** `novetest replay <ok_run_id>` (no flag) should produce `reruns_total=1`. If it produces a different default, that contradicts the §6.1 policy in the handoff.

2. **`--reruns 0` boundary.** Try `novetest replay <ok_run_id> --reruns 0` against pytest-basic. Per the classifier (`unable_to_replay` when no/all-errored reruns), this should classify as `unable_to_replay` with `reason: "no-replayed-runs"` and `reruns_total: 0` (versus `replay-run-errored` for the Scenario D case where reruns happened but all errored).

3. **Replay against an originally-failed run.** The fixtures used here all have the original status=passed. Try `novetest run` against `pytest-failing/` (which has failing tests), grab its run_id, then `novetest replay --reruns 3`. The classifier semantics on a fixture whose original itself is non-deterministic vs deterministic-failing are worth pinning — particularly the `consistency_summary` shape when the original failed.

4. **`replay` against a tombstoned original.** Run `novetest memory delete <run_id>` (or whatever the equivalent tombstone path is), then try to replay it. Per the handoff's closed `ReplayUnavailable.reason` enum, this should surface `tombstoned-original` — exit 0 with `kind: "unavailable"` in `data.replay_outcome` (structured non-error). If instead you see an unhandled exception or a misleading "not-found", that's a defect surface worth filing.

5. **Engine-not-ready surface.** The brief specifies that `engine-not-ready` (e.g. running replay in a workspace where pytest is no longer installed in the target's resolution path) → exit 4 (`EXIT_ENGINE_MISSING`), mirroring `run`. Hard to materialize cleanly outside an empty-no-engine fixture; if you have time, try a workspace where the original was captured under one venv but the replay is attempted in a stripped venv. Stretch goal; skip if hard to reproduce.

6. **Citation round-trip across many reruns.** The integration test `test_flaky_suspected_synthesis.py` pins the round-trip for ONE replay attempt. Stretch goal: replay twice in a row (`novetest replay <orig> --reruns 5` twice), then check whether `get_replay_result(store, original_ref)` returns the LATEST result or the first one. The persistence is at `replay/results/run_<original_ulid>/replay_result.json` — a stable single file per original — so the second replay overwrites. Worth confirming.

7. **`flaky-python` parity drift.** The on-disk counter at `.flaky_invocations` persists across replays within the SAME workspace tmp. So if you re-run `novetest replay` against the SAME workspace twice, the second invocation's reruns start from a different counter value (you'll see a different `per_rerun_outcomes` pattern but still divergent → still `inconsistent`). Pin this as expected behavior, NOT a defect. Reset by `rm .flaky_invocations`.

8. **Determinism of `classify_replay_consistency`.** Pure function; same input records → same output `ReplayResult` byte-identically. The handoff claims this; the unit test under `tests/unit/replay/test_classifier.py` (457 lines, table-tested) pins it. If you want a CLI-level determinism probe: re-derive via the synthesizer's cache-only path (the Phase 6 entry slice introduced `build_test_outcome_from_run_id`) — but Replay's `get_replay_result` is the direct analog and already round-trips byte-identically per the integration tests.

---

## Anything that wasn't obvious during merge

- **Rebase was clean.** Only `b62554a` (marketing docs) was between the worktree base (`377a92f`) and main tip. Marketing changes touched only `design/website-plan/**` — zero overlap with `src/`, `tests/`, fixtures, or anything Replay touched. The rebase was mechanical; SHAs changed but content is byte-identical to the team's commits.
- **Worktree was on `replay-team-phase5-entry` branch** (not prefixed with `worktree-`); the FF-merge command had to use that local branch name. Branch is being deleted as part of cleanup.
- **No conflicts. No surgical edits. No new logic from me.**
- **Test gate passed BOTH on the original team commits (handoff claim: 949+5, mypy 87) AND on the rebased state (same numbers).** The rebase did not introduce any drift.
- **Out-of-scope confirmation is intentional in the verification doc.** The verification doc deliberately surfaces what is NOT done (no SQLite, no integrated-test Replay) so Manual Test does not chase phantom "missing" features. Two scenarios (E and the §"Out of scope" paragraph at top) make this explicit.
- **Status's `replay` surface has a working-as-designed nuance** (Scenario G): the typical replay flow leaves `status.sub_reports.replay == "unavailable"` because the latest run after a replay is the last rerun, which has no replay_result.json of its own. Only `inspect <original_run_id>` surfaces `replay: available`. This is documented because a naive reader of the brief might expect status to flip after `replay`.

---

## Post-verification cleanup (Main Branch already done)

- Worktree at `/home/yjshin/dev/novetest-replay-phase5` will be removed and its branch `replay-team-phase5-entry` deleted after this verification doc lands.
- INDEX.md regenerated.

End of verification.
