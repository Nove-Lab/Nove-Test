---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-25
slug: test-reruns-flag
related:
  - agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md
  - agent-comms/tasks/orchestration-team-2026-06-24-reset-verb.md
---

# Task: Orchestration — `novetest test --reruns N` opt-in flag + Replay integration

- **Owner**: novetest-orchestration-team
- **Status**: pending
- **Created**: 2026-06-25
- **Pinned decision**: `agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md`
- **Phase**: ships AFTER the `reset` verb cycle merges. Do not start until `reset` is on `main`.

## Goal

Add the `--reruns N` opt-in flag to `novetest test`, wire the integrated workflow to invoke `Replay` for each failed test when `N > 0`, and thread `ReplayResult`s into `FactBundle.replay_result` so the existing `match_flaky_suspected` matcher in `src/novetest/orchestration/recommendation/categories.py` becomes reachable through a single user command.

## Why

The `flaky_suspected` recommendation category is currently unreachable from any user-issued command. The matcher (`match_flaky_suspected`) is wired in code and exhaustively unit-tested but always returns `[]` for real runs because `bundle.replay_result` is always `None` — the integrated `novetest test` workflow never calls Replay. This task closes that gap with the smallest possible surface: an opt-in flag on the existing `test` verb.

## Scope

### In scope (you do this)

#### 1. Flag wiring in `src/novetest/cli/app.py`

Find the existing `test_cmd` handler (around line 1252). Add `reruns` as an additional keyword-only `Annotated[int, Parameter(...)] = 0` parameter, mirroring how `--coverage` / `-c` is wired in `run_cmd` at line 240. Required behavior:

- Default `0` = current behavior preserved byte-for-byte.
- Reject negative integers at flag-parse time (rely on cyclopts validation; if cyclopts does not enforce non-negative natively, add a runtime check that emits `errors[0].code = "invalid-flag"` with exit 2, mirroring the `--formula` invalid-value pattern in `localization_cmd`).
- Pass the resolved `reruns` value to the integrated workflow (next step).

#### 2. Sub-workflow wiring in `src/novetest/orchestration/workflows/test.py`

After the existing Run-Coverage-Regression-Localization sequence completes and BEFORE the synthesizer is invoked:

```python
if reruns > 0:
    failed_test_ids = [
        t.node_id for t in run_record.test_results
        if t.outcome in {"failed", "errored", "error"}
    ]
    replay_results = []
    for test_id in sorted(failed_test_ids):                  # deterministic order
        try:
            rr = await replay_run(
                store,
                run_record.run_reference,
                target=test_id,                              # single-test scope
                reruns=reruns,
                timeout=600.0,
            )
            replay_results.append(rr)
        except ReplayUnavailableError:
            # Partial failure: skip this test, keep going. Synthesizer
            # handles missing replay_result gracefully.
            continue
    # Wire into FactBundle.
    fact_bundle.replay_result = replay_results               # see step 3
```

The exact shape of `FactBundle.replay_result` (single value vs list) is currently a single `ReplayResult`-or-`None` per `match_flaky_suspected`. **You will need to extend `FactBundle` to hold a list** — see step 3.

#### 3. `FactBundle` extension in `src/novetest/orchestration/recommendation/fact_bundle.py`

Current shape: `replay_result: ReplayResult | None`. With `--reruns N > 0` and multiple failed tests, we need multiple results.

