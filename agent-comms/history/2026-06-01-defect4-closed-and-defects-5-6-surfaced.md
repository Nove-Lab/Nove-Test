---
from: novetest-pm-team
to: all
type: history
created: 2026-06-01
slug: defect4-closed-and-defects-5-6-surfaced
related:
  - agent-comms/history/2026-06-01-localization-phase4-modes-and-cargo-defect-cascade.md
  - agent-comms/tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md
  - agent-comms/tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md
---

# History: 2026-06-01 cycle — Defect 4 CLOSED + Defects 5/6 surfaced during Manual Test exploration

Single-team Localization fix-up. Defect 4 (`novetest localization
latest` rejecting non-per-test runs) verdict **passed** byte-accurate
on merged tip `4b5fd1d`. Manual Test exploration **discovered + root-
cause-localized two additional pre-existing bugs** (Defect 5, Defect 6)
along the new surface. Both queued as follow-up slices.

## Slices in scope

| Team | Commit | Verdict |
|---|---|---|
| Localization | `4b5fd1d` | passed |

Cycle: dispatch → handoff → verification (`d6af3a6`) → findings
(`40cac62`) → close (this commit).

## What shipped

`check_localization_availability` gate in `retrieval.py` relaxed
from `mapping_granularity == "per-test"` to "non-tombstoned + has
failed tests". The 3-mode dispatcher in `derive_localization_findings`
already handled all three modes (sbfl_per_test / sbfl_aggregate /
failure_proximity) — the gate was just over-restrictive due to a
historical artifact.

After this fix:
- `novetest localization latest` works for all 3 mode-dispatch paths
- All 4 supported languages get the convenience verb working
- Persisted findings reachable through both `<run_id>` AND `latest`
  verbs identically

Surgical change: 2 src files modified (retrieval.py gate + docstring,
derive.py docstring refresh), ZERO new src files (count stays 72),
+3 net tests. Gate green: 762+5 on equipped host.

## DoD bullets ticked in `delivery-phasing.md` this close

**None.** This was a discoverability bug-fix, not a phase-tracked
feature. Phase 4 §4 #2 was already ticked at the prior close
(`97285e5`). Phase 4 §4 #3 (perf NFR) remains the only open Phase 4
bullet.

## What the cycle accomplished (product framing)

`novetest localization latest` is the **user-facing convenience verb**
for "show me localization for the most recent analyzable run". Before
this slice it silently returned "no analyzable runs" for 3 of 4
supported languages (cargo, go, jest) AND any pytest run without
`--coverage` (the failure_proximity case). Users had to know the
explicit `<run_id>` workaround.

After this slice the convenience verb is universally functional. AI
agents and humans both stop needing the workaround. This is the LAST
piece of Phase 4 §4 #2's user-facing surface: as of `4b5fd1d`,
"fault localization" works through any verb for any supported
language regardless of coverage mode.

## Defect 5 surfaced — cache-read path ignores `--formula` / `--top-n` flags

Manual Test discovered + **root-cause-localized empirically**:

```
$ novetest localization latest                          # baked into cache: ochiai, top_n=10
$ novetest localization latest --formula op2 --top-n 3  # silently ignored
  → "formula": "ochiai", "top_n": 10                    # WRONG: flags dropped

$ rm -rf .novetest/localization                         # cache invalidation
$ novetest localization latest --formula op2 --top-n 3  # fresh derive
  → "formula": "op2", "top_n": 3                        # CORRECT: flags applied
```

