---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
slug: localization-cli
created: 2026-05-29
related:
  - agent-comms/tasks/orchestration-team-2026-05-29-localization-cli.md
  - agent-comms/decisions/2026-05-28-localization-finding-shape-v2.md
  - src/novetest/cli/app.py
  - src/novetest/orchestration/workflows/inspect.py
---

# Handoff: Localization CLI slice (Phase 4 §4)

## Summary

Projects the now-complete Localization engine surface onto the CLI — the
4th application of the project's `engine → CLI → freeze` cadence
(mirrors the Regression CLI slice `c074226`). Two real verbs
(`novetest localization <run_id>` and `novetest localization latest`),
an `inspect` Localization section (cache-only), `--formula` / `--top-n`
flags validated at the CLI boundary, and the working-draft
`localization_outcome` envelope block discriminated by `kind`. No engine
code touched; the projection follows `LocalizationFinding.to_dict()` /
`LocalizationUnavailable.to_dict()` verbatim (adds `kind`, strips the
top-level `schema_version`).

## Worktree

- Branch: `novetest-localization-cli` (off `main` tip `f2243b8`).
- Path: `/home/yjshin/dev/aispace/Nove-Test-localization-cli`
- Clean except the intended changes (see Files below).

## Files

**Edited (src — 2 files, 0 new):**
- `src/novetest/cli/app.py` — `localization_app` sub-App; `localization_run`
  (`@localization_app.default`, positional `run_id` + kw-only
  `--formula`/`--top-n`); `localization_latest`
  (`@localization_app.command(name="latest")`);
  `_validate_localization_flags` (boundary guard → `invalid-flag` exit 2);
  `_localization_outcome_payload` projection. Dropped `"localization"`
  from the `_register_flat_stub` loop; refreshed the stale `inspect_cmd`
  docstring.
- `src/novetest/orchestration/workflows/inspect.py` —
  `InspectView.localization_outcome` field; `_resolve_inspect_localization`
  (cache-only via `get_localization_findings`);
  `_localization_outcome_section` projection; wired into
  `build_inspect_view` + `to_dict()`; flipped `sub_reports["localization"]`.

**Added (tests — 4 files):**
- `tests/unit/cli/test_localization.py` (10)
- `tests/unit/cli/test_localization_latest.py` (5)
- `tests/unit/orchestration/workflows/test_inspect_localization.py` (8)
- `tests/integration/cli/test_localization_e2e.py` (3)

**Edited (tests — existing, 0 new test functions):**
- `tests/unit/orchestration/workflows/test_inspect.py` (+14 lines —
  `get_localization_findings` stub wired into the seam-patch helper).
- `tests/unit/orchestration/workflows/test_inspect_regression.py` (+15
  lines — same seam stub).
- `tests/integration/cli/test_subcommand_stubs.py` (−1 parametrize case:
  `localization` dropped; only `test`/`replay` remain stubs).

## Verification

- `uv run pytest -q tests/unit tests/integration` → **638 passed + 3
  skipped**. The 3 skips are the pre-existing Node-dependent jest
  integration tests on this dev box. (Task brief quoted a 611+5 baseline
  measured on the Manual-Test box; the box-independent figure is the
  **+26 new / +25 net** test delta. The 4 new files also pass in
  isolation: `26 passed`.)
- `uv run mypy` → **clean, `--strict`, 69 source files** (no new src
  files — count unchanged from baseline).
- Manual smoke against a real `localization-branch` tmp store:
  `run --coverage` (status failed) → `localization latest`
  `kind: "fact-set"`, top-level `schema_version` absent,
  presentation key `formula == "ochiai"`, `entries[0]` rank 1 symbol
  `divide` score_raw 1.0, entry-level `evidence_lines`/`schema_version`
  correctly absent, `code_location.evidence_lines` present;
  `--formula bogus` → exit 2 `invalid-flag`; `inspect <run_id>`
  post-derive → `localization_outcome.kind == "fact-set"`,
  `sub_reports.localization == "available"`.

## Envelope-schema implications

- New OPTIONAL `data.localization_outcome` block (discriminated by
  `kind` ∈ {`fact-set`, `unavailable`}) on `localization`,
  `localization.latest`, and `inspect` envelopes. Top-level envelope
  `schema: novetest/v1` is **unchanged** (no bump — additive data block,
  same pattern as `coverage_outcome` / `regression_outcome`).
