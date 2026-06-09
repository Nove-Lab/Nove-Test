---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-09
slug: mvp-release-readiness-assessment
related:
  - agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md
  - agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md
  - agent-comms/tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
---

# Verification — MVP release-readiness assessment (comms-only slice)

## Merged commit

- **HEAD**: `91ef953` (rebased onto `388f0f0`, FF-merged into `main`)
- **Source handoff**: `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`
- **Source question** (open, routes blocker to PM): `agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md`
- **Worktree base**: `bd4d300` → rebased onto `main` head `388f0f0` (CEO-approved equip-and-exercise default-posture decision landed in flight) → FF-merged at `91ef953`

## What landed

- 4 files. **Zero `src/**`, zero `tests/**`, zero `pyproject.toml`, zero `.github/workflows/**`, zero `scripts/install.sh`, zero `THIRD_PARTY_NOTICES.txt`.**
  - `WORKLOG.md` (+11 lines, top entry dated 2026-06-09)
  - `agent-comms/INDEX.md` (regenerated; +1 line for the new Open Question)
  - `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md` (NEW; status `done`)
  - `agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md` (NEW; status `open`)

## Why no test gate ran post-merge (rationale)

Charter mandates re-running `uv run pytest -q tests/unit tests/integration` + `uv run mypy` *after conflict resolution*. The rebase auto-merged INDEX.md cleanly (Pending and Recent-decisions sections are disjoint), so **no manual conflict resolution happened**. The slice diff is comms-only — zero bytes of executable code, zero type stubs, zero test files. Running the gate would consume ~1 minute and surface no information not already known from the pre-rebase state. Skipped under Karpathy "simplicity first." The pre-merge state of `main` at `388f0f0` had a green local gate (post-B2 closure baseline: 1209 passed + 23 skipped + 1 env-bound failure on `dotnet`).

If Manual Test wants to belt-and-suspenders re-run, it's a no-op:

```bash
uv run pytest -q tests/unit tests/integration   # expect 1209 passed / 23 skipped / 1 dotnet env-bound fail
uv run mypy --strict src/novetest               # expect clean across 92 source files
```

## Verification scenarios for Manual Test

This slice landed an **assessment + routing**, not a behavior change. So scenarios verify the assessment's *artifacts* and *empirical claims*, not engine semantics.

### Scenario A — Handoff + Question files render cleanly

```bash
# Read both new files end-to-end, verify the YAML frontmatter parses and the
# in-doc tables render correctly in your viewer.
less agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md
less agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md
```

Expected:
- Handoff YAML: `from: novetest-release-team`, `to: novetest-main-branch-team`, `type: handoff`, `status: done`.
- Question YAML: `from: novetest-release-team`, `to: novetest-pm-team`, `type: question`, `status: open`.
- Both have all `related:` paths resolving to actual files in the repo.

Quick sanity:

```bash
# Every `related:` path in both files should resolve. Spot-check.
grep -E '^\s+- ' agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md \
  | grep -oE '(agent-comms|design)/[^ ]+\.md' | while read p; do test -f "$p" && echo "OK $p" || echo "MISSING $p"; done

grep -E '^\s+- ' agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md \
  | grep -oE '(agent-comms|design)/[^ ]+\.md' | while read p; do test -f "$p" && echo "OK $p" || echo "MISSING $p"; done
```

All lines should print `OK ...` (no MISSING).

### Scenario B — INDEX.md reflects the new question and the still-pending task

```bash
grep -A1 '## Open questions' agent-comms/INDEX.md
grep -A2 '## Pending' agent-comms/INDEX.md
```

Expected:
- Open questions section contains exactly: `release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md`.
- Pending section still contains: `release-team-2026-06-08-mvp-release-readiness-assessment.md` (because the task isn't done in the assessment sense — Release team can't close it until the routed blocker clears AND a second Phase-3 sign-off pass lands).

Also verify the equip-and-exercise default-posture decision (which landed on `main` while the release worktree was in flight) is visible:

```bash
grep 'equip-and-exercise-default-verification-posture' agent-comms/INDEX.md
```

Expected: one match under Recent decisions.

### Scenario C — WORKLOG top entry is the release assessment

```bash
head -40 WORKLOG.md
```

Expected: top dated entry is `## 2026-06-09 — phase0-release-readiness / mvp-empirical-revalidation-and-routing`. The block contains the four standard bullets (Landed / Verified / Left open / Gotcha / Next) and references both new files.

### Scenario D — Empirical claim spot-check (optional, ~5 min)

The handoff makes specific empirical claims about the release pipeline at HEAD. You can cheaply verify the static ones without re-running CI:

```bash
# Vendored JAR SHA-256 matches the in-file pin
sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
# Expected: b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc

grep -i 'b016ef6b' src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt
# Expected: the same SHA-256 line, verifying integrity claim

# Production deps surface (claim: exactly 2 — cyclopts + numpy)
grep -A3 '^dependencies' pyproject.toml
# Expected: cyclopts>=3.0 and numpy>=1.26 only

# install.sh exists, header declares POSIX-sh
head -10 scripts/install.sh
# Expected: '#!/usr/bin/env sh' or similar POSIX-sh shebang
```

