---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-16
slug: phase0-closure-partial
---

# History: Phase 0 closure — 2/3 DoD closed, #3 deferred to next cycle

Two parallel slices addressed both Phase 0 RED root causes diagnosed in
`history/2026-05-16-phase0-gha-attempt-red.md`. Run team's portability
fix proved out on the 9-cell CI matrix; Release team's YAML fix proved
out on 3 of 4 PyApp build cells. The 4th cell (`macos-x86_64`) is
blocked on GHA infrastructure (macos-13 runner pool saturation), not on
the fix itself. PM ticked DoD #1 and #2 with a footnote on #2; DoD #3
deferred to a next-cycle Release polling/completion task.

## Cycle summary

| Slice | Commit on main | Verdict |
|---|---|---|
| Run: `test_pytest_unavailable_raises_typed_error` cross-platform (Option A — `tmp_path` fake executable) | `fc79209` | passed (Manual Test + ci.yml 9-cell green) |
| Release: `release-test.yml` Wrap-wheel absolute-path fix | `855f56a` | **partial** — 3/4 PyApp targets green, macos-x86_64 stuck in GHA queue |

## What closed

- **Phase 0 DoD #1 ticked.** Run team's Option A fix (`tmp_path`-rooted
  always-fail script branched on `sys.platform`) preserved the original
  test intent (binary spawns, exits non-zero, JSON report absent →
  adapter raises `AdapterInvocationError`). `ci.yml` run `25955963916`
  on commit `c05751d` produced 9/9 green cells across
  Linux/macOS/Windows × Python 3.11/3.12/3.13 — the first 9-cell green
  observation in this project's history.

- **Phase 0 DoD #2 ticked (with footnote).** Release team's YAML fix
  captures the wheel path as absolute (`$GITHUB_WORKSPACE/dist/...`) so
  the subsequent `cd pyapp-src` does not invalidate it before PyApp's
  `build.rs` reads it. `release-test.yml` run `25955972426` produced
  3/4 PyApp binaries (`linux-x86_64`, `linux-aarch64`, `macos-arm64`)
  + `.sha256` sidecars + `novetest --version` smoke test green on each.
  Identical YAML step exercised on 3 different runner types =
  behaviorally verified. The 4th cell (`macos-x86_64`) is blocked on
  GHA infrastructure, not on the fix path; PM judged this sufficient
  for tick + footnote.

## What stayed open

- **Phase 0 DoD #3 unticked.** `install-script-e2e` job (the
  curl-pipe-sh end-to-end gate) auto-skipped because `needs: build`
  cannot complete while the macos-x86_64 cell is queued. The fix path
  is verified; the verification gate is GHA-infra-dependent. Deferred
  to a next-cycle Release task: either wait for the queue to drain and
  re-observe, or transition to `macos-universal2` (drop the macos-13
  Intel target entirely; ship a single universal2 binary wrapped on the
  `macos-arm64` runner). PM will decide the wait-vs-transition timeout
  when the next cycle is dispatched.

- Phase 2 DoD #2/#3/#4 still open (next cycle candidates).

## Load-bearing learnings

### 1. GHA `macos-13` runner pool is saturated for hours

Both `release-test.yml` runs `25954755663` (prior RED, 06:15Z) and
`25955972426` (this fixed run, 07:18Z) had their `macos-x86_64` cell
sit in queue past the 5-hour mark while every other runner type
(`ubuntu-latest`, `macos-latest` = arm64, `ubuntu-22.04-arm`) picked up
jobs within seconds. Not a workflow defect; pure runner availability.
GitHub is in the process of deprecating macos-13 runners, so this
saturation may be steady-state rather than transient.

**Mitigation options for the next-cycle task:**
- (a) wait for the pool to drain (indefinite)
- (b) transition to `macos-universal2`: PyApp/python-build-standalone
  ships universal2 macOS binaries; we can drop `macos-x86_64` from the
  matrix and ship a single `macos-universal2` artifact wrapped on a
  `macos-arm64` runner. The `install.sh` arch-detection branch also
  needs a small update (treat `Darwin x86_64` → `macos-universal2` if
  no x86_64-specific binary is published).

### 2. GHA "Re-run failed jobs" preserves successful job outcomes in-place

When CEO triggered an in-place macos-x86_64 re-run at 12:13Z, the API
showed the same run's `startedAt` advancing to 12:13:22Z but the 3
successful jobs kept their original `success` / `completedAt: 07:20Z`
values. The `gh run view --json status` field reads "queued" while only
the failed-or-stuck job is being re-attempted.

