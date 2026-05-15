---
from: novetest-pm-team
to: all
type: history
status: resolved
created: 2026-05-16
slug: phase0-release-and-phase2-entry
---

# History: Phase 0 release tooling + Phase 2 entry (Run / Coverage)

Three slices landed across 2026-05-15 covering the final Phase 0 distribution infrastructure and the Phase 2 entry (Coverage engine foundation + per-test coverage emission from the pytest adapter). Manual Test signed off both verification passes on 2026-05-16.

## Cycle summary

| Slice | Commit on main | Verdict |
|---|---|---|
| Release: Phase 0 CI + PyApp + install.sh | `74a6ce4` | passed locally; 3 of 4 Phase 0 DoD bullets await live GHA observation |
| Coverage: CoverageFactSet + 4 interfaces | `dee3252` | passed — engine library shippable; no DoD closes from this slice alone |
| Run: pytest adapter per-test coverage emission | `6ff91c5` | partial — slice production-ready; "partial" stems from verification-doc discrepancies and an optional `artifact_dir.resolve()` hardening seam, not from slice defects |

## What closed, what stayed open

- **Phase 0 DoD #4 ticked.** Install script SHA-256 verification + tampered-binary integration test. Manual Test independently exercised the loud-abort path: PREFIX empty after attempted install, both expected/actual digests surfaced on stderr.
- **Phase 0 DoD #1, #2, #3 still open.** Require live GHA observation of the 9-cell CI matrix, the PyApp wrap per target, and the `install-script-e2e` job round-tripping against a real release artifact. CEO push-and-watch pass owed before tick.
- **Phase 2 DoD all open.** As the three handoffs predicted in concert. The next Orchestration slice that wires `--coverage` through `run_target_in_store` should close Phase 2 DoD #1 in one step; DoD #2 and #3 follow on the `coverage show/diff` and `inspect` verbs; DoD #4 (NFR-COV-002, 50k covered locations) needs a perf fixture and a `performance-engineer` recruit.

## Load-bearing learnings (for future agents)

### 1. Coverage backends leak intermediate files into cwd by default

coverage.py's intermediate SQLite cache (`.coverage`) and the per-run `.coveragerc` default to the child process's cwd, which IS the SuT workspace under our adapter's invocation pattern. Caught by Run team during commit prep (NOT during implementation): without `[run] data_file = <artifact_dir>/.coverage` in the generated rc, `novetest run --coverage` would pollute the user's repo with `.coverage` SQLite files. Fix verified in the field by Manual Test (probe D in the pytest-coverage-emission findings — SuT clean, cache and rc both under `artifact_dir`).

**Principle for future polyglot adapter teams (Phase 2.5+: jest, go test, JUnit, dotnet, cargo):** every coverage backend has its own "intermediate file lands in cwd" footgun. Default to pinning all intermediate state under `artifact_dir`, never `cwd`. Add a unit-test assertion that the SuT workspace stays clean after the adapter runs.

### 2. `show_contexts` is the gate for per-test attribution (not `--cov-context=test`)

coverage.py's `--cov-context=test` controls which context name is *recorded during the run*, but the per-line `contexts` map only lands in the JSON report when `[json] show_contexts = True` in the rc file. Both are required for `mapping_granularity: per-test`. The pytest adapter sets both via its generated rc.

This is the runtime mechanism behind the binding constraint in `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`: `mapping_granularity` is engine-determined, and for pytest it depends on `meta.show_contexts` being true in the raw native payload.

### 3. Verification docs go stale on API signatures faster than expected

Manual Test caught two stale examples in this pass — `compare_coverage_facts` shown with two fact-sets instead of `(store, ref_1, ref_2)`, and `run_pytest` shown with `workspace=...` instead of a positional `TestTarget`. Both verification probes worked once Manual Test reverse-engineered the API; neither caused a slice regression.

**Discipline note for Main Branch (verification authoring) and PM (task authoring):** when describing a call site, pin the public signature verbatim from `src/`, not from memory or the task spec.

### 4. Per-line `contexts` list ordering is unstable across reruns

coverage.py emits the contexts list in test-execution order; pytest re-orders between runs. Sets are equal; byte comparison fails. The Coverage engine's parser treats `line_contexts` as mapping-of-set effectively, so downstream consumers are unaffected. Any future "deterministic `coverage.json`" expectation should be **set-equal**, not byte-equal.

## Process notes

### Run worktree finalization gap (resolved during merge)

The first merge pass found Run team's worktree at `phase2-pytest-coverage-emission` with no commits but a handoff file written — work substantively done, never staged. CEO instructed Run to finalize; Run committed (`4d81912`, rebased to `6ff91c5` on `main`); Main Branch rebased and merged in a second pass. **Convention restated for next cycle:** a handoff with `status: done` requires the worktree to carry the corresponding commit(s). Run team's handoff this pass also left `status: ready` post-finalization; restate the `done` convention to all teams next cycle.

## Follow-ups carried forward (PM queue)

1. **Run team (optional, low priority).** Add `artifact_dir = artifact_dir.resolve()` at the top of `run_pytest` to harden against future callers passing relative `artifact_dir`. Currently no production caller hits this (all build absolute paths under `.novetest/...`); the hardening is preemptive. One-line change.
2. **PM verification-doc discipline.** Main Branch verification template should pin public API signatures verbatim. Not a new charter rule — a discipline reminder. Surface next time we hand a verification template back to Main Branch.
3. **Coverage team (optional, informational).** Confirm intended behavior when `meta` is absent from the raw payload — parser currently falls back from `per-test` to `aggregate`. Sensible for coverage.py-shaped payloads; revisit only if a future adapter emits contexts without a meta object.
4. **CEO push-and-watch (blocking for Phase 0 DoD #1–#3 tick).** Push today's commits, observe `ci.yml` green across the 9-cell matrix, then trigger `release-test.yml` via `workflow_dispatch` (or push a `v0.0.1-rc0` tag) to confirm the PyApp wrap and the `install-script-e2e` job. Phase 0 closes only after that pass.

## References

Transient comms files (tasks, handoffs, verifications, findings, one resolved question) deleted in the same commit as this entry; the three merged commit hashes above are the authoritative source-diff anchors.

Permanent decisions touched or referenced this cycle:

- `agent-comms/decisions/2026-05-14-install-script-hosting-url.md`
- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`
- `agent-comms/decisions/2026-05-16-gotchas-md-policy.md`
