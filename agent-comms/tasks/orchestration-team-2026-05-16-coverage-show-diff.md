---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-16
slug: coverage-show-diff
related:
  - history/2026-05-16-coverage-cli-wiring.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Task: Implement `novetest coverage show` + `coverage diff` CLI verbs

## Scope / Mission

Promote the `coverage` subcommand group from stub to working handlers:

- `novetest coverage show <run_id>` — load the persisted CoverageFactSet
  for a single run and project it onto the envelope's `coverage_outcome`
  block (the shape frozen in
  `decisions/2026-05-16-coverage-outcome-envelope-shape.md`).
- `novetest coverage diff <baseline_run_id> <target_run_id>` — compare
  two runs' CoverageFactSets and project the resulting `CoverageDelta`
  onto a new `data.coverage_delta` envelope block.

Both verbs surface the `CoverageUnavailable` outcome cleanly — this is
the first CLI surface where `kind: "unavailable"` becomes reachable
end-to-end (closes the known limitation from the prior cycle's findings).

Closes **Phase 2 DoD #2** ("`novetest coverage diff` returns structured
deltas with stable Code Location identity"). Does NOT close DoD #3
(`inspect` Coverage section — separate slice) or #4 (50k-location perf
— separate slice).

## Pre-flight reading

1. `CLAUDE.md`
2. `agent-comms/INDEX.md`
3. `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` —
   binding `coverage_facts.json` layout (the on-disk shape `show` reads)
4. `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md` —
   binding envelope projection for `kind: "fact-set" | "unavailable"`
   (reused verbatim for `show`)
5. `agent-comms/history/2026-05-16-coverage-cli-wiring.md` — the prior
   slice that introduced `coverage_outcome`; this task extends the
   pattern to two new verbs
6. `agent-comms/tasks/orchestration-team-2026-05-16-coverage-show-diff.md`
   (this file)
7. `WORKLOG.md` top 3 entries
8. `design/interace-contract/orchestration.md` — your envelope authority
9. `design/interace-contract/coverage.md` — read-only; tells you the
   `get_coverage_facts` / `compare_coverage_facts` contracts
10. `design/workflows/coverage.md` (Sections for `show` and `diff`)
11. `design/implementation-plan/delivery-phasing.md` Phase 2 DoD

## Pinned data contracts (Coverage engine, READ-ONLY)

### `get_coverage_facts`

```python
# src/novetest/coverage/retrieval.py
def get_coverage_facts(
    store: ProjectStore,
    run_reference: RunReference,
) -> CoverageFactSet | CoverageUnavailable: ...
```

- Returns `CoverageFactSet` on cache hit; `CoverageUnavailable` (with
  `reason: "missing-derived-facts"` or similar) when no
  `coverage_facts.json` exists for that run.
- **Cache-read only.** Never auto-derives — that's `derive_coverage_facts`'s
  job, called only at `run --coverage` time per the prior slice.

### `compare_coverage_facts`

```python
# src/novetest/coverage/compare.py
def compare_coverage_facts(
    store: ProjectStore,
    baseline_run_reference: RunReference,
    target_run_reference: RunReference,
) -> CoverageDelta | CoverageUnavailable: ...
```

- Returns `CoverageDelta` on success; `CoverageUnavailable` propagated
  from either side if either run lacks derived facts.
- `CoverageDelta.to_dict()` exists — use it for envelope projection.

### `CoverageDelta` shape (for envelope projection reference)

```python
# src/novetest/coverage/compare.py
@dataclass(frozen=True)
class CoverageDelta:
    baseline_run_reference: RunReference
    target_run_reference: RunReference
    baseline_granularity: str
    target_granularity: str
    summary_before: CoverageSummary
    summary_after: CoverageSummary
    files_added: tuple[str, ...]
    files_removed: tuple[str, ...]
    file_deltas: tuple[FileCoverageDelta, ...]
    schema_version: int = 1
```

`to_dict()` returns the same structure as JSON (per the existing
implementation).

## Envelope shape

### `coverage show` — reuse `coverage_outcome` (frozen v1)