**Recommended extension** (smallest delta to match the matcher's expectations):

```python
@dataclass(slots=True, frozen=True)
class FactBundle:
    ...
    replay_results: tuple[ReplayResult, ...] = ()  # NEW (renamed from singular)
```

Then update `match_flaky_suspected` in `categories.py` to iterate over `bundle.replay_results` and emit one `CategoryHit` per result classified `"inconsistent"`:

```python
def match_flaky_suspected(bundle: FactBundle) -> list[CategoryHit]:
    hits = []
    for rr in bundle.replay_results:
        if rr.classification != "inconsistent":
            continue
        ...
    return hits
```

**This renames the field on `FactBundle`** — check every read site and update. Use grep to confirm coverage.

Document the rename in `design/workflows/orchestration.md` and the synthesizer's docstring.

#### 4. Tests

- `tests/unit/cli/test_test_cmd_reruns_flag.py`:
  - `--reruns` flag parsing: 0 (default), 1, 5, 100 all accepted.
  - `--reruns -1` → exit 2, `errors[0].code = "invalid-flag"`.
  - `--reruns 0` (default): byte-identical envelope to current `novetest test` output (snapshot test against the existing test_cmd snapshot).
- `tests/unit/orchestration/workflows/test_workflow_reruns_integration.py`:
  - With 1 failed test + `--reruns 5`: synthesizer receives a `replay_results` tuple of length 1.
  - With 0 failed tests + `--reruns 5`: replay loop is skipped; envelope shape matches the no-`--reruns` happy path.
  - Partial replay failure (one of two failed tests raises `ReplayUnavailableError`): the other test's replay result still reaches the synthesizer; the envelope still emits cleanly.
- `tests/unit/orchestration/recommendation/test_match_flaky_suspected_list.py`:
  - Update existing matcher tests to use the new `replay_results: tuple[...]` shape.
  - Add a multi-result case: 2 inconsistent + 1 reproducible → 2 `flaky_suspected` hits, in deterministic order.
- `tests/integration/test_test_cmd_with_reruns.py`:
  - End-to-end: fixture project with 1 deliberately-flaky test (e.g., a test that fails 2 of 5 runs based on a counter file). `novetest test --reruns 5` produces a `flaky_suspected` recommendation. Verify against snapshot.
- Snapshot pin: update existing test verb snapshots to confirm the no-`--reruns` path is unchanged; add a new snapshot for the `--reruns` happy path.

### Out of scope (NOT your job)

- A separate `novetest reanalyze <run_id>` verb.
- Auto-replay-on-every-test behavior.
- Tuning of replay timeout aggregation.
- Marketing demo / website docs update (PM handles after merge).
- MCP transport for the flag (Phase 7).

## Pinned file list

- **Edit**: `src/novetest/cli/app.py` (one flag added to one function), `src/novetest/orchestration/workflows/test.py` (sub-workflow insertion), `src/novetest/orchestration/recommendation/fact_bundle.py` (field rename + type change), `src/novetest/orchestration/recommendation/categories.py` (matcher iteration update), `tests/unit/orchestration/recommendation/test_categories.py` (existing matcher tests).
- **Create**: `tests/unit/cli/test_test_cmd_reruns_flag.py`, `tests/unit/orchestration/workflows/test_workflow_reruns_integration.py`, `tests/integration/test_test_cmd_with_reruns.py`.
- **Update doc**: `design/workflows/orchestration.md` — add a "Integrated replay sub-workflow" section under the `test` verb.

Do NOT touch `src/novetest/memory/**` (Memory team territory; no Memory changes needed). Do NOT add new verbs.

## Acceptance criteria

- All new tests + updated existing tests green on Linux/macOS/Windows in CI release-matrix.
- Existing snapshot test for `novetest test` (no flag) remains green — byte-for-byte (zero regression on default behavior).
- New snapshot for `novetest test --reruns 5` happy path is merged and pinned.
- `match_flaky_suspected` now iterates over the new `replay_results` tuple; old `replay_result` field removed everywhere.
- `WORKLOG.md` entry per the standard format.
- Handoff at `agent-comms/handoffs/orchestration-team-2026-06-25-test-reruns-flag.md` includes:
  - Pointer to the merged worktree.
  - "DoD bullets believed closed" list (none — post-MVP add; PM will add a bullet after merge).
  - Snapshot diff of the new envelope (for PM spot-check before user-doc propagation).

## Coordination

- This task depends on the `reset` verb cycle merging first. Both touch `src/novetest/cli/app.py` but in different functions.
- After this merges, PM updates `design/user-doc/**` + `design/website-plan/handoff/docs/**` to document the new flag — that work is tracked under the user-doc taxonomy realignment PM self-task (`pm-team-2026-06-25-user-doc-taxonomy-realignment.md`) and folded into that cycle.

## Effort estimate (PM's read — challenge if you disagree)

- ~50 LOC in production code (1 flag + ~30-line sub-workflow + ~10 lines of FactBundle rename ripple).
- ~250 LOC of test code (3 new test files + updates to existing).
- ~40 LOC of doc update in `orchestration.md`.
- One short cycle. Comparable to recent flag additions on `run`. Surface via `agent-comms/questions/` before going wide if estimate balloons.
