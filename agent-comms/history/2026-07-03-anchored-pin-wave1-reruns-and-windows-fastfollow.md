---
from: novetest-pm-team
to: all
type: history
created: 2026-07-03
slug: anchored-pin-wave1-reruns-and-windows-fastfollow
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md
  - agent-comms/questions/orchestration-team-2026-07-03-reruns-replay-api-mismatch.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Cycle close: anchored-pin Wave 1 (Memory/Run/Regression) + `--reruns` + Windows fast-follow

Five cycles closed together, 2026-07-03. Merges: `0a6cddf` (reruns),
`4196ee9` (memory pin), `0825f64` (run dispatch), `8b2dce8` (regression D5),
`886dc09` (fast-follow). Batch verified at `b982fad`; final state proven by
CI run `28643184018` — **10/10 SUCCESS** including the 3 previously-red
`windows-latest` jobs. All five Manual Test verdicts PASSED (run slice's
PARTIAL superseded by the fast-follow).

## What shipped

- **`novetest test --reruns N`**: `flaky_suspected` is now reachable from a
  single user command (previously dead code — matcher could never fire).
  Whole-run replay adaptation (see Lesson 3). Replay reruns are first-class
  Memory entries (1 original + N replays in `memory list`).
- **Memory pin primitives** (dormant until Wave 2): `pinned_engine` field in
  store.json (additive, tolerant, NO schema bump — stays v1),
  `get/set_pinned_engine` (write-time six-pair validation; malformed shape →
  `ProjectStoreCorruptError`, never silent None), `find_nearest_store`
  upward walk (metadata-less `.novetest/` dirs are walked past). All four
  symbols module-path-only (`novetest.memory.project_store`), NOT re-exported
  in `__init__` — same contract whose violation caused the 2026-06-25
  reset-verb kick-back; this time the consumer brief pins it.
- **Run detection API**: `detect_engine_candidates` / `probe_engine` /
  `list_supported_engine_pairs` single source of truth; `execute(engine=…)`
  pinned dispatch (readiness still gated, no re-detection). The §4.1 latent
  bug (selector vs readiness disagreeing on Java's rank) is dead — pom+go.mod
  fixture proves readiness and dispatch agree. `execute(engine=None)` legacy
  branch remains until Orchestration removes the last caller (their TODO).
- **Regression D5**: baseline selection filters by target run's
  `engine_name` via shared `resolve_baseline_for_run`; `inspect`/`status`
  rerouted through it (three consumers agree by construction). Cross-engine-
  only priors → `no-comparable-baseline` with NEW `detail` form
  `"<target> (engine=<name>)"`.

## Lessons (load-bearing)

1. **Envelope-bound paths must be `.as_posix()`.** `str(Path.relative_to())`
   yields `\` on Windows; evidence strings flow into AI-agent-consumed
   envelopes and must serialize identically on every platform. The run slice
   violated its own test's (correct) contract; Linux-only pre-merge gates
   STRUCTURALLY cannot catch this class — it surfaced only on post-merge
   Windows CI. Same-day loop: found 11:00 → brief → one-line fix (`886dc09`,
   fix + docstring only, zero test changes) → merged → 10/10 by 15:40.
   Note: 4 pre-existing `str(relative_to)` sites in cargo/junit/dotnet
   adapters are artifact-log keys (not envelope evidence), deliberately left
   alone; optional hygiene audit.
2. **Pre-merge Windows spot-run is unowned.** Main Branch attempted a
   `workflow_dispatch` spot-run for the path-sensitive diff and got HTTP 403
   (session gh identity lacks dispatch rights). Unresolved: grant dispatch
   rights or designate the CEO as executor for path-sensitive diffs
   (`relative_to`/`glob`/`os.sep` in envelope surfaces).
3. **Brief pseudocode must be validated against shipped API signatures.**
   The reruns brief pinned a per-failed-test replay loop that was
   unimplementable against the real Replay API (no `target=` param;
   results keyed by original run id would overwrite; N×reruns full-suite
   cost). Team adapted to ONE whole-run attempt, kept the frozen surface
   intact, and filed a ratification question rather than silently diverging
   — correct routing. **Ratification still open** at close time
   (`orchestration-team-2026-07-03-reruns-replay-api-mismatch.md`); the
   amendment target is the decision doc (the brief is deleted by this
   close). Behavioral nuance for the Wave 3 doc pass: multiple flaky tests
   in one run → ONE `flaky_suspected` with empty `test_id`.
4. **Parallel slices coupling at merge worked.** Memory's pin validation
   imports Run's consolidated `list_supported_engine_pairs` — written
   against a sibling in-flight slice, verified live at batch HEAD (M3).
   Batch verification at a single HEAD with per-slice findings + explicit
   batch-level caveat attribution kept blame assignment clean.
5. **D5 audit found 3 engine-blind sites outside Regression's ownership**
   (`regression-team-2026-07-03-d5-cross-run-audit.md`, open): (A) Coverage
   `compare_coverage_facts` — the only genuine corruption path, reproduced
   by Manual Test (`coverage diff <pytest_run> <cargo_run>` emits a
   meaningless CoverageDelta, zero guard); (B) Localization regression-prior
   selection (noise — FLUCCS reweighting silently degrades in mixed stores);
   (C) `orchestration/workflows/test.py:290` same pattern (noise). Routing
   decision pending with CEO.

## Carry-forwards

- **Wave 2 (Orchestration anchored-init) is UNBLOCKED** — both dependencies
  merged, CI green. Before dispatch, PM should amend the brief: fold the
  `ProjectStore.to_dict()` explicit-null vs persistence-omits asymmetry note
  (Memory findings #2), and — if CEO routes D5-C that way — the
  `test.py:290` one-liner (`resolve_baseline_for_run` swap; handoff
  documents the seam-migration pattern: monkeypatches on removed
  `find_runs_for_target` hard-fail, swap stubs in the same slice).
- **Wave 3 PM doc pass** (task `pm-team-2026-06-25-user-doc-taxonomy-realignment.md`)
  now owes the `--reruns` documentation too; trigger = anchored-pin merge.
- Regression, at leisure: equal-`created_at` tie yields a diagnostically
  misleading engine-suffixed detail (tie eliminated the candidate, message
  blames the engine); distinct detail form or run_id tie-break.
- Document `check_regression_availability` any-sibling vs strictly-older
  divergence before its first caller wires it (reviewer note).
- GOTCHAS additions this wave: `PYTHONPATH` leak (host ROS2 profile;
  `env -u PYTHONPATH` prefix).
