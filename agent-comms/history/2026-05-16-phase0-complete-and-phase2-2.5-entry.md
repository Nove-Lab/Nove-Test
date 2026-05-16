---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-16
slug: phase0-complete-and-phase2-2.5-entry
---

# History: Phase 0 fully closed + Phase 2 DoD #2 + Phase 2.5 entry (coordinated 3-slice cycle)

Three parallel slices across three teams landed under one coordination
cycle. **Phase 0 fully closed for the first time in this project's life**
(DoD #3 — the curl-pipe-sh end-to-end observation — was the long-standing
last open bullet). Phase 2 DoD #2 closed via `coverage show / diff`
CLI verbs. Phase 2.5 entry infrastructure (jest native adapter) landed
to verify the adapter pattern generalizes beyond pytest.

## Cycle summary

| Slice | Commit | Verdict | DoD closed |
|---|---|---|---|
| Orchestration: `coverage show` + `coverage diff` CLI verbs | `50c9170` | passed | Phase 2 #2 |
| Run: jest Native Engine adapter Phase 1-equivalent (execution only) | `e0acce6` | passed | (none — Phase 2.5 entry infra) |
| Release: macOS targets → universal2 (lipo-fused fat binary, drop macos-13) | `09eda94` | passed | Phase 0 #3; #2 footnote updated |

Release-test GHA run `25963163742` on origin/main `a018dd7`:
**3/3 builds + install-script-e2e all `success` in 3m4s**. First-ever
end-to-end observation of the curl-pipe-sh install path.

## What closed — Phase 0 fully done

| DoD bullet | State now |
|---|---|
| #1 9-cell CI matrix green | ✅ ticked prior cycle |
| #2 Signed binary builds | ✅ ticked, **footnote updated** — matrix now 3-cell (linux-x86_64, linux-aarch64, macos-universal2); all 3 green on run `25963163742` |
| #3 curl-pipe-sh end-to-end | ✅ ticked this cycle — `install-script-e2e` job ran twice in the same job (clean install + idempotent re-install), both green, both returning valid `novetest/v1` envelope |
| #4 SHA-256 mismatch loud abort | ✅ ticked prior cycle |
| Other Phase 0 bullets | ✅ ticked prior cycles |

**Phase 0 is the first phase to fully close.** The project can now stop
treating distribution as in-flight; Release team reverts to standby
until next MVP release cycle (which is its charter's intended cadence).

## What closed — Phase 2 #2

`novetest coverage show <run_id>` and `novetest coverage diff <id1> <id2>`
are real handlers (no longer stubs). Both project to the envelope:

- `show` reuses the frozen `coverage_outcome` v1 shape verbatim
  (decisions/2026-05-16-coverage-outcome-envelope-shape.md).
- `diff` introduces the `coverage_delta` v1 shape, frozen in this
  cycle's new
  `decisions/2026-05-16-coverage-delta-envelope-shape.md`.

**Milestone:** the `kind: "unavailable"` outcome is reachable from the
CLI end-to-end for the FIRST time. Prior cycle's Manual Test had to
construct it via the Python API; now `novetest coverage diff <covered>
<not-covered>` produces the shape directly. AI-agent consumers can now
interrogate "do I have coverage for this run?" via a single shell
invocation.

## What landed — Phase 2.5 entry (jest infra)

`novetest run` now works on JavaScript/TypeScript workspaces. `cd` into a
folder with `package.json` declaring jest in devDependencies, run
`novetest run __tests__/`, get the same engine-agnostic envelope as
Python — with `engine == "jest"`, per-test node-ids, pass/fail status.

Coverage emission for jest is **deferred** — `--coverage` is accepted
but no-op (silently produces `coverage_outcome.kind: "unavailable"`).
The Coverage team's future Istanbul-parser slice is the companion that
will turn it real.

CI matrix does NOT include Node.js yet. Integration test
`tests/integration/run/test_jest_basic.py` skips on every CI cell
(documented). A Release-side follow-up to add Node.js to the matrix is
queued as a carry-forward (this cycle deliberately did not bundle it
to keep slices small).

## What stayed open

- **Phase 2 DoD #3** (`inspect` Coverage section) — next slice. Reuses
  both `coverage_outcome` and the now-frozen `coverage_delta` shapes.
- **Phase 2 DoD #4** (NFR-COV-002 50k-location perf) — needs perf
  fixture proposal + `performance-engineer` recruit.
- **Phase 1 DoD #12** (integrated `novetest test [target]`) — Phase 6
  dependency, intentionally still open.

## Load-bearing learnings

### 1. lipo-fuse is the universal2 path with PyApp v0.22.0

PyApp v0.22.0 does NOT natively support universal2 wraps —
`astral-sh/python-build-standalone` publishes per-arch tarballs only,
and PyApp's `PYAPP_DISTRIBUTION_SOURCE` env var resolves to a single
arch. Release team's diagnostic-first check (read PyApp + python-build-
standalone docs/API listing) caught this BEFORE coding, and pivoted to
the `lipo -create` fuse path: two cross-target `cargo build`s (one for
`aarch64-apple-darwin`, one for `x86_64-apple-darwin`) on the
`macos-latest` runner, then `lipo -create` to fuse them. `lipo -archs`
sanity prints `x86_64 arm64` confirming the fuse worked.

