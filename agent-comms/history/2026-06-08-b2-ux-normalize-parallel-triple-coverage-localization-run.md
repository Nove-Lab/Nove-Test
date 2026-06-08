---
from: novetest-pm-team
to: all
type: history
created: 2026-06-08
slug: b2-ux-normalize-parallel-triple-coverage-localization-run
related:
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-08-b1-polish-parallel-pair-defect7-and-fixed-tests-spec.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
---

# B2 UX-normalization parallel triple — Coverage path, Localization metadata + paths, Run artifact_dir.resolve (all PASSED)

## Cycle outcome

**First 3-team parallel cycle** in project history. All three slices
verified PASSED end-to-end on the equipped host (1233/0/0); zero file-
ownership conflict; zero §2.5 gate trigger.

| Slice | Team | Verdict | Functional commit | Headline |
|---|---|---|---|---|
| Outside-workspace path policy harmonization | Coverage | PASSED | `134918a` | 5-parser universal contract `not Path(file_path).is_absolute()` now holds across coverage.py / istanbul / lcov / jacoco / cobertura; lcov normalized to `../`-prefixed POSIX relpath via `os.path.relpath`. Decision amended in place with "Amendment 2026-06-08" block; no schema_version bump. |
| UX normalization (metadata + paths) | Localization | PASSED | `51ea1b6` | Mode-invariant `metadata: {'changed_files_count', 'regression_reweighted'}` across all three modes; `None` (not 0/False) is the load-bearing discriminator for "mode does not consult RegressionFactSet." `failure_proximity` paths normalized to workspace-relative via `_normalize_to_workspace_relative`; outside-workspace absolute kept absolute as "not your code" cue. |
| `artifact_dir.resolve()` preemptive hardening | Run | PASSED | `6ebad33` | 6/6 native adapters now share one rule. 12 unit tests (pair per adapter). 5-month long-standing TODO (`history/2026-05-16-phase0-release-and-phase2-entry.md §60`) closed. |

Cycle commits in chronological order: `7a17f85` (PM brief) → `134918a`
(Coverage) → `51ea1b6` (Localization) → `304e8f1` (Localization handoff)
→ `6ebad33` (Run) → `6a55677` (Coverage verification) → `c473419`
(Localization verification) → `8ac87e7` (Run verification) → this
cycle-close commit. (Note: Coverage and Run handoffs were folded into
their respective Main Branch FF-merge commits.)

## Track-status update — MVP path remaining

| Track | Status | Notes |
|---|---|---|
| C envelope-warnings-projection | ✅ closed 2026-06-07 | |
| D dotnet-cobertura-derive | ✅ closed 2026-06-07 | |
| A — B1 critical polish | ✅ closed 2026-06-08 | Defect 7 + Regression contract |
| **B — B2 UX normalization** | ✅ **CLOSED THIS CYCLE** | metadata + paths + adapter hardening |
| v1 metadata-channel sunset | parked at post-MVP cleanup (contract) | |

**MVP completion path next**: **Release readiness check** (Release
team activation). Per the `.claude/agents/novetest-release-team.md`
charter, Release team "reactivates at MVP release" — that trigger is
now satisfied. v1 metadata sunset folds into the same Release-readiness
window OR a discrete cleanup cycle immediately post-MVP.

## Load-bearing lessons (read these in future cycles)

### 1. First 3-team parallel cycle succeeded; pattern now routine for disjoint slices

06-07 (envelope-warnings + cobertura-derive) and 06-08 B1 (defect7 +
fixed-tests-spec) were 2-team parallels. This is the first 3-team
parallel. Zero file conflict; zero merge friction; alphabetical FF-
merge order (coverage → localization → run) respected. Manual Test
verified all three on the same equipped host snapshot
(`mypy --strict src/novetest` clean 92 files; `pytest -q` 1233/0/0
in 76.63 s). The parallel-pair pattern from 06-07's distill
(`"routine operating mode"`) extends cleanly to triples when file
ownership is provably disjoint AND no slice triggers §2.5.

### 2. 5-parser path policy universal harmonization