Root cause: the cache-read path in the CLI surface (orchestration
layer's `localization` workflow) reads persisted findings without
re-deriving when CLI flags differ from baked-in state. The flag-
handling logic itself works (post-cache-delete probe proves this).
The bug is purely cache invalidation.

Severity: medium. Defaults always work; only users explicitly
passing `--formula` / `--top-n` after a first call hit this. Workaround
exists (delete cache).

**Queued**: `tasks/localization-team-2026-06-01-localization-cache-flag-invalidation-defect5.md`

## Defect 6 surfaced — `status.sub_reports.*` disconnected from on-disk state

Manual Test reproduced:

```
$ novetest status               # → sub_reports: {coverage: "unavailable", localization: "unavailable", ...}
$ novetest inspect <run_id>     # → coverage_outcome.kind: "fact-set", localization_outcome.kind: "fact-set"
$ novetest localization latest  # → kind: "fact-set" (post-Defect-4 fix)
$ ls .novetest/{coverage/facts,localization/findings}/run_<id>/*.json
  → both files exist, both valid
```

`status.sub_reports.*` reports `unavailable` for engines whose facts
ARE on disk AND whose dispatch verbs work correctly. AI agents
consuming `status` as the "is X available?" gate will incorrectly
skip downstream invocations.

Manual Test's hypothesis: the `status` workflow's precondition probe
likely uses the pre-Defect-4 `mapping_granularity == "per-test"`
semantics (or a similar over-restrictive check) that was relaxed in
`retrieval.py` but not in the `status` reporting layer. **Symmetric
fix to Defect 4** likely applies, but in a different file.

Sub-observation also bundled: `inspect.coverage_outcome.percent_covered`
returns `None` while on-disk `summary.percent_covered` is `85.71`.
Looks like `inspect` reads the wrong nested path (top-level vs
`summary.*`). Bundle into Defect 6 triage.

Severity: medium. `status` is the primary "is X available?" gate for
AI agents; lying about it is worse than just being inconvenient.

**Queued**: `tasks/orchestration-team-2026-06-01-status-sub-reports-staleness-defect6.md`

## Process notes

### Manual Test exploration discovered both new defects

Defects 5 and 6 were NOT in the verification doc's scenarios. Manual
Test discovered them while walking the new "all 3 modes reachable
through `latest`" surface — the exact kind of exploratory probing
their charter exists for. They produced:

- Reproducers for both (verbatim, copy-paste runnable)
- Root-cause localization for Defect 5 (proved the flag-handling
  logic works; isolated the bug to cache invalidation)
- Hypothesis for Defect 6 (symmetric fix to Defect 4)

This is the **best argument for the Manual Test / Main Branch
boundary correction** (process correction from yesterday's history,
commit `2747fba`). Manual Test's exploratory territory produces
high-value discoveries; Main Branch's gate-only territory keeps
merges deterministic. Both surfaces were validated this cycle.

### Verification doc nit — Main Branch Probe C path stale

Manual Test caught: Main Branch's documented path for Defect 5 cache
probe (`.novetest/store/projects/*/localization/`) doesn't exist.
Actual layout is `.novetest/localization/findings/run_*/`. The
wildcard silently matches nothing, so naive copy-paste of Probe C
would falsely conclude flags don't work AT ALL (rather than
"work-on-cache-miss"). Manual Test corrected, re-ran, and root-cause-
localized correctly.

Pattern: **verification doc nit pattern returns** (after one
gap-cycle). The "informal best practice" from prior history's
suggestion ("Main Branch dry-runs snippets against merged tip
before filing") was held last cycle but not this one. Recommendation
to Main Branch: re-adopt the dry-run check, OR add a small helper
script `tools/locate_findings.sh` to print correct store paths
(more durable than relying on doc author's memory).

PM action: do NOT queue as a separate slice (process improvement,
not load-bearing). Carry-forward note in this history.

### 4-defect cascade now has a 4+2=6-defect tail

Phase 4 §4 #2's landing arc spans 5/31 → 6/1 → 6/1 (this cycle):

| # | Defect | Resolved by | Status |
|---|---|---|---|
| 1 | cargo-llvm-cov `--no-fail-fast` blocks LCOV on failures | `18fc224` | closed prior cycle |
| 2 | fixture panic site ≠ bug site | `3ccfd72` | closed prior cycle |
| 3 | parser catch-all + stdlib pollution | `05f86bc` | closed prior cycle |
| 4 | `localization latest` rejects non-per-test runs | `4b5fd1d` | **closed this cycle** |
| 5 | CLI flags ignored on cache-read path | (queued) | open |
| 6 | `status.sub_reports.*` disconnected from on-disk state | (queued) | open |

Defects 5+6 are NOT regressions of THIS cycle's fix — both pre-existed
(Defect 5 since Localization CLI shipped 5/29; Defect 6 since status
workflow shipped Phase 1). The 3-mode-dispatch surface change just
made them reachable / observable. Net: 4 → 6 (2 carry-forwards).

## Other deferred items (visible to future PM)

1. **Defect 5** (cache invalidation on flag mismatch) — queued.
2. **Defect 6** (status.sub_reports staleness) — queued.
3. **Phase 4 §4 #3** (perf NFR-LOC-002) — only remaining Phase 4
   bullet.
4. **Phase 3 JUnit / dotnet** — gated on Open Q #4 / #5.
5. **UX normalizations** (low-priority polish, optional pre-MVP):
   - `metadata` shape asymmetry across modes (per-test `{}` vs
     aggregate/failure_proximity `{changed_files_count, regression_reweighted}`)
   - File-path absoluteness asymmetry (`failure_proximity` emits
     absolute paths; others emit repo-relative)
6. **Memory `delete` polish** — long-standing carry-forward.
7. **Envelope freeze v2 amendment** for failure_proximity deviation
   — low-priority informal.
8. **Verification-doc dry-run check** — informal Main Branch best
   practice; re-adopt OR formalize with `tools/locate_findings.sh`.

## What the next cycle is

CEO picks from:
- **Defect 5 + Defect 6** (parallel, both small, both medium-severity)
- **Phase 4 §4 #3** (perf NFR — Phase 4 final close)
- **Phase 3 JUnit / dotnet** (gated on Q resolution)

PM recommendation: **parallel Defect 5 + Defect 6** is the cleanest
next slice. Both small, both with clear reproducers + root-cause
hypotheses, both fix product-credibility surfaces (AI agents will
trust `status` and `--formula` after the fix). Phase 4 §4 #3 perf
NFR can follow.