**Principle for future GHA observation passes:** per-job
`startedAt`/`conclusion` is ground truth; the run-level `status` only
lifts to `completed` when every job is terminal.

### 3. Local YAML parsing is not a substitute for GHA execution (carried
    forward from prior cycle)

Reinforced this pass: both root causes (Run's `/bin/false`, Release's
relative-path) are the kind that only surface at execution time. Local
`yaml.safe_load` + local `pytest -q` are necessary but not sufficient
for any workflow / portability-sensitive change. Live observation on
real CI is the only valid verification.

### 4. Cargo build was unexpectedly fast (~80s per target on warm cache)

The runner-level `~/.cargo` cache appears warm across re-runs even
without an explicit `actions/cache` block. The cache optimization the
prior cycle's history flagged as optional truly is optional — do not
add it pre-emptively unless a future RED-iteration loop demonstrates
otherwise.

### 5. Self-documenting fixes from both teams this cycle

Both teams shipped fixes whose inline comments quote the original
failure mode verbatim:
- Run team's test docstring explicitly explains why `/bin/false` was
  abandoned (Linux ships `/bin/false`, macOS ships `/usr/bin/false`,
  Windows ships neither).
- Release team's YAML comment quotes PyApp v0.22.0's exact panic
  message (`"Project path is not a file: dist/novetest-...whl"`).

These are the kind of comments that prevent a future maintainer from
"simplifying" the fix away. Manual Test flagged both as
maintainer-friendly prose. Principle for future fixes that touch
portability or workflow YAML: spell out the failure mode in a comment
so the next agent doesn't have to re-derive it.

## Process notes

- **Two parallel teams worked without coordination friction.** Run team
  touched `tests/unit/run/adapters/test_pytest_adapter.py`; Release
  team touched `.github/workflows/release-test.yml`. Disjoint file
  scopes meant Main Branch merged Run first (`fc79209` ff from
  `1fddb94`), then rebased Release's branch onto `9771501` (cleanly,
  no conflicts) and merged as `855f56a`. The merge-before-handoff
  pattern Release's task spec authorized worked correctly: Release
  proceeded with self-trigger + observation after the YAML landed on
  main.
- **Two findings, both passed, both noted self-documenting comment
  quality.** Manual Test's findings were short and clean — the
  verification doc's "spot-check only, ≤10 min" framing was honored.
- **PM judgment call: DoD #2 tick with footnote.** Strict reading
  would have held #2 until all 4 cells green; behavioral verification
  on 3 different runner types running the identical YAML step was
  judged sufficient evidence. Footnote in `delivery-phasing.md`
  references this history entry so the asymmetry is permanent
  metadata, not lost in commit prose.
- **Prior RED run `25954755663` cancelled** (via `gh run cancel`) to
  keep `gh run list` output tidy. The run carries no useful signal
  beyond what's already captured in this history entry.

## Follow-ups carried forward (PM queue for next cycle)

1. **Release polling/completion task (blocking for DoD #3).** Either
   (a) wait for `macos-x86_64` cell in run `25955972426` to drain and
   observe `install-script-e2e` green, or (b) transition to
   `macos-universal2` (drop `macos-x86_64` matrix target + update
   `install.sh` arch detection). PM decides wait timeout when
   dispatching. Recommended: wait 1-2 hours, then fallback to
   universal2 if still blocked.

2. **Phase 2 next slice candidate.** Most natural: `novetest coverage
   show <run_id>` + `coverage diff <id1> <id2>` CLI verbs
   (Orchestration team). Closes Phase 2 DoD #2. Envelope projection
   extends the now-frozen `coverage_outcome` shape from
   `decisions/2026-05-16-coverage-outcome-envelope-shape.md`. First
   slice where `kind: "unavailable"` becomes reachable end-to-end.

3. **Carried from prior cycle (still deferred):** Run team
   `artifact_dir.resolve()` 1-line hardening; Coverage `meta`
   absence behavior (informational); getting-started doc for the
   dev-deps triple needed when consuming novetest as a wheel.

## References

Transient comms files (2 tasks, 2 handoffs, 2 verifications, 2
findings) deleted in the same commit as this entry. Two commit hashes
are the authoritative source-diff anchors: `fc79209` (Run portability)
and `855f56a` (Release YAML path fix).

Permanent items touched or created this cycle:
- `delivery-phasing.md` Phase 0 DoD #1 ticked; DoD #2 ticked with
  footnote referencing this entry; DoD #3 still unticked.
- This history entry.

No `decisions/` entry added this cycle.