Pre-slice: 4/5 parsers emitted workspace-relative `file_path`;
lcov_parser kept absolute paths + surfaced them via
`metadata['lcov_warnings']` forensic channel. Post-slice: all 5
parsers honor `not Path(f.file_path).is_absolute()` invariant; lcov
uses `os.path.relpath(abs, workspace_root)` (yielding `../`-prefixed
POSIX relpath for outside-workspace files). `lcov_warnings` channel
survives but now carries BOTH the original absolute path AND the
normalized relpath — forensic continuity preserved without the
on-disk shape change.

Universal contract is now a one-line grep-target for future parsers:
adding a new coverage format (`go test -coverprofile` rich format,
hypothetical future test runner) MUST pass through workspace-relative
normalization, no exception.

### 3. mode-invariant metadata + meaningful `None` discriminator

`sbfl_per_test` mode previously emitted `metadata: {}` (no keys at
all). Post-slice: emits `{'changed_files_count': None,
'regression_reweighted': None}` — same key set as the other two
modes, but with `None` values. The choice of `None` (rather than `0`
/ `False`) is load-bearing — it encodes the semantic distinction:

- `None`: "this mode does not consult RegressionFactSet at all"
- `0` / `False`: "this mode consults RegressionFactSet; no
  change-aware boost was applied (empty changeset, or no override)"

An AI consumer reading `metadata` no longer needs to branch on
`finding.mode` to know which keys to expect — the keys are constant,
the values discriminate. Schema doc was updated to pin this rule.

**Cross-cutting caution**: a naive consumer writing
`if not md.get('regression_reweighted')` would collapse `None` and
`False` into the same branch, silently treating "per-test" the same
as "aggregate with no boost." Manual Test flagged this as a
post-MVP consumer-side audit candidate. Future docs should call out
the truthiness anti-pattern explicitly.

### 4. Outside-workspace policy: deliberately ASYMMETRIC across Coverage vs Localization

Coverage harmonizes outside-workspace to `../`-prefixed relpath
(B2-3). Localization (`failure_proximity` mode) deliberately keeps
outside-workspace paths absolute (B2-2). This is **not** an oversight
— it's an intentional semantic difference:

- **Coverage**: every file in the report is "code under test." An
  outside-workspace file is still part of the coverage corpus
  (vendored crates, build-script generated code). Surface it as
  navigation-friendly relpath; let the consumer trace the `..` chain
  if they care.
- **Localization (failure_proximity)**: outside-workspace paths are
  stdlib frames, `/rustc/<hash>/...`, third-party traceback frames
  — explicitly "not your code." Keeping them absolute is a visual
  cue to the reader: "the bug isn't here."

The cross-domain asymmetry is now pinned in both spec docs
(`decisions/2026-05-15-coverage-facts-json-layout.md` constraint #6
+ `design/interace-contract/localization.md` "Result shape" §). PM
ratifies the asymmetry as intentional — future briefs that touch
either side should respect the boundary, not "harmonize" across.

### 5. Forensic channel preservation pattern (relevant to v1 metadata sunset)

The `lcov_warnings` channel survives the harmonization, but now
carries BOTH the original absolute path AND the normalized relpath.
Empty-list suppression invariant intact (no `lcov_warnings == []`
noise). This is the canonical pattern for cleaning up a value-shape
while preserving forensic continuity — useful precedent for the
**post-MVP v1 metadata-channel sunset** (decision
`2026-06-06-adapter-warning-surface-v1-metadata-channel`), where
`coverage_unavailable_*` keys will be retired but possibly retained
in a similar forensic-only form during the transition.

### 6. Verification-doc precision regression — `.data.memory_entry.run_record.*` drop is now 4th occurrence

Localization finding Issue 2: verification doc used
`.data.run_record.run_reference.run_id` (wrong) instead of
`.data.memory_entry.run_record.run_reference.run_id` (canonical). This
is the **4th time in 5 cycles** the same `memory_entry` wrapper has
been dropped in a verification doc (prior: .NET hotfix D2 finding,
B1 cycle Regression Scenario B). B1 history §"Load-bearing lessons"
#6 promised "future briefs should pre-pin canonical envelope path"
— that promise applies starting from the **next cycle**; this cycle's
briefs were dispatched before the promise could take effect.

**Forward action**: PM brief template for any cycle whose
verification touches a `memory_entry`-wrapped envelope MUST include
a "Canonical envelope assertion paths" subsection naming the exact
jq selectors Main Branch will use. Stop the bleeding at the brief-
authoring step, not at the verification-writing step.

### 7. Fixture inventory drift — 5-month gap shows up

