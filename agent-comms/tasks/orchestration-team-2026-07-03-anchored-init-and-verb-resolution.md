---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-07-03
slug: anchored-init-and-verb-resolution
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/tasks/memory-team-2026-07-03-engine-pin-store-primitives.md
  - agent-comms/tasks/run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
---

# Task: Orchestration — anchored init, verb walk-up resolution, pin dispatch wiring

- **Owner**: novetest-orchestration-team
- **Pinned decision**: `2026-07-03-engine-selection-policy.md` (all of D1–D7)
- **Sequencing**: **DO NOT START until the Memory slice
  (`engine-pin-store-primitives`) and the Run slice
  (`pin-driven-dispatch-and-detection-api`) are both on `main`.** You
  consume both APIs. The Regression slice is independent but touches
  `workflows/inspect.py` / `workflows/status.py` — coordinate merge order
  with Main Branch if cycles overlap.

## Goal

Ship the user-facing anchored-pin model: init that pins (D1) with bounded
discovery (D4), verbs that resolve their workspace by upward walk (D2),
bare/explicit target semantics with anchor-relative normalization (D3),
transient `--engine` override (D3), lazy migration (D6), and the new error
codes (D7).

## In scope

### 1. `init` workflow (D1 + D4 + D7) — `orchestration/workflows/init.py`

Using Run's `detect_engine_candidates` + per-candidate readiness:

- **Exactly one READY candidate** → `create_project_store` +
  `set_pinned_engine` (Memory) → success envelope now includes
  `data.pinned_engine`.
- **No marker** → do NOT create a store. Run the bounded downward
  discovery per D4 (depth ≤ 2; if inside a git repo never leave it;
  invoked at `/` or `$HOME` → refuse without traversal; skip
  `node_modules/ target/ .venv/ venv/ .git/ dist/ build/ .novetest/`;
  stop descending at a found project root). Exit non-zero, error code
  **`no-engine-detected`**, `data.candidates = [{path, ecosystem,
  engine_name}]`, message instructing the agent to `cd` into each
  candidate and run `init` there itself.
- **≥2 READY candidates** → do NOT create a store. Exit non-zero, error
  code **`engine-ambiguous`**, `data.candidates`, message requiring
  `novetest init --engine <name>`.
- **`--engine <name>`** optional flag on `init`: validated against the six
  pairs (invalid → `invalid-flag`, exit 2, mirroring the `--formula`
  pattern); when supplied, skips ambiguity handling and pins that engine.
  Re-init on an existing store with `--engine` **re-pins in place** —
  never a second store, run history retained.

### 2. Verb anchor resolution (D2) — one shared helper

Introduce ONE workspace-resolution helper wrapping Memory's
`find_nearest_store(cwd)`; route **every** verb through it. Found →
anchor store + pin govern; not found → existing `uninitialized` error.
Remove any per-verb ad-hoc cwd assumptions. No verb may scan downward.

### 3. Target semantics (D3, clarified)

- Bare invocation (no target argument) → `target_expression = ""`
  (workspace scope at the anchor) regardless of the invocation
  subdirectory.
- Explicit target paths are normalized to **anchor-relative canonical
  form** before `resolve_test_target` (workspace-relpath utility), so the
  same ask from different cwds shares one baseline series.
- `--engine <name>` transient override on `test` / `run`: validated; does
  NOT re-pin; passed to Run's `execute(engine=...)`.

### 4. Migration (D6)

On any verb, if the resolved store has no pin: call Run detection at the
anchor — one ready candidate → `set_pinned_engine` silently, proceed;
ambiguous → `engine-ambiguous` error instructing re-init with `--engine`.

### 5. Envelope + renderers

- `init` success and `status` payloads surface `data.pinned_engine`.
- New error codes wired with their `data.candidates` payloads.
- After your wiring, no `execute(engine=None)` caller remains — notify Run
  (their TODO) so the legacy branch can be dropped in a follow-up.

## Out of scope

- User-doc updates (`design/user-doc/**` claims "You do not pass an
  `--engine` flag" — now false; PM owns the doc pass after merge and will
  fold it into the taxonomy-realignment cycle).
- Fan-out / `workspaces test` (rejected alternative §1), env-var override
  (rejected), readiness caching (Open Q #18), MCP transport.

## Pinned file list

- **Edit**: `src/novetest/cli/app.py` (flags, error codes, anchor
  resolution call), `src/novetest/orchestration/workflows/init.py`,
  `src/novetest/orchestration/workflows/test.py` (+ siblings for the
  shared resolution helper), renderers as needed.
- **Create**: the resolution helper module (your placement call),
  discovery-bounds module, tests:
  `tests/unit/cli/test_engine_flags.py`,
  `tests/unit/orchestration/workflows/test_init_anchoring.py`,
  `tests/unit/orchestration/test_anchor_resolution.py`,
  `tests/integration/test_anchored_pin_e2e.py` (dual-marker fixture:
  init → engine-ambiguous → init --engine → test from a nested subdir
  works via walk-up → bare vs explicit-target series separation).

## Acceptance criteria

- Full suite green on the CI matrix; mypy clean.
- Snapshot: single-marker workspace `init → test` envelopes unchanged
  except the additive `data.pinned_engine`.
- All four D7 codes observable in integration tests, with `data.candidates`
  payload shapes pinned by snapshot.
- Legacy (pin-less) store fixture: first verb backfills silently
  (unambiguous case) — no user-visible change beyond the pin appearing.
- `WORKLOG.md` entry; handoff at
  `agent-comms/handoffs/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md`
  with the envelope diffs for PM's user-doc pass.

## Effort estimate (PM's read — challenge if you disagree)

~300 LOC production, ~500 LOC tests. The largest of the four slices —
one full cycle; surface via `agent-comms/questions/` before going wide if
it balloons.
