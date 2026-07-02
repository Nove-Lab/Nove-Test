---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-07-03
slug: pin-driven-dispatch-and-detection-api
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Task: Run — pin-driven dispatch + single-source detection API

- **Owner**: novetest-run-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` (D1, D2, D3)
- **Sequencing**: no dependencies — may start immediately, parallel with
  Memory and Regression. The Orchestration slice consumes your new API.

## Goal

Move engine *detection* out of the per-invocation hot path and into an
explicit API for `init`, make `execute()` accept an externally resolved
engine (the pin or a transient override), and collapse the two divergent
priority lists into one source of truth.

## Why

Under the anchored-pin model, run-time detection ceases to exist: a store
implies a pin. Detection happens only at `init` (and D6 backfill), through
one API. This is also where the latent bug documented in the 2026-07-02
question §4.1 dies: `engine_selector._ECOSYSTEM_MARKERS` and
`readiness.assess_engine_readiness` currently disagree on Java's rank
(java 3rd vs junit 5th), so a `pom.xml`+`go.mod` workspace can have Go
readiness-verified but JUnit dispatched. With a single list and pin-driven
dispatch, no code path remains where the mismatch can misfire.

## In scope

### 1. Single source of truth for the marker/priority table

Consolidate the ordered marker table in
`src/novetest/run/engine_selector.py:16-33` and the disambiguation order in
`src/novetest/run/readiness.py:164-224` into ONE module-level constant
(engine_selector is the natural home). Both call sites consume it. Add a
regression test asserting the two paths can never diverge again (e.g. the
readiness order is derived from, not parallel to, the selector table).

### 2. Detection API for init (consumed by Orchestration)

- `detect_engine_candidates(workspace: Path) -> list[Candidate]` — marker
  scan of ONE directory (no recursion), returning every matched ecosystem
  pair in canonical order. Promote/adjust the existing internal helper;
  update `design/interace-contract/run.md` accordingly.
- Per-candidate readiness: reuse the existing probes so callers can
  distinguish *marker-matched* from **ready** candidates — decision D1's
  ambiguity is defined over READY candidates (a tooling-only `package.json`
  with no runnable jest must not trigger `engine-ambiguous`).
- `probe_engine(workspace, ecosystem, engine_name)` — readiness for one
  specific engine (used at init-pin time and for pin-targeted reporting),
  replacing the scan-until-first-success pattern for pinned flows.

### 3. `execute()` accepts the resolved engine

Extend `execute()` (`src/novetest/run/engine.py:34-79`) with an explicit
`engine: tuple[str, str] | None` parameter:

- Provided (the normal path once Orchestration wires pins): dispatch that
  engine directly; do NOT re-detect.
- `None`: preserve today's auto-detect behavior byte-for-byte, as a
  temporary compatibility path — Orchestration removes the last `None`
  caller in its slice, after which the `None` branch may be dropped (leave
  a TODO referencing the orchestration slug).

## Out of scope

- CLI flags, init workflow, walk-up resolution, store/pin persistence
  (Memory), migration flow (Orchestration), any adapter changes, the
  `_invoke_adapter` if-elif ladder refactor (the decorator-registry
  question — `foundations.md:318/475` vs reality — is tracked separately;
  do NOT expand into it).

## Pinned file list

- **Edit**: `src/novetest/run/engine_selector.py`,
  `src/novetest/run/readiness.py`, `src/novetest/run/engine.py`,
  `design/interace-contract/run.md`.
- **Tests**: update existing under `tests/unit/run/`; add — dual-marker
  fixture returns both candidates in canonical order; tooling-only
  `package.json` (no jest) yields candidate-but-not-ready; `execute()`
  with explicit engine skips detection; single-list divergence guard.

## Acceptance criteria

- Full unit + integration green on the CI matrix; mypy clean.
- `execute(engine=None)` path byte-identical to current envelopes
  (snapshot-pinned).
- The §4.1 mismatch is demonstrably dead: a test covering the
  `pom.xml`+`go.mod` fixture shows readiness and dispatch agree.
- `WORKLOG.md` entry; handoff at
  `agent-comms/handoffs/run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md`
  documenting the final detection API signatures for Orchestration.

## Effort estimate (PM's read — challenge if you disagree)

~120 LOC production, ~250 LOC tests. One cycle.