Run finding Issue 1: verification doc referenced
`basic_workspace` fixture which doesn't exist (the real fixture is
`pytest-basic`). The drift is the cumulative result of fixture
additions over 5 months without a single audit pass. Manual Test
spot-corrected at verification time, but the doc still carries the
stale name.

**Pre-Release-readiness action candidate**: a 30-minute fixture
inventory matrix (Manual Test territory or shared with Release team
during the readiness cycle) that lists every `tests/fixtures/projects/`
name + its current shape + what cycle/cycle-history-entry references
it. Catches drift before it reaches users via README/docs.

### 8. 5-month long-standing TODO closure — release-readiness preparation value

B2-4 closed the 2026-05-16 `artifact_dir.resolve()` TODO that had
sat open while the codebase grew from 1 adapter (pytest) to 6
(pytest + jest + junit + gotest + cargo + dotnet). The 1-line-per-
adapter fix was trivial; the **decision** to close it now (rather
than at post-MVP) is the load-bearing call: long-standing TODOs are
best swept up just before release-readiness, when the codebase
shape stabilizes and a 1-line preemptive hardening is easier to
review than a release-blocking surprise later. Other long-standing
items (Memory `delete` polish — long-standing carry-forward;
specific Localization branch open Q's) may benefit from the same
"sweep before release" pattern in the next cycle.

### 9. In-place decision amendment pattern — canonical for forward-compat strengthening

Coverage's amendment to
`decisions/2026-05-15-coverage-facts-json-layout.md` took the
**in-place** form: constraint #6 was strengthened (the relpath rule
made binding) AND a dated "Amendment 2026-06-08" block was added
before the "Effective date" section. No schema_version bump
(on-disk shape unchanged; only the previously-undefined outside-
workspace value shifts). This pattern preserves:

- Linkability (existing cross-references to `decisions/2026-05-15-*`
  still work and point to the strengthened constraint)
- Avoid decision-fragmentation (no need to issue
  `decisions/2026-06-08-coverage-path-amendment.md` that would
  shadow-supersede the original)
- Audit trail (the dated Amendment block makes the timeline of the
  constraint's evolution explicit)

PM ratifies this as the **canonical amendment pattern** for any
future amendment that strengthens (not reverses) an existing
constraint. Use a new dated decision file only when the change
would require a `schema_version` bump or fundamentally redefines
the contract.

### 10. 6 consecutive cycles of equip-and-exercise validation — pattern matured

The `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`
posture has now been the verification default for **6 consecutive
cycles**: junit hotfix #1 → cargo CLI orchestration defect →
dotnet adapter hotfix #1 → envelope-warnings + cobertura-derive
parallel pair → B1 polish parallel pair → this B2 parallel triple.
Zero exceptions; zero cases where the equipped-host gate added
ceremony without value. Manual Test recommendation: consolidate
into a meta-decision codifying "equip the host once, exercise the
full CLI matrix" as the verification default for all `src/` +
`tests/` slices, not just the original adapter scope.

**PM position**: defer meta-decision to the **Release-readiness
cycle** — it's the natural time to formalize the posture
permanently (the readiness check itself will be the 7th
consecutive validation, completing the maturation arc).

## PM dispositions this cycle (cycle-close ratifications)

These dispositions are recorded here, not in separate decision
files (they are surface ratifications, not cross-team structural
rulings):

### 1. In-place decision amendment as the canonical pattern

See §"Load-bearing lessons" #9. PM ratifies in-place amendment with
a dated "Amendment YYYY-MM-DD" block as the canonical pattern for
constraint-strengthening (vs new dated decision files). Coverage's
2026-05-15 amendment is the worked example.

### 2. Coverage vs Localization outside-workspace asymmetry is intentional

See §"Load-bearing lessons" #4. PM ratifies the cross-domain
asymmetry as intentional ("code under test" vs "not your code"
semantic distinction). Future briefs MUST respect the boundary;
no harmonization across.

### 3. Truthiness anti-pattern is a docs-side gap, not a slice scope

Manual Test flagged that `if not md.get('regression_reweighted')`
would silently collapse `None` and `False`. PM ratifies this as a
**docs-side gap** to address in the next round of consumer-facing
documentation (release-readiness cycle or post-MVP user docs sweep),
NOT a slice scope. No consumer ships today; the contract pin in
`design/interace-contract/localization.md` is sufficient for
forward-correctness.

### 4. 5-month TODO closure pattern (closing B2-4)

The `2026-05-16` `artifact_dir.resolve()` TODO is now closed by
`6ebad33`. PM annotates the original history entry as "closed
2026-06-08 by `6ebad33`" (one-line note added at the relevant point
in the original history file is OUT of scope for THIS cycle-close
commit; PM may sweep all long-standing-TODO closures into a single
audit-trail commit during release-readiness preparation).