```json
{
  "command": "coverage.show",
  "ok": true,
  "data": {
    "coverage_outcome": {
      "kind": "fact-set",
      "run_reference": {...},
      "mapping_granularity": "per-test",
      "summary": {...}
    }
  }
}
```

On `CoverageUnavailable`: `kind: "unavailable"` with
`{run_reference, reason, detail}`. Exit code 0 (the verb succeeded; the
outcome is part of the result).

### `coverage diff` — new `coverage_delta` block

Propose the v1 shape (PM will freeze in a follow-up decision IFF the
shape needs cross-team re-use; for now, document it in your handoff):

```json
{
  "command": "coverage.diff",
  "ok": true,
  "data": {
    "coverage_delta": {
      "kind": "delta",
      "baseline_run_reference": {...},
      "target_run_reference": {...},
      "baseline_granularity": "per-test",
      "target_granularity": "per-test",
      "summary_before": {...},
      "summary_after": {...},
      "files_added": [...],
      "files_removed": [...],
      "file_deltas": [...]
    }
  }
}
```

On `CoverageUnavailable`:

```json
{
  "command": "coverage.diff",
  "ok": true,
  "data": {
    "coverage_delta": {
      "kind": "unavailable",
      "run_reference": {...},   // whichever side was unavailable
      "reason": "...",
      "detail": "..."
    }
  }
}
```

Discriminator `kind: "delta" | "unavailable"`. Same omission-not-null
discipline as `coverage_outcome` — but since both verbs always emit
a meaningful outcome, omission case doesn't arise.

## Files to write / modify

- `src/novetest/cli/app.py` — replace `coverage` group stubs with real
  handlers:
  - `coverage_show(run_id: str)` — call `_require_store`, resolve
    `run_reference` via `list_run_history` lookup (mirror the pattern
    in `memory_show`), call `get_coverage_facts`, project to envelope.
  - `coverage_diff(baseline_run_id: str, target_run_id: str)` — same
    lookup pattern twice, call `compare_coverage_facts`, project to
    envelope.
  - Remove the corresponding `_register_group_stub("coverage", ...)`
    entries.
  - Reuse the existing `_coverage_outcome_payload` helper from the
    prior slice for `show`. Add a `_coverage_delta_payload` helper for
    `diff`.
- `src/novetest/orchestration/workflows/coverage.py` (NEW) — thin
  facade if the CLI handler grows beyond ~20 lines of logic. Otherwise
  inline the workflow in the CLI handler. PM permits either; pick the
  shape that keeps `cli/app.py` thin per charter.
- `tests/unit/cli/test_coverage_cmd.py` (NEW) — 5+ cases:
  - show with valid run_id + facts present → `kind: "fact-set"` payload
  - show with valid run_id + facts absent → `kind: "unavailable"`,
    `reason` from `coverage/results.py` constants
  - show with non-existent run_id → envelope `errors[0].code == "not-found"`,
    exit code 2 (mirror `memory_show` not-found path)
  - diff with two valid runs both having facts → `kind: "delta"` with
    full payload
  - diff where one side lacks facts → `kind: "unavailable"`
- `tests/integration/orchestration/test_coverage_cli.py` (NEW) —
  subprocess E2E covering:
  - `novetest run --coverage tests/` against `pytest-coverage` fixture
    (twice, to get two run_ids)
  - `novetest coverage show <id1>` → envelope `coverage_outcome.kind == "fact-set"`
  - `novetest coverage diff <id1> <id2>` → envelope `coverage_delta.kind == "delta"`,
    `summary_before.percent_covered ≈ summary_after.percent_covered`
    (same fixture run twice = no real delta)
  - `novetest coverage show <fake-id>` → envelope `errors[0].code == "not-found"`,
    exit code 2

## Files NOT to touch

- `src/novetest/coverage/**` — Coverage team's territory. Consume
  `get_coverage_facts`, `compare_coverage_facts`, the result types.
- `src/novetest/memory/**`, `src/novetest/models/**` — Memory team's.
- `src/novetest/run/**` — Run team's.
- `tests/fixtures/projects/pytest-coverage/**` — Run team's fixture.
  Use as-is.
- `agent-comms/decisions/**`, `history/**` — PM only.
- `pyproject.toml` — no new deps needed.