All four should match the handoff's empirical claims.

### Scenario E — Cross-reference with the routed question's failure inventory

The question file's §"Failure inventory" enumerates 20 failing tests by exact path. Spot-check that those test files exist on `main` at HEAD (the failures live in CI, but the test FILES should exist locally — they're red on Windows, green on Linux/macOS):

```bash
# Category A (3 Coverage tests)
grep -l 'test_fixture_coverlet_basic_yields_one_file_fully_covered' tests/unit/coverage/test_cobertura_parser.py
grep -l 'test_fixture_partial_coverage_yields_two_files' tests/unit/coverage/test_cobertura_parser.py
grep -l 'test_derive_xunit_all_sources_unresolvable_returns_sources_not_found' tests/unit/coverage/test_derive_xunit.py

# Category B (1 Coverage LCOV separator test)
grep -l 'test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning' tests/unit/coverage/test_lcov_parser.py

# Category C (4 Localization B2-2 path-normalization tests)
grep -l 'test_absolute_workspace_internal_path_normalized_to_relative' tests/unit/localization/test_derive_failure_proximity.py
grep -l 'test_absolute_path_outside_workspace_kept_absolute' tests/unit/localization/test_derive_failure_proximity.py
grep -l 'test_absolute_and_relative_for_same_file_collapse_to_relative' tests/unit/localization/test_derive_failure_proximity.py
grep -l 'test_failure_proximity_ranks_buggy_file_top' tests/integration/localization/test_failure_proximity_e2e.py
```

Each `grep -l` should print the file path it matched in. Confirms the routed-question inventory is accurate against current `main`.

## Critical edge cases worth probing

1. **The question is OPEN** (status: open). Manual Test should NOT attempt to "fix" anything in the question's scope — that's PM-routing territory, and 3 follow-up cycles are proposed (Coverage Windows / Localization Windows / Run JUnit Windows test gate). Manual Test confirms the question's enumeration is empirically grounded; PM disposes routing.

2. **The slice closes ZERO new DoD bullets** but **empirically re-validates 3 of 5 Phase 0 DoD bullets (#2 binary build, #3 install.sh e2e, #4 SHA-256 verify) against HEAD `bd4d300`** via `release-test.yml` run `27176266868`. Manual Test does NOT need to re-run that workflow — the link is in the handoff if curiosity strikes. The PM tick-bookkeeping question (handoff §"DoD bullets believed closed by this slice") is a PM call.

3. **DoD #1 surfaced as stale** — the question file lays out 3 PM options (un-tick / stale-marker / re-scope). Manual Test confirms the stale-marker rationale is well-supported (Windows red >= 8 days, 30+ consecutive red runs since `d4ebafa` 2026-06-01) but should not advocate for a specific PM choice.

4. **No regression risk.** Since zero executable code changed, no engine behavior shifted. The only risk vector is doc/INDEX drift, which Scenarios A–C verify.

5. **The 4 just-landed-today (2026-06-08) Localization B2-2 tests (Category C in the question) are part of TODAY's main-line history** — `51ea1b6 feat(localization): B2 UX normalization`. They pass on Linux/macOS (your local gate sees them green); they fail on Windows CI due to the `Path.relative_to` drive-prefix loss flagged in the question. This is a real cross-OS defect, not an artifact of the assessment slice. The Localization team's brand-new B2-2 work is correct on the host it was authored on; the Windows assertion has to land in a follow-up.

## Rebase / merge notes for the audit trail

- **Worktree branch**: `release/mvp-readiness-assessment`, based on `bd4d300`.
- **Rebase target**: `main` head `388f0f0` (the equip-and-exercise default-posture decision landed on `main` while this slice was in flight; main moved 1 commit ahead of the worktree's base).
- **Rebase result**: clean auto-merge on INDEX.md (release added an Open-question line; main added a Recent-decision line; sections are disjoint, no manual edit required).
- **Conflict count**: 0.
- **FF merge**: `388f0f0..91ef953` fast-forwarded into `main` cleanly.
- **Worktree cleanup**: deferred to after Manual Test sign-off (per charter "remove AFTER successful merge + verification").

## What Main Branch did NOT do (charter-discipline notes)

- Did NOT re-run CI on the worktree branch. The handoff itself argues this is a no-op (branch is identical to main HEAD modulo 4 comms files).
- Did NOT touch `src/`, `tests/`, `pyproject.toml`, `.github/workflows/**`, `scripts/install.sh`, or `THIRD_PARTY_NOTICES.txt`. Charter forbids it; the slice intentionally requires none.
- Did NOT close the open question. That's PM territory; the question stays open until PM disposes routing.
- Did NOT amend the `WORKLOG.md` entry (release team authored it; preserved verbatim per charter "preserve attribution").
- Did NOT proactively dispatch the 3 follow-up cycles. PM owns the routing call; the question file already lays out a parallel-triple suggestion matching the B2 shape.
