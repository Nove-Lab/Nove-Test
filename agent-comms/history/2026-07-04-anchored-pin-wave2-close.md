---
from: novetest-pm-team
to: all
type: history
status: archived
created: 2026-07-04
slug: anchored-pin-wave2-close
related:
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/history/2026-07-03-anchored-pin-wave1-reruns-and-windows-fastfollow.md
  - agent-comms/tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md
---

# History: anchored-pin Wave 2 close — D1–D7 fully live; one Windows fast-follow routed

## Summary

Wave 2 of the anchored-pin program (decision
`2026-07-03-engine-selection-policy.md`) is closed: all three slices merged,
Main-Branch-verified, and Manual-Test-passed. The anchored-pin model is now
**fully live on `main`** — every D1–D7 binding has shipped, and D5
("cross-run analyses never cross an engine boundary") is now enforced in
all four consumers (Regression, Orchestration inspect/status/test-outcome,
Coverage, Localization). One Windows-only normalization defect surfaced
post-merge in CI and was kicked back per charter; the fast-follow is routed
and is the only open engineering item from the program.

## The three slices

| Slice | Commit | Merge gate | Manual Test |
|---|---|---|---|
| Orchestration — anchored init + verb walk-up + pin dispatch (D1–D7, incl. Finding C §2b) | `76a4ffb` | 1511/5/0, mypy 116 clean | **passed** (Windows `./...` caveat noted) |
| Coverage — cross-engine guard in `compare_coverage_facts` (D5 Finding A) | `17a61f8` | same cohort gate | **passed** |
| Localization — engine-scoped regression-prior via `resolve_baseline_for_run` (D5 Finding B) | `4818642` | same cohort gate | **passed** |

Main Branch verified the cohort at `7ddfc0f`; Manual Test exercised every
D1/D4/D7 decision-table outcome on the real CLI (single-marker pin,
markerless refusal + bounded discovery incl. `$HOME` scan refusal,
dual-marker `engine-ambiguous`, deep-subdir walk-up, transient `--engine`
override without re-pin, lazy pin backfill on legacy stores, `reset`
re-create guard) — findings recorded at `e6cafd8`, all verdicts **passed**,
no regressions found.

## The CI red + kick-back (open item)

Post-merge CI at the wave-2 tip (dispatch run `28671731628`): **7/10** —
ubuntu×3, macos×3, perf green; windows×3 red on exactly ONE test:
`normalize_target_expression` mangles go's `./...` to `...` because Win32
strips trailing dots, so `(anchor / '...').exists()` returns True and the
existing-subpath branch fires. Unobservable on POSIX by construction — the
Linux merge gate was honestly green. Same failure class as the wave-1
windows-path-separator fast-follow; main NOT rolled back (precedent).

Routing (CEO-approved close): Main Branch kick-back question resolved as
routed; fast-follow brief filed to Orchestration —
`tasks/orchestration-team-2026-07-04-windows-dotdotdot-normalization-fastfollow.md`
(pure-lexical all-dots guard recommended; exit condition = windows matrix
green, CI 10/10 re-dispatched). The kick-back question file is retired when
that cycle closes.

## Program status after this wave

- **Live**: pins at init; upward-walk verb resolution; no run-time engine
  guessing anywhere; bounded discovery; D7 error surface
  (`no-engine-detected`, `engine-ambiguous`); transient `--engine`
  override; lazy migration; engine-scoped cross-run analysis in all four
  engines' consumers.
- **Known-red**: go `./...` explicit-target pass-through on Windows only,
  until the fast-follow lands.
- **Next (Wave 3, PM)**: user-doc taxonomy realignment
  (`tasks/pm-team-2026-06-25-user-doc-taxonomy-realignment.md`, rescoped
  2026-07-03) + documenting `--engine`/`--reruns` + the ratified reruns
  nuance (single `flaky_suspected`, empty `test_id` on multi-test
  divergence) + removing the now-false *"You do not pass an `--engine`
  flag"* doc claim.

## Retired with this close

Per the transient-channel convention (wave-1 precedent `72d0f5d`): the
three wave-2 task briefs, three handoffs, three verifications, three
findings (verdicts preserved above; full text in git history at `e6cafd8`),
and the two questions resolved during wave-2 prep (reruns ratification —
answer preserved in the 2026-06-25 decision's Amendment 2026-07-03; D5
audit routing — answer preserved in the routed briefs and this entry).