## Verification commands

```sh
# Unit
uv run pytest -q tests/unit/cli/test_coverage_cmd.py

# Full suite (baseline 267 + new)
uv run pytest -q tests/unit tests/integration

# mypy --strict
uv run mypy

# Manual smoke
cd /tmp && rm -rf coverage-show-diff-smoke
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-coverage coverage-show-diff-smoke
cd coverage-show-diff-smoke
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' novetest init
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' novetest run --coverage tests/ --output json > /tmp/run1.json
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' novetest run --coverage tests/ --output json > /tmp/run2.json
ID1=$(python3 -c "import json; print(json.load(open('/tmp/run1.json'))['data']['memory_entry']['entry_id'])")
ID2=$(python3 -c "import json; print(json.load(open('/tmp/run2.json'))['data']['memory_entry']['entry_id'])")
uv run --with /home/yjshin/dev/Nove-Test novetest coverage show "$ID1" --output json | python3 -m json.tool | head -30
uv run --with /home/yjshin/dev/Nove-Test novetest coverage diff "$ID1" "$ID2" --output json | python3 -m json.tool | head -40
uv run --with /home/yjshin/dev/Nove-Test novetest coverage show fake-id --output json
```

The smoke confirms:
1. Both verbs respond to the CLI without Cyclopts error.
2. `show` projects to `coverage_outcome.kind == "fact-set"` with full
   summary.
3. `diff` projects to `coverage_delta.kind == "delta"` with both
   summaries + file_deltas (same fixture → mostly empty deltas, but
   non-error response).
4. `coverage show fake-id` returns the not-found envelope.

## DoD bullets to claim closed

In the handoff's "DoD bullets believed closed" list, name:

- **Phase 2, bullet #2** — "`novetest coverage diff` returns structured
  deltas with stable Code Location identity."

Do NOT claim Phase 2 #1 (already closed prior cycle), #3 (inspect —
separate slice), or #4 (perf — separate slice).

## Reporting (handoff)

Write `agent-comms/handoffs/orchestration-team-2026-05-16-coverage-show-diff.md`
with the standard sections:

- Worktree path + branch + base commit.
- Files written/modified.
- pytest counts (new total) + mypy result.
- WORKLOG entry text (paste).
- DoD bullets believed closed.
- **Proposed `data.coverage_delta` envelope shape** — paste the final
  shape your code emits, so PM can decide whether to add a
  `decisions/2026-05-16-coverage-delta-envelope-shape.md` entry. If
  the shape matches the proposed shape in this task spec verbatim,
  say so; if it differs, document why.
- Open items / surprises.

Append WORKLOG entry per format. Run `python3 tools/regen_comms_index.py`.
Stage WORKLOG + handoff + INDEX alongside source.

## Out of scope (do NOT do these in this task)

- `novetest inspect <run_id>` Coverage section — Phase 2 DoD #3, next
  slice.
- 50k-location perf fixture — Phase 2 DoD #4, separate scoping.
- Modify the `coverage_outcome` shape — frozen in
  `decisions/2026-05-16-coverage-outcome-envelope-shape.md`. `show`
  reuses verbatim.
- Modify the on-disk `coverage_facts.json` layout — frozen in
  `decisions/2026-05-15-coverage-facts-json-layout.md`.
- Touch Coverage engine internals — `get_coverage_facts`,
  `compare_coverage_facts`, `CoverageDelta.to_dict()` exist; consume
  as-is.
- Auto-derive on `coverage show` against a run without facts — the
  contract is cache-read-only; surface `kind: "unavailable"` instead.
- Add a `--baseline` flag or any other behavioral extension to the
  verbs — minimum surface only this cycle.

## Why this task exists

The prior slice (`10300bb`) introduced the persisted `CoverageFactSet`
and the `coverage_outcome` envelope shape — but the only CLI surface
that emitted them was `novetest run --coverage`. Users can't yet
**inspect** existing coverage data (they'd have to re-run) or
**compare** two runs at the CLI surface. This task closes both
omissions in one slice and exercises the `kind: "unavailable"` branch
end-to-end for the first time (the missing test coverage Manual Test
flagged in the prior cycle's findings).