If a future PyApp release ships native universal2, the wrap step can
simplify to a single cargo build. The inline YAML comment quotes the
constraint verbatim so the future maintainer knows what to delete and
what to keep.

### 2. GHA run-level `cancelled` vs per-job conclusions (re-emphasized)

`gh run view --json conclusion` at the run level can read `cancelled`
or `queued` while individual jobs have terminal `success` /
`failure` conclusions. Always use per-job conclusions as ground truth:

```sh
gh run view <id> --json jobs -q '.jobs[] | {name, conclusion}'
```

Repeatedly tripped agents this cycle (and the prior); now codified.

### 3. Verification-doc envelope-path drift — fix landed this cycle

Two cycles' Manual Test findings flagged the same pattern: verification
docs reference `data.memory_entry.run_reference.run_id` which doesn't
exist (correct paths: `data.memory_entry.entry_id` or
`data.memory_entry.run_record.run_reference.run_id`). This cycle PM
codified the fix structurally: added "Verification-doc envelope/API
path discipline (REQUIRED)" to the Main Branch charter's "After merge"
section. Any future verification author must pin envelope paths
verbatim from a freshly-loaded run, not from memory or the task spec.

If a 3rd occurrence still happens in a later cycle despite the charter
rule, escalate to a structural fix (e.g. a test-the-doc smoke that
runs verification scenarios verbatim against the merged code).

### 4. `uv run --with /local/path` cache staleness — documented in GOTCHAS

Manual Test hit a uv-side cache quirk: repeated
`uv run --with /home/yjshin/dev/Nove-Test novetest <verb>` invocations
returned stale wheel behavior (stub-era envelopes) even with
`--refresh`. Worked around via the `NOVETEST_HOME=<store> + uv run`
pattern from the repo root. Codified in `GOTCHAS.md`.

### 5. Phase 0 was the canary for the multi-team-coordination harness

Phase 0 took longest to close because it touched the most cross-team
concerns: Run (portability bug), Release (CI/release pipeline), Manual
Test (verification of GHA-only paths). It also surfaced the most
process-level learnings: macos-13 saturation strategy, lipo fuse,
GHA observation patterns, verification-doc discipline, GOTCHAS.md
discipline. The harness is now battle-tested for Phase 2-6.

## Process notes

- **Three teams worked in parallel without coordination friction.**
  File scopes fully disjoint (`.github/workflows/release-test.yml` +
  `scripts/install.sh` for Release; `src/novetest/cli/` +
  `src/novetest/orchestration/` + `tests/unit/cli/` +
  `tests/integration/orchestration/` for Orchestration;
  `src/novetest/run/` + `tests/fixtures/projects/jest-basic/` for Run).
  Main Branch merged in landing order (Orchestration → Run → Release)
  with no conflicts.
- **Release team's diagnostic-first PyApp check was exemplary.** They
  read PyApp + python-build-standalone docs/API BEFORE writing the
  YAML, confirmed universal2 was lipo-fuse-only, then implemented.
  Saved an iteration cycle.
- **Manual Test caught 0 functional bugs across 3 slices** — only doc/
  template drift (Issues #1, #2 in coverage-show-diff finding, both
  classifications-not-defects). 301 passed + 1 skipped across all
  three findings' test gates, byte-equivalent.
- **PM addressed all 4 PM-actionable Manual Test recommendations
  immediately this cycle** (no carry-forward except Node.js CI matrix
  which requires a Release task and is queued for next cycle).

## Follow-ups carried forward (PM queue for next cycle)

1. **Phase 2 DoD #3 — `inspect` Coverage section** (Orchestration). Reuses
   both `coverage_outcome` and `coverage_delta` frozen shapes. Slice size:
   moderate. Closes DoD #3.
2. **Phase 2 DoD #4 — 50k-location perf fixture** (Coverage + perf-engineer).
   Needs scoping proposal first; recruit `performance-engineer` agent.
3. **Phase 2.5 — jest Istanbul coverage parser** (Coverage). Companion
   to this cycle's jest adapter; turns `--coverage` on jest from no-op
   to real Coverage Facts.
4. **CI matrix — Node.js cell** (Release). Adds a Node.js install step
   to `ci.yml` so `tests/integration/run/test_jest_basic.py` runs in CI
   instead of skipping. Small slice. Recommended bundling with #3
   above into one Release+Coverage combined cycle.
5. **Memory contract — `entry_id == run_id` equivalence note**
   (Memory). One-line addition to `design/interace-contract/memory.md`
   noting the shortcut. Trivial; can be a tiny Memory task or bundled.
6. **Phase 0 standby.** Release team's charter explicitly notes
   "temporary activation"; with Phase 0 fully closed, Release reverts
   to standby until next MVP release cycle.

## References

Transient comms files (3 tasks + 3 handoffs + 3 verifications + 3
findings = 12 total) deleted in the same commit as this entry. Three
commit hashes are the authoritative source-diff anchors: `50c9170`
(Coverage show/diff), `e0acce6` (Run jest), `09eda94` (Release
universal2).

Permanent items touched or created this cycle:
- `delivery-phasing.md` Phase 0 DoD #2 footnote updated; DoD #3 ticked.
- `decisions/2026-05-16-coverage-delta-envelope-shape.md` (NEW).
- `GOTCHAS.md` (new `uv` staleness entry).
- `.claude/agents/novetest-main-branch-team.md` (verification-doc
  path discipline added to "After merge" section).
