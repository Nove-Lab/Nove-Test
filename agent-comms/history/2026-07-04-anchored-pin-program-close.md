---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-07-04
slug: anchored-pin-program-close
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/history/2026-07-03-anchored-pin-wave1-reruns-and-windows-fastfollow.md
  - agent-comms/history/2026-07-04-anchored-pin-wave2-close.md
---

# History: anchored-pin program CLOSED — fast-follow 10/10, Wave 3 docs shipped

## Summary

The anchored-pin program (decision `2026-07-03-engine-selection-policy.md`,
question opened 2026-07-02) is **fully closed** — code, CI, manual
verification, and user documentation. This entry closes the last two
cycles: the windows-`./...` fast-follow and the Wave 3 consolidated doc
pass. No open engineering or documentation items remain from the program;
`agent-comms` pending is empty at close.

## Cycle 1 of 2 — windows `./...` normalization fast-follow

- **Fix** `fdf44d7` (Orchestration): pure-lexical guard
  `_has_all_dots_component` in `normalize_target_expression` — all-dots
  path components (`...`, `./...`, `a/.../b`; `..` excluded as genuine
  parent navigation) short-circuit to verbatim pass-through BEFORE any
  filesystem probe, removing the Win32 trailing-dot-strip dependency
  entirely. +2 regression tests, one making the Windows failure shape
  POSIX-observable via a recording `Path.exists` spy.
- **Merge + gate** (Main Branch): clean rebase onto `1f85ee9`, targeted 28
  passed, mypy 116 clean, full suite reconciled with the wave-2 cohort
  gate.
- **CI verdict (the wave-2 ⏳ bullet, now ticked)**: dispatch run
  **28675082033** at `0ccfe12` — **10/10**; windows-latest ×
  py3.11/3.12/3.13 all green on
  `test_normalize_engine_native_pattern_passes_through` (the exact three
  legs red at `7ddfc0f`, run 28671731628). Verdict commit `31db7e8`.
- **Manual Test: passed** (`21e677a`): spy-observed zero probes for the
  all-dots family even with a colliding real directory on disk; `../`
  still probes (no over-broadening); `./tests` canonicalization intact;
  real-CLI `run ./...` records `target_expression = './...'` verbatim.
  go/dotnet absent on host (third consecutive cycle — standing equip gap);
  Windows remains CI-verified by design.
- The Manual Test KNOWN-RED caveat from
  `2026-07-04-anchored-pin-wave2-close.md` is **retired**.

## Cycle 2 of 2 — Wave 3 consolidated doc pass (`1f85ee9`, PM)

Closed `pm-team-2026-06-25-user-doc-taxonomy-realignment` (rescoped
2026-07-03), 15 files, +305/−71. Envelope shapes sourced from
Manual-Test-observed merged behavior (`e6cafd8`), not from briefs:

1. **Anchored-pin surface** — languages ×3, quick-start ×3,
   troubleshooting ×2: replaced the now-false *"You do not pass an
   `--engine` flag"* and the fixed-priority silent-win docs with the pin
   model (init pins; verbs walk up; `engine-ambiguous` /
   `no-engine-detected` routing with `data.candidates` shapes;
   host-dependent viability rule; transient `--engine` override; lazy
   backfill; reset pin-carry). Repaired agent/quick-start's dangling
   walk-up anchor by writing the missing section.
2. **`--reruns` surface** — all five "never fires today" `flaky_suspected`
   annotations replaced with the ratified whole-run semantics (empty
   `test_id` on multi-test divergence); worked usage added.
3. **Taxonomy SSoT** — `recommendation-synthesis.md` §8 "Closed taxonomy
   v1 — authoritative list" + future-change checklist, cross-linked from
   all four category-listing pages.
4. **`rm -rf .novetest` review** — every remaining occurrence is an
   uninstall or corrupt/wipe-failed context where `reset --confirm`
   cannot help: verified correct as-is, zero edits.
5. Manual Test Observation 2 (zero-collected explicit target reports
   `passed`) documented as troubleshooting cautions in human+agent docs.

## Program totals (2026-07-02 question → 2026-07-04 close)

- 1 binding decision (D1–D7) + 1 ratification amendment; 8 engineering
  slices across 6 teams (Memory, Run, Regression, Orchestration ×3 incl.
  two fast-follows, Coverage, Localization) + 1 PM doc pass; 2 Windows
  fast-follows caught post-merge by the CI matrix and closed at 10/10.
- Structural wins: no run-time engine guessing anywhere; D5 engine-boundary
  rule enforced in all four cross-run consumers; the
  engine_selector/readiness two-priority-lists latent bug dead by design;
  Open Q #17 resolved; docs and code taxonomy-aligned with a pinned SSoT.

## Follow-up candidates (NOT scheduled — surface to CEO when relevant)

1. Zero-collected explicit target → `status: "passed"` (documented as a
   caution; a warning or distinct status is a small Run-team slice if
   demand surfaces — Manual Test Observation 2).
2. Ambiguity message wording "Multiple viable engines detected" when zero
   are toolchain-ready (cosmetic — Observation 3).
3. `reset` success envelope carries no `pinned_engine` (byte-stability
   choice — Observation 4).
4. Manual-Test host equip gap: go + dotnet absent three cycles running.
5. Q5 from the 2026-07-02 question (foundations.md decorator-registry
   stale claim) remains parked and untracked by any task.

## Retired with this close

Fast-follow transients (task brief, kick-back question `main-branch-team-
2026-07-04-windows-dotdotdot-normalization-ci-red` [resolved-as-routed],
verification, handoff, findings — full text preserved at `21e677a`), the
resolved Wave-3 PM task file, and the resolved marketing-pm
install-path-website-integration task file (its arc closed 2026-07-02 in
its own history entry).
