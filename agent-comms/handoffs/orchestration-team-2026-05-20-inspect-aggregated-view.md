---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-20
slug: inspect-aggregated-view
related:
  - tasks/orchestration-team-2026-05-20-inspect-aggregated-view.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Handoff: `novetest inspect <run_id>` — aggregated single-run view

## Worktree

- Path: `/home/yjshin/dev/novetest-inspect-aggregated-view`
- Branch: `worktree-inspect-aggregated-view`
- Base commit: `215a941` (main)
- Commit: `0acb725` — `feat(orchestration): build novetest inspect aggregated single-run view`

## Files written / modified

Created:
- `src/novetest/orchestration/workflows/inspect.py` — `InspectView` frozen
  dataclass + `build_inspect_view(store, run_id) -> InspectView | None`.
  Mirrors `status.py`'s `StatusView` + `build_status_view`. Includes a
  module-private `_coverage_outcome_section` projection.
- `tests/unit/orchestration/workflows/test_inspect.py` — 7 unit cases.
- `tests/unit/cli/test_inspect_cmd.py` — 2 unit cases.
- `tests/integration/orchestration/test_inspect_cli.py` — 5 subprocess E2E.

Modified:
- `src/novetest/orchestration/workflows/__init__.py` — export `InspectView`
  + `build_inspect_view`.
- `src/novetest/cli/app.py` — dropped `"inspect"` from the
  `_register_flat_stub` tuple; added the thin `inspect_cmd` handler
  (`@app.command(name="inspect")`); imports `build_inspect_view`.
- `tests/integration/cli/test_subcommand_stubs.py` — parametrize list
  drops the now-implemented `["inspect"]` entry.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **311 passed + 1
  skipped** (299-test main baseline + 14 new − 1 dropped stub parametrize
  case; the skip is the pre-existing `test_jest_basic` no-Node skip).
  1 syrupy snapshot passed.
- `uv run mypy` → **clean**, `--strict`, 51 source files (+1 for
  `inspect.py`).
- Manual smoke skipped — the 5 subprocess E2E tests already exercise the
  real CLI end-to-end across all four `inspect` paths (coverage-run,
  plain-run, fake-id, uninitialized, tombstoned).

## `InspectView` container shape (for PM to freeze)

`InspectView.to_dict()` emits, under the envelope's `data`:

```json
{
  "run_reference": { "run_id": "<ULID>", "created_at": <int>, "schema_version": 1 },
  "run_summary": {
    "status": "passed" | "failed" | "errored" | ...,
    "target_expression": "<str>",
    "target_type": "<str>",
    "engine_name": "<str>",
    "ecosystem": "<str>",
    "summary_counts": { "<status>": <int>, ... },
    "tombstoned": <bool>
  },
  "coverage_outcome": { ...frozen coverage_outcome block, discriminated by `kind`... },
  "sub_reports": {
    "coverage":     "available" | "unavailable",
    "regression":   "unavailable",
    "localization": "unavailable",
    "replay":       "unavailable"
  }
}
```

Design rationale:
- **`coverage_outcome`** reuses the frozen v1 shape verbatim
  (`decisions/2026-05-16-coverage-outcome-envelope-shape.md`) — `kind:
  "fact-set"` when `coverage_facts.json` exists, `kind: "unavailable"`
  (reason `missing-derived-facts`) when the run had no `--coverage`.
- **`sub_reports`** is the same string-marker convention `status` uses.
  It always carries exactly four keys; `coverage` flips to `"available"`
  when facts exist. Regression/Localization/Replay are hard-`"unavailable"`
  until their engines land.
- **Monotonic evolution**: Phase 3/4/5 each add a sibling detail block
  (e.g. `regression_facts`) next to `coverage_outcome` and flip the
  matching `sub_reports` marker. The `sub_reports` dict shape never
  changes — pure additive growth, so freezing it now is safe.

## DoD bullets believed closed (PM verifies + ticks — not ticked here)

- **Phase 2 DoD #3** — `novetest inspect <run_id>` returns the Coverage
  section populated. `inspect` is now a real command; the Coverage
  section is a live `coverage_outcome` block sourced from persisted
  facts.

## Open items / notes for PM

- **Deviation from task spec, intentional**: the task suggested sourcing
  the unavailable reason via `check_coverage_availability`. Its
  `no-coverage-evidence` reason is NOT in the frozen `coverage_outcome`
  reason enum (`coverage/results.py::REASON_*` — the decision doc binds
  the enum to that module). Feeding it into the block would violate the
  frozen decision. Used `get_coverage_facts`'s `CoverageUnavailable`
  directly instead — it yields the contract-valid `missing-derived-facts`
  and makes the `inspect` Coverage section byte-identical to what
  `coverage show` emits, which the task explicitly wants.
- **Projection duplication**: `_coverage_outcome_section` (`inspect.py`)
  and `_coverage_outcome_payload` (`cli/app.py`) produce the identical
  wire shape. They cannot share one function — `inspect.py` is in
  `orchestration`, and importing from `cli/app.py` would create an
  `app.py → orchestration.workflows → inspect.py → cli.app` import
  cycle. The shape is decision-frozen, so no drift risk. A future slice
  could lift the projection into a shared `orchestration` module once a
  third in-orchestration consumer appears (rule-of-three).
- **Envelope schema implication**: none. `schema: novetest/v1` unchanged
  — this is a purely additive `data` extension on a command that was
  previously a stub. No `decisions/` schema bump needed.
- Recommend PM freeze the `InspectView` container shape above as a
  `decisions/` entry next cycle, as the task requested.