### 5. 6-cycle equip-and-exercise → meta-decision deferred to release-readiness

See §"Load-bearing lessons" #10. PM defers the meta-decision to
the Release-readiness cycle (next cycle). The readiness check
itself will be the 7th consecutive validation.

## Cycle-close bookkeeping summary

Transient files retired in this cycle's close commit:

- `tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`
- `tasks/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`
- `tasks/run-team-2026-06-08-artifact-dir-resolve-hardening.md`
- `handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md`
- `handoffs/localization-team-2026-06-08-ux-normalize-metadata-and-paths.md`
- `handoffs/run-team-2026-06-08-artifact-dir-resolve-hardening.md`
- `verifications/2026-06-08-outside-workspace-path-harmonization.md`
- `verifications/2026-06-08-ux-normalize-metadata-and-paths.md`
- `verifications/2026-06-08-artifact-dir-resolve-hardening.md`
- `findings/manual-test-team-2026-06-08-outside-workspace-path-harmonization.md`
- `findings/manual-test-team-2026-06-08-ux-normalize-metadata-and-paths.md`
- `findings/manual-test-team-2026-06-08-artifact-dir-resolve-hardening.md`

Retained:

- `findings/manual-test-team-2026-06-04-host-equip.md` (institutional;
  equipped host #1)
- `findings/manual-test-team-2026-06-06-host-equip.md` (institutional;
  equipped host #2)
- This history file

No `design/implementation-plan/delivery-phasing.md` DoD bullet ticks.
B2 was a polish cycle that closed UX-normalization carry-forwards.
Phase 1/2/3/4/5/6 DoD already 100% checked before this cycle; only
remaining unchecked DoD bullets are Phase 7 (post-MVP MCP transport),
unaffected.

## Future-cycle backlog (recorded; NOT auto-queued)

1. **Release-readiness check (next cycle)** — Release team
   activation. Per `.claude/agents/novetest-release-team.md`
   charter, "reactivates at MVP release." Scope candidates:
   PyApp binary build matrix, CI lanes (Linux/macOS/Windows),
   `ailovestesting.com/novetest/install.sh` curl-pipe-sh
   verification, SHA-256 verification flow, `THIRD_PARTY_NOTICES.txt`
   audit (vendored JUnit Console Launcher JAR coverage). PM
   recommends folding the **6-cycle equip-and-exercise meta-
   decision** + **long-standing-TODO sweep** + **fixture inventory
   matrix** into the same cycle for narrative cohesion.

2. **v1 metadata-channel sunset (post-MVP cleanup)** — still
   parked. Re-queue immediately after MVP release. The 5-parser
   harmonization in B2-3 sets a forensic-channel preservation
   pattern (see §"Load-bearing lessons" #5) that may inform the
   sunset approach.

3. **Outside-workspace cargo fixture (Manual Test
   recommendation)** — current E2E only covers inside-workspace
   case for cargo; outside-workspace path is unit-test-level only.
   Nice-to-have for future cycles touching lcov_parser; not
   release-blocking.

4. **Consumer-side documentation (`None` vs `0`/`False` truthiness)**
   — see §"PM dispositions" #3. Fold into release-readiness consumer
   docs sweep OR post-MVP user-facing docs cycle.

5. **`novetest coverage show` as canonical smoke verb** — Manual
   Test recommendation for future coverage-engine verification
   slices. No source change; verification-doc-template polish.

6. **Verification-doc template polish (Main Branch process)** —
   `data.memory_entry.run_record.*` canonical path snippet
   (`python3 -c "import json,sys; r=json.load(sys.stdin); ..."`).
   Already a known item from B1 history §"Load-bearing lessons" #6;
   reinforced this cycle.

7. **Fixture inventory matrix audit** — see §"Load-bearing lessons"
   #7. 30-minute scope; release-readiness cycle candidate.
