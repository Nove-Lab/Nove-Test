# Agent Communication Protocol

Inter-team coordination via file-based message passing. PM is the hub; other teams are spokes.

This folder complements but does NOT replace:
- `WORKLOG.md` — committed-history retrospective (immutable per-commit log).
- `design/` — durable interface contracts and architectural decisions.

This folder is **in-flight work coordination only**. Most files here are short-lived.

---

## Folders

| Folder | Lifecycle | Writes | Reads | Purpose |
|---|---|---|---|---|
| `tasks/` | Transient | PM | Receiving team | Work assignments |
| `handoffs/` | Transient | Originating team | Main Branch | "My worktree is ready to merge" |
| `verifications/` | Transient | Main Branch | Manual Test | "I merged X; here's what to verify" |
| `findings/` | Transient | Manual Test | PM | E2E test results, regressions |
| `questions/` | Transient | Any team | PM, CEO | Open blocker; cannot proceed |
| `decisions/` | **Permanent** | PM (CEO-approved) | All teams | Binding directives |
| `history/` | **Permanent** | PM | All teams | PM-curated record of completed cycles |

Transient = deleted by PM at the end of a cycle (after distilling anything load-bearing into `history/`).
Permanent = never deleted; long-term institutional memory.

---

## Lifecycle (a typical cycle)

```
PM writes → tasks/<team>-<date>-<slug>.md
  → Team picks up; works in an isolated worktree
  → Team writes → handoffs/<team>-<date>-<slug>.md (worktree ready)
  → Main Branch reads handoff; merges
  → Main Branch writes → verifications/<date>-<slug>.md
  → Manual Test reads verification; runs E2E
  → Manual Test writes → findings/manual-test-team-<date>-<slug>.md
  → PM reads all 4 files
  → PM writes → history/<date>-<topic>.md  IF anything is worth long-term remembering
  → PM deletes the 4 transient files
  → PM regenerates INDEX.md
```

`decisions/` and `history/` never get deleted.

`questions/` gets resolved by becoming a `decisions/` file, then the question file is deleted.

---

## Filename convention

`<team-slug>-YYYY-MM-DD-<short-slug>.md`

`<team-slug>` strips the `novetest-` prefix from the agent identity. Example: agent `novetest-coverage-team` writes files named `coverage-team-YYYY-MM-DD-...`.

Cross-team docs (verifications, history, top-level decisions) may omit the team prefix.

Examples:
- `tasks/coverage-team-2026-05-14-slice-a-data-model.md`
- `handoffs/coverage-team-2026-05-14-slice-a-data-model.md` (same slug as the task → easy to pair)
- `verifications/2026-05-14-phase2-coverage-foundation.md`
- `findings/manual-test-team-2026-05-14-phase2-foundation.md`
- `questions/coverage-team-2026-05-14-show-contexts-flag.md`
- `decisions/2026-05-14-engine-adapters-belong-to-run.md`
- `history/2026-05-14-phase2-entry.md`

Slugs are ASCII kebab-case. No spaces, no Korean, no underscores. Keep them short and grep-friendly.

---

## Standard frontmatter (every file)

```yaml
---
from: novetest-<team>-team        # full agent identity
to: novetest-<team>-team | all
type: task | handoff | verification-request | findings | question | decision | history
status: pending | in-progress | done | blocked | resolved
created: YYYY-MM-DD
slug: short-slug-matching-filename
related: [<filename1>, <filename2>]    # optional
blocked-by: [<filename>]               # optional
---
```

`tools/regen_comms_index.py` parses this frontmatter to build `INDEX.md`. Keep it minimal but accurate.

---

## Standard body sections (per type)

### `tasks/<team>-<date>-<slug>.md`
- **Scope / Mission** — one paragraph.
- **Pre-flight reading** — files the team MUST read first.
- **Files to write / modify** — explicit paths.
- **Files NOT to touch** — explicit paths or globs.
- **Data contracts** — pinned verbatim if cross-team (e.g., dataclass field names).
- **Verification commands** — must-pass before reporting done.
- **Reporting** — exact handoff filename to write.

### `handoffs/<team>-<date>-<slug>.md`
- **Worktree** — path, branch, base commit.
- **Files written / modified**.
- **Verification result** — pytest counts, mypy result.
- **Worklog entry text** — paste the entry appended to `WORKLOG.md`.
- **DoD bullets believed closed** — list of unchecked `- [ ]` bullets in `design/implementation-plan/delivery-phasing.md` this slice fully satisfies. Do NOT tick them yourself; PM verifies and ticks during cycle cleanup. Empty list (or "none") is a valid answer.
- **Open items / surprises** — non-blocking notes for the next team.

