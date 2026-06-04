---
from: novetest-main-branch-team
to: novetest-pm
type: question
created: 2026-06-04
slug: junit-hotfix-2-gate-failed
status: open
related:
  - agent-comms/handoffs/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
  - agent-comms/tasks/run-team-2026-06-04-phase2.5-junit-adapter-hotfix-2.md
  - agent-comms/findings/manual-test-team-2026-06-04-phase2.5-junit-adapter-hotfix.md
worktree: /home/yjshin/dev/aispace/novetest-junit-hotfix-2
branch: run-team/junit-adapter-hotfix-2
tip_commit: 41d58ab
---

# Question — JUnit hotfix #2 pre-merge gate failed on equipped host; merge ABORTED

## Decision needed

Hotfix #2 (`41d58ab`) does NOT pass the pre-merge gate on the equipped
host (JDK 17.0.19 + Maven 3.9.16 + Gradle 8.14.5). Three integration
tests fail. PM must decide: kick back to Run team for hotfix-3, or
accept partial scope (Maven path only) and defer Gradle Defect 2 +
CLI-smoke envelope-path fix.

**Merge has been aborted. No push performed. Worktree retained at
`/home/yjshin/dev/aispace/novetest-junit-hotfix-2` for Run team.**

## Pre-merge gate result

```
$ uv run mypy
Success: no issues found in 90 source files

$ uv run pytest -q tests/unit tests/integration
3 failed, 1033 passed, 3 skipped in 55.14s
```

Run team's handoff claimed `1025 passed + 14 skipped + 0 failed` on
their JDK-less host. On this equipped host: `1033 passed + 3 skipped
+ 3 FAILED`. The smokes execute (not skip) because mvn + gradle are
on PATH — that's how the bugs surfaced.

## Failure 1 — CLI smoke envelope path WRONG (both Maven + Gradle)

```
tests/integration/run/test_junit_maven.py::test_cli_smoke_run_emits_envelope  FAILED
tests/integration/run/test_junit_gradle.py::test_cli_smoke_run_emits_envelope FAILED
> KeyError: 'run_record'
> assert envelope["data"]["run_record"]["engine_name"] == "junit"
```

The new smoke tests dereference `data["run_record"]`, but the actual
envelope shape on the merged tip is `data["memory_entry"]["run_record"]`
(pinned by prior verification doc lines 105-122, by `models/run_record.py`,
and by `workflows/run.py:85-89`). Run team's gate did not catch this
because on their JDK-less host the smoke skip-gates on `which(mvn) is None`,
so the dereference never executed against a real envelope.

Same class of defect as hotfix #1 Defect 4 (the `(0, 1)` exit-code bug):
a CLI-smoke assertion shipped without being exercised end-to-end against
the canonical envelope. One-line fix per file:
`data["run_record"]` -> `data["memory_entry"]["run_record"]`.

## Failure 2 — Gradle `--continue` does NOT restore coverage_xml on 8.14.5

```
tests/integration/run/test_junit_gradle.py::test_coverage_run_emits_jacoco_xml FAILED
> AssertionError: assert 'coverage_xml' in result.artifact_paths
> artifact_paths={'stdout', 'stderr', 'reports_dir'}  # no coverage_xml
> returncode=1
```

Observed on Gradle 8.14.5 with the hotfix's `--continue` flag inserted
before `jacocoTestReport`. The Run team's argv unit test proves the
flag ordering; the runtime semantics on 8.14.5 differ from the assumed
model. Hypotheses (Run team to diagnose, not Main Branch): `:test`
abort prevents `jacoco.exec` finalization despite `--continue`, OR
`_stage_coverage_xml`'s glob doesn't find the report under 8.14.5's
output layout. Maven coverage path **does pass** on this host — the
`-Dmaven.test.failure.ignore=true` Maven fix works as designed.

## Diff scope match against commit-message claims

- D2 Maven (`-Dmaven.test.failure.ignore=true`): closed and verified.
- D2 Gradle (`--continue`): **NOT closed** on Gradle 8.14.5 (failure 2).
- D4 smoke `(0,3)`: argv assertion correct, but downstream envelope
  dereference is wrong (failure 1) — smoke cannot reach the rc check
  on the happy-path branch.
- Gradle 9 launcher dep: fixture edit looks correct; not exercised
  on 8.14.5 host.

## What was NOT done

- No merge commit created.
- No verification doc written.
- No push to origin.
- Worktree NOT removed; branch NOT deleted.

## Recommendation

Kick back to Run team for **hotfix #3** with two surgical fixes:
1. Envelope path correction in both `test_cli_smoke_run_emits_envelope`
   tests.
2. Gradle coverage_xml: reproduce on equipped host (toolchains in
   `~/.local/share/novetest-toolchains.sh`), diagnose, and fix argv
   or staging glob.

Run team can add a 3rd commit on the same worktree; no rebase needed
(main still at `6099841`).

## Process lesson candidate

Run team's pre-handoff gate runs on a JDK-less host where JUnit
integration tests skip. Even with hotfix #2 adding argv unit tests,
the integration-level wiring (envelope path, real Gradle graph) is
unexercised on that host. The equip-and-exercise mandate should
arguably apply to the originating team's own pre-handoff gate when
a hotfix modifies integration-level tests.
