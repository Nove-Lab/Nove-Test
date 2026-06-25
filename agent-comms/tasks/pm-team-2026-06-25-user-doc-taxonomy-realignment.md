---
from: novetest-pm-team
to: novetest-pm-team
type: task
status: pending
created: 2026-06-25
slug: user-doc-taxonomy-realignment
related:
  - src/novetest/orchestration/recommendation/categories.py
  - design/user-doc/human
  - design/user-doc/agent
  - design/website-plan/handoff/docs
---

# Task: PM — Realign user-doc + Docs handoff with the real recommendation taxonomy

- **Owner**: novetest-pm-team (self)
- **Status**: pending
- **Created**: 2026-06-25
- **Discovered**: 2026-06-25 during the marketing-website terminal-example design conversation. The category names used in user-doc and Docs handoff were narrative-descriptive (`tests_failed`, `new_test_failure`, `coverage_regressed`, `flaky_suspect`, `recovered_from_failure`) and **do not match the actual closed taxonomy v1** shipped in `src/novetest/orchestration/recommendation/categories.py` (`regression_with_localization`, `investigate_location`, `investigate_regression`, `coverage_gap`, `flaky_suspected`, `unavailable_analysis`, `all_green`).

## Goal

Make every category name, glyph mapping, citation-kind table, and routing example in the user-facing docs **exactly match** the code in `src/novetest/orchestration/recommendation/categories.py` and the renderer in `src/novetest/cli/renderers/test.py`. Single source of truth for the taxonomy: the code.

## Why

- **Agents pin to `recommendations[].category` strings.** A doc-set that promises `tests_failed` while the CLI emits `investigate_regression` produces routing that silently never fires. The agent-set docs are the worst-affected: deterministic routing is the entire pitch.
- **Marketing-website demo (designed 2026-06-25) uses the REAL taxonomy** to stay honest with the code. Without this fix, the marketing site (correct) and the docs site (stale) will contradict each other within one product brand.
- **The bug was introduced because the original user-doc author (PM) wrote category names from product intent rather than from code.** Future PMs may repeat this mistake if there is no pinned single-source-of-truth. This task also produces that pin.

## Scope

### In scope

1. **Read `src/novetest/orchestration/recommendation/categories.py`** end to end. Confirm the 7 category constants and the priority table; transcribe verbatim into a new section of the design doc (see step 5).
2. **Read `src/novetest/cli/renderers/test.py` `_category_glyph` + `_citation_line`.** Confirm: (a) which categories use which glyphs (only `all_green` → `✓`, `unavailable_analysis` → `—`, all others → `!`); (b) the citation kinds emitted by `_citation_line` (`run_reference`, `localization_finding`, `coverage_fact`, `regression_fact`, `test_result`, `replay_result`). Transcribe.
3. **Update `design/user-doc/agent/after-test.md`**:
   - Replace the entire "Closed taxonomy of categories (v1)" table with the real 7 entries.
   - For each category: update the semantic description from the matcher's docstring + brief intent (NOT from imagination).
   - Replace the "Citation kinds" table with the real 6 kinds (`run_reference`, `localization_finding`, `coverage_fact`, `regression_fact`, `test_result`, `replay_result`) and their selector shapes from `_citation_line`.
4. **Update `design/user-doc/human/after-test.md`**:
   - Same table replacement.
   - Replace the worked-failure example (`! [tests_failed]`) with one using `! [regression_with_localization]` (most representative single-failure case).
5. **Update `design/user-doc/{human,agent}/quick-start.md`** and `troubleshooting.md` — every occurrence of `[tests_failed]`, `[new_test_failure]`, `[coverage_regressed]`, `[flaky_suspect]`, `[recovered_from_failure]` → real category. Grep + manual review per occurrence (not a blind sed: some occurrences are in narrative prose where the meaning must adjust, not just the token).
6. **Update `design/website-plan/handoff/docs/understanding-results.md`** and `quick-start.md` — same fixes. Marketing demo (Hero / inspect / JSON) already targets real taxonomy; the Docs page set must follow suit.
7. **Pin the single source of truth** — add a new section to `design/implementation-plan/recommendation-synthesis.md` (or the closest existing design doc; verify it exists) titled "Closed taxonomy v1 — authoritative list" that points at `src/novetest/orchestration/recommendation/categories.py` and forbids paraphrasing the category names anywhere downstream. Any future doc that lists categories must transclude or cross-reference this section.
8. **Add a flaky_suspected forward-reference**: in every user-doc that lists categories, mark `flaky_suspected` with a clear annotation:
   > *"Requires Replay engine results (today: opt-in via `novetest test --reruns N`, pending integration cycle — see [decision 2026-06-25-test-reruns-flag-and-replay-integration](../../agent-comms/decisions/2026-06-25-test-reruns-flag-and-replay-integration.md)). In v0.1.2 this category does not fire from `novetest test` alone."*
9. **Add an integration test (no code, just a checklist in the design doc)** that every future taxonomy addition must:
   - Land the category constant in `categories.py` first.
   - Update the doc tables in the same commit (or the immediately following commit).
   - Regen INDEX.

### Out of scope

- Changing the actual code categories. This task is doc-side only.
- Updating the `--reruns` flag itself (separate Orchestration cycle; this task only updates docs to reference that decision).
- Updating the marketing website handoff README (the Docs page set inside handoff/docs is in scope; the parent handoff/README.md is unchanged).

## Pinned file list

- **Edit**: `design/user-doc/{human,agent}/quick-start.md`, `design/user-doc/{human,agent}/after-test.md`, `design/user-doc/{human,agent}/troubleshooting.md` (6 files), `design/website-plan/handoff/docs/understanding-results.md`, `design/website-plan/handoff/docs/quick-start.md` (2 files), and one design doc for the SSoT pin (e.g. `design/implementation-plan/recommendation-synthesis.md`).
- **Create**: nothing.
- **Touch source code**: NO. PM never edits `src/**` or `tests/**`.

Total file count: 9 files.

## Acceptance criteria

- `grep -rln "tests_failed\|new_test_failure\|coverage_regressed\|flaky_suspect\|recovered_from_failure" design/user-doc design/website-plan/handoff/docs` returns 0 hits (other than the forward-reference annotation explaining the discrepancy with the OLD names, if any historical note is needed).
- Every category mentioned in user-doc + Docs handoff appears in the real `CATEGORIES` frozenset in `categories.py`.
- Marketing demo (Hero / inspect / JSON) is taxonomy-consistent with the Docs page set.
- Single source of truth section in the design doc exists and is linked from each doc page that lists categories.
- No `WORKLOG.md` entry required (PM doc-only commit; WORKLOG hook only fires for `src/` + `tests/`).

## Scheduling

- **Urgency: BEFORE the marketing website launches.** Marketing site uses real taxonomy; user-doc lagging behind will surface to users via cross-link confusion.
- **Concrete trigger**: pick up immediately after the current marketing-demo deliverable is in the marketing team's hands, OR opportunistically during any quiet PM window.
- Sizing: ~4 hours of focused PM time. Single commit. No team dispatch.

## Coordination

- After the `--reruns` cycle merges, this task expands slightly: documenting the new `--reruns` flag's effect on `flaky_suspected` becomes part of the same doc surface. Plan for that follow-up edit pass.
- If marketing team raises questions about category names while this task is pending, point them at the marketing demo (real names) and at this task; do not introduce a third naming.