- Shape is a **working draft** — PM freezes it via
  `decisions/2026-05-XX-localization-outcome-envelope-shape.md` AFTER
  Manual Test fields it (mirrors the two Coverage + the Regression
  envelope freezes).

## Deviations from the brief

The task's prose JSON sketch (task §"Wire shape (working draft)") is
idealized; the brief ALSO pins `LocalizationFinding.to_dict()` /
`LocalizationEntry.to_dict()` as source-of-truth and instructs "do not
re-shape". The projection therefore follows the engine `to_dict()`
verbatim. Where the sketch and the actual `to_dict()` differ (the SKETCH
is the stale artifact, the code is correct):

1. **`formula` not `primary_formula`** — the fact-set presentation key is
   `formula` (the actual `LocalizationFinding.to_dict()` key). The sketch
   wrote `primary_formula`.
2. **No entry-level `evidence_lines`** — `LocalizationEntry.to_dict()`
   does NOT emit `evidence_lines`; the suspicious-lines list lives INSIDE
   `code_location.evidence_lines`. The sketch placed `evidence_lines` at
   entry level.
3. **No entry-level `schema_version`** — only the top-level
   `LocalizationFinding` carries `schema_version` (which the projection
   strips). The sketch showed `schema_version: 1` on each entry.

Actual to_dict keys to anchor the freeze on:
- fact-set top-level: `kind, run_reference, engine_name, ecosystem, mode,
  confidence, formula, alternate_scores_available, top_n, entries,
  derived_at, metadata`.
- entry: `rank, tied_with, code_location, score_raw, score_normalized,
  formula, alternate_scores, related_failed_tests, evidence_citations`.
- `code_location`: `kind, file, symbol, line_range, primary_line,
  evidence_lines`.
- unavailable: `kind, run_reference, reason, detail` (all always present;
  `run_reference` may be `null` for the latest-resolution empty /
  all-non-analyzable cases; reasons use **underscore** form).

These were not improvised — the projection is a pure verbatim pass of the
engine `to_dict()`, exactly as the brief's "do not re-shape" instruction
requires. PM resolves the sketch-vs-code wording before the freeze.

## DoD bullets believed closed (PM verifies + ticks — do NOT tick here)

- `delivery-phasing.md` Phase 4 §4 **[186]** — `novetest localization
  latest --output json` against `localization-branch` ranks the bug in
  top 3 (integration case 1 ranks `divide` at #1, Ochiai 1.0).
- `delivery-phasing.md` Phase 4 §4 **[189]** — all four formulas
  computed + persisted (engine) AND `--formula` selects which is
  presented as primary (this slice closes the second half).
- **[187] partially** — per-test `mode` populates correctly; the
  `sbfl_aggregate` / `failure_proximity` modes + their fixtures are
  separate post-CLI Localization slices (NOT claimed here).
- **[188]** (perf NFR-LOC-002) — NOT claimed (separate perf cycle).

## Notes for Main Branch

- Merge gate: `uv run pytest -q tests/unit tests/integration` (expect
  638+3) and `uv run mypy` (expect clean, 69 files).
- This worktree also contains the WORKLOG.md entry (2026-05-29 /
  localization-cli) and a regenerated `agent-comms/INDEX.md`.
- **Base-commit / INDEX caveat (action required):** this worktree
  branched off `f2243b8` **as the task brief instructed**, but the actual
  `main` tip is `3094d1e` ("comms: queue 2026-05-29 parallel cycle —
  Localization CLI + cargo adapter"), which added the 2026-05-29 task
  files (`tasks/orchestration-team-2026-05-29-localization-cli.md` +
  `tasks/run-team-2026-05-29-cargo-adapter.md`) and listed them under
  Pending in INDEX.md — all AFTER f2243b8. Because those task files are
  not present in this worktree's tree, my `regen_comms_index.py` produced
  an INDEX.md whose Pending section is empty. **After merging this branch
  onto `main` (3094d1e), re-run `python3 tools/regen_comms_index.py`** so
  the still-pending run-team cargo-adapter task is preserved and this
  cycle's task status is recomputed from the real frontmatter. (The task
  files are the source of truth; INDEX.md is derived — re-regen resolves
  it cleanly. Prefer "take the regenerated output" over hand-merging the
  INDEX.md conflict.)
- Suggested verification request to Manual Test: field all three
  surfaces against a real `localization-branch` store — every `REASON_*`
  propagation path, the `--formula`/`--top-n` flag matrix, the cache-hit
  `derived_at` preservation, and the `inspect` cache-only contract.
