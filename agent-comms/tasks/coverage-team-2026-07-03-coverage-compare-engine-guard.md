---
from: novetest-pm-team
to: novetest-coverage-team
type: task
status: pending
created: 2026-07-03
slug: coverage-compare-engine-guard
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
  - agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md
---

# Task: Coverage — engine-mismatch guard in `compare_coverage_facts` (D5, Finding A)

- **Owner**: novetest-coverage-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` D5
- **Sequencing**: Wave 2, no dependencies — parallel with the Orchestration
  and Localization slices. **Priority item of the wave**: this is the only
  cross-engine path that emits corrupt facts (not just noise), and it is
  agent-triggerable from the CLI today.

## Why

D5 audit Finding A (`questions/regression-team-2026-07-03-d5-cross-run-audit.md`):
`compare_coverage_facts` (`src/novetest/coverage/compare.py:182-243`)
resolves both sides and computes the set-difference delta with **zero**
`engine_name` validation, although both `CoverageFactSet`s carry the field
(`src/novetest/models/coverage_fact_set.py:189`). Two CLI callers hand it
user-supplied pairs unchecked (`cli/app.py:663` — `coverage diff <a> <b>`;
`cli/app.py:788` — `compare <a> <b>`). Result: `novetest coverage diff
<pytest_run> <cargo_run>` silently emits a meaningless `CoverageDelta`.
Contrast: Regression's `compare_runs` refuses the same input shape with
`REASON_ENGINE_MISMATCH`.

## In scope

1. **Guard inside `compare_coverage_facts`** (engine-side, not caller-side,
   so every present and future consumer is protected): when the two
   `CoverageFactSet.engine_name`s differ → return `CoverageUnavailable`
   with a NEW reason constant mirroring Regression's naming
   (recommended: `REASON_ENGINE_MISMATCH`; detail string carrying both
   names, mirroring `regression/compare.py:178-183`).
2. **Envelope**: the new reason is an additive enum value on the existing
   `coverage_change = unavailable` surface. PM pre-authorizes a one-line
   amendment to `decisions/2026-05-16-coverage-delta-envelope-shape.md`
   recording the new reason — append it as part of this slice (cite this
   brief's slug).
3. **Callers**: no CLI changes expected — both call sites already render
   `CoverageUnavailable` reasons generically. Verify and state so in the
   handoff (or fix minimally if a reason string leaks unrendered).
4. **Regression-side embed**: `regression/compare.py:572` calls
   `compare_coverage_facts` only after its own engine guard passes, so the
   new reason is unreachable there — assert this with a test comment, no
   behavior change.

## Out of scope

Localization/Orchestration findings (routed separately), baseline
*selection* logic (Regression owns `resolve_baseline_for_run`), CLI
argument validation redesign, per-file path normalization.

## Pinned file list

- **Edit**: `src/novetest/coverage/compare.py`, the reasons/constants
  module it uses, `agent-comms/decisions/2026-05-16-coverage-delta-envelope-shape.md`
  (additive amendment only).
- **Tests**: `tests/unit/coverage/` — mixed-engine pair →
  `CoverageUnavailable(REASON_ENGINE_MISMATCH)` with both names in detail;
  same-engine pair unchanged (snapshot); CLI `coverage diff` integration
  case rendering the new reason cleanly.

## Acceptance criteria

- `novetest coverage diff <pytest_run> <cargo_run>` (fixture) returns the
  unavailable envelope with the new reason — no `CoverageDelta` emitted.
- Existing same-engine snapshots byte-identical.
- Full suite green on the CI matrix; mypy clean; `WORKLOG.md` entry;
  handoff at
  `agent-comms/handoffs/coverage-team-2026-07-03-coverage-compare-engine-guard.md`.

## Effort estimate (PM's read — challenge if you disagree)

~25 LOC production, ~80 LOC tests. Half cycle.
