---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-05-20
slug: inspect-aggregated-view
related:
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Task: `novetest inspect <run_id>` — build the aggregated view + populate Coverage section

## Scope / Mission

Build `novetest inspect <run_id>` for the first time and close **Phase 2
DoD #3** (`inspect` returns the Coverage section populated).

**Important — this is NOT a stub extension.** `inspect` is currently a
*flat stub* registered via `_register_flat_stub("inspect")` in
`src/novetest/cli/app.py` (emits a "not implemented" envelope, exits
`EXIT_USAGE`). There is no orchestration workflow behind it. This slice
builds the whole aggregated-view command: a real workflow, a real CLI
handler, and the Coverage section populated.

The aggregated view inspects ONE already-stored run. It does not execute
anything. Regression / Localization / Replay sections are present-but-empty
in this slice (Phase 3/4/5 populate them); only the Coverage section is
made real now.

## Pre-flight reading

1. `CLAUDE.md` + your charter `.claude/agents/novetest-orchestration-team.md`
2. `design/implementation-plan/delivery-phasing.md` — Phase 1 "Stub fact
   surface" note on `inspect`, and Phase 2 DoD #3
3. `agent-comms/decisions/2026-05-16-coverage-outcome-envelope-shape.md`
   — the `coverage_outcome` block is BINDING; reuse it verbatim
4. `src/novetest/orchestration/workflows/status.py` — the precedent.
   `build_status_view` + `StatusView.to_dict()` is the exact pattern to
   mirror for `build_inspect_view` + `InspectView.to_dict()`
5. `src/novetest/cli/app.py` — how `status` is registered as a real
   command (vs `_register_flat_stub`), and the existing
   `_coverage_outcome_payload` projection (~ lines 260-287)
6. `src/novetest/coverage/__init__.py` — public API exports; you will
   consume `get_coverage_facts` and `check_coverage_availability`
7. The `memory show <run_id>` handler in `app.py` — mirror its
   `run-not-found` and `uninitialized` error handling

## Files to write / modify

- `src/novetest/orchestration/workflows/inspect.py` — NEW. `InspectView`
  dataclass + `build_inspect_view(store, run_id)`. Mirror `status.py`'s
  structure (frozen dataclass, `to_dict()`).
- `src/novetest/orchestration/workflows/__init__.py` — export the new
  symbols.
- `src/novetest/cli/app.py` — replace the `inspect` flat-stub
  registration with a real command handler.
- `tests/unit/orchestration/workflows/test_inspect.py` — NEW.
- `tests/unit/cli/test_inspect_cmd.py` — NEW.
- `tests/integration/orchestration/test_inspect_cli.py` — NEW.

## Files NOT to touch

- `src/novetest/coverage/**`, `src/novetest/run/**`, `src/novetest/memory/**`,
  `src/novetest/models/**` — consume their PUBLIC APIs read-only; do not
  edit them. If you need a new API surface from another engine, STOP and
  write `agent-comms/questions/orchestration-team-2026-05-20-*.md`.
- `.github/**`, `pyproject.toml`, any `agent-comms/decisions/**`.
- The `coverage_outcome` shape — frozen; reuse, do not redesign.

## Data contracts (pinned verbatim)

### `data.coverage_outcome` — reuse the frozen v1 shape

The `inspect` envelope's Coverage section IS a `coverage_outcome` block,
identical to what `coverage show` emits. Discriminated by `kind`:

```json
// kind: "fact-set" — Coverage Facts exist for this run
{ "kind": "fact-set",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "mapping_granularity": "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "summary": { ...CoverageSummary.to_dict()... } }

// kind: "unavailable" — no Coverage Facts for this run
{ "kind": "unavailable",
  "run_reference": { "run_id": "<ULID>", "created_at": "<ISO8601-UTC>" },
  "reason": "missing-native-payload" | "native-payload-corrupt" | "run-not-found",
  "detail": "human-readable explanation" }
```

Reuse the existing `_coverage_outcome_payload` projection in `app.py`.
Do NOT improvise a different shape. Full constraints in
`decisions/2026-05-16-coverage-outcome-envelope-shape.md`.

`coverage diff`-style `coverage_delta` composition is **out of scope** for
this slice — `inspect` inspects a single run, no baseline pair.

### Sourcing the Coverage section

`inspect` does not run anything. Source the Coverage outcome from the
already-persisted facts:
- `get_coverage_facts(store, run_reference)` -> if facts exist, project
  `kind: "fact-set"`.
- otherwise `check_coverage_availability(...)` -> project
  `kind: "unavailable"` with the reason.

### Aggregated-view container

`InspectView.to_dict()` carries, at minimum: the run's `run_reference`,
a run summary (test pass/fail counts from the Run Record), the
`coverage_outcome` block, and present-but-empty Regression / Localization
/ Replay sections. For the three not-yet-real sections, mirror
`StatusView.to_dict()`'s `sub_reports` convention (`"unavailable"`
markers) so the shape is consistent with `status`. Document your chosen
container shape in the handoff — PM will freeze it as a `decisions/`
entry next cycle, so describe it precisely.

### Error handling (mirror `memory show`)

- `inspect <unknown-run-id>` -> structured `not-found` error, exit `2`.
- `inspect` from a tree with no ancestor `.novetest/` -> structured
  `uninitialized` envelope pointing at `novetest init`, exit `2`, no
  traceback.
- Tombstoned runs remain inspectable (mirror `memory show`).
- `schema: novetest/v1` unchanged — this is an additive `data` extension.

## Verification commands (must pass before handoff)

- `uv run pytest -q` — green.
- `uv run mypy` — clean.
- Manual smoke: `novetest run` a fixture, then
  `novetest inspect <run_id> --output json` shows the run + a
  `coverage_outcome` block; with `--coverage` on the run it is
  `kind: "fact-set"`, without it is `kind: "unavailable"`.

## Coding guidelines

Invoke the `andrej-karpathy-skills:karpathy-guidelines` skill before
writing code. You may recruit `Plan` / `api-designer` for the view-shape
design.

## Reporting

Write `agent-comms/handoffs/orchestration-team-2026-05-20-inspect-aggregated-view.md`.
Per the post-flight protocol: append a `WORKLOG.md` entry (this slice
touches `src/` + `tests/`), run `python3 tools/regen_comms_index.py`,
stage `WORKLOG.md` + new comms files + `INDEX.md` with source.

**DoD bullets believed closed:** claim Phase 2 DoD #3 (`inspect` returns
the Coverage section populated) in the handoff's "DoD bullets believed
closed" list. Do NOT tick it yourself — PM verifies and ticks during
cycle cleanup. Also describe your `InspectView` container shape so PM can
freeze it.