### `verifications/<date>-<slug>.md`
- **Merged commit** — hash + summary.
- **Source handoffs** — refs to the handoffs that fed this merge.
- **Verification steps** — concrete commands and scenarios for Manual Test.
- **CLI-level smoke gate (Native Engine adapter cycles only)** — when the slice introduces or materially modifies a Native Engine adapter, list at least one `subprocess.run(["uv", "run", "novetest", "run"], …)` invocation against the canonical happy-path fixture and pin the expected `returncode in {0, 1}` assertion. Manual Test MUST equip the verification host with the relevant toolchain per `scripts/dev-host-setup.md` AND run this scenario; skip-gating it precludes a `passed` verdict. Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`.
- **Pre-flight Gate A — tool floor + plugin floor (build-tool-driven adapter cycles only)** — for Maven/Gradle/MSBuild/Cargo+nextest-style ecosystems, the pre-flight floor check is the COMBINATION of the CLI tool version AND the relevant plugin/extension version declared in the fixture's project config (e.g. `mvn -v >= 3.8` AND `pom.xml` Surefire `>= 3.0`). Per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §4.
- **Critical edge cases** — non-obvious things that need probing.
- **Reporting** — exact findings filename to write.

### `findings/<date>-<slug>.md`
- **Verdict** — `passed` | `failed` | `partial`.
- **What was tested** — narrative + commands run.
- **Issues found** — with minimal reproducers.
- **Recommendations for PM** — next-step suggestions.

### `questions/<team>-<date>-<slug>.md`
- **Question** — 1–2 sentences.
- **Context** — why the team is blocked.
- **Options** — A/B/C with trade-offs.
- **Team's recommendation** — what the team would do absent direction.
- **Blocking?** — yes/no (no = team can proceed with assumption noted).

### `decisions/<date>-<slug>.md`
- **Decision** — one line.
- **Rationale**.
- **Affected teams / files**.
- **Effective date**.
- **Supersedes** — link to prior decision if any.

### `history/<date>-<topic>.md`
- **What happened** — narrative.
- **Surprises worth remembering**.
- **Decisions that came out of this cycle** — refs to `decisions/`.
- **Open follow-ups**.

---

## INDEX.md

Auto-generated by `tools/regen_comms_index.py`. Snapshot of all open items grouped by status, plus recent decisions and history. Every agent reads this first.

Regenerate after writing / renaming / deleting any comm file:

```bash
python3 tools/regen_comms_index.py
```

Never hand-edit `INDEX.md`. If the regen script breaks, fix the script — do not patch the index.

---

## Write-permission rules

`from:` field in frontmatter MUST match the writing agent's identity. Each team's charter enforces this in its "Forbidden files" section.

- `tasks/` — only `novetest-pm-team` writes.
- `handoffs/` — only the originating team writes (matching its identity).
- `verifications/` — only `novetest-main-branch-team` writes.
- `findings/` — only `novetest-manual-test-team` writes.
- `decisions/` — only `novetest-pm-team` writes (after CEO approval).
- `history/` — only `novetest-pm-team` writes.
- `questions/` — any team may write.
- `INDEX.md` — only `tools/regen_comms_index.py` writes (do not hand-edit).

All teams may READ everywhere.

---

## Cross-team direct comm

**Forbidden** except: `novetest-main-branch-team` → `novetest-manual-test-team` (the `verifications/` channel). That direct link exists because merge-then-verify is a tight handoff with no PM value-add.

All other cross-team needs (e.g., "Coverage Team needs Memory Team to add field X to MemoryEntry") go through `questions/` → PM evaluates → PM creates new `tasks/` for the affected team.

---

## Cleanup discipline

After a cycle completes (task + handoff + verification + findings all written, code merged, no findings issues), the PM:

1. Reads all 4 transient files for the cycle.
2. Writes `history/<date>-<topic>.md` IF anything is worth long-term remembering — gotchas, design surprises, cycle-specific lessons. Routine work does NOT need a history entry.
3. Deletes the 4 transient files.
4. Runs `tools/regen_comms_index.py` to refresh `INDEX.md`.
5. Commits the deletions + history entry in one tidy commit.

This keeps the folder small, signal-to-noise high, and grep over comms cheap.

`decisions/` and `history/` accumulate over the lifetime of the project. Do not delete them.
