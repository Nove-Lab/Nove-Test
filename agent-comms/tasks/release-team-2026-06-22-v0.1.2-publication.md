---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-22
slug: v0.1.2-publication
blocked-by:
  - agent-comms/tasks/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
related:
  - agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md
  - agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md
  - agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
---

# v0.1.2 publication — bump `pyproject.toml::version` + tag + draft Release

## Mission

Cut the v0.1.2 user-visible release. This release bundles:

- v0.1.1 → v0.1.2 worth of main-branch improvements landed since
  2026-06-10:
  - **Windows install pipeline** (4th `release-test.yml` matrix cell +
    `scripts/install.ps1` + `install-ps1-e2e` job) — landed 2026-06-18
  - **Human text renderer** (`OutputMode.TEXT` now emits human-readable
    output instead of pretty-printed JSON) — landed 2026-06-18
  - **NOTICES verbatim license texts** (Apache 2.0 + BSD 3-Clause
    inlined; wheel attribution surface byte-identical to upstream
    canonical) — landed 2026-06-19
  - **First-run latency bench** (release-test.yml gates the 5-15s
    documented budget on every release) — landed 2026-06-19
  - **wheel-NOTICES inclusion probe** (CI fails if NOTICES.md ever
    stops shipping) — landed 2026-06-19
  - **`workspace_relpath` utility promotion** (Coverage-private path
    helpers lifted to `src/novetest/utils/path_utils.py`) — landed
    2026-06-19
  - **v1 metadata-channel sunset** (dotnet adapter's `coverage_unavailable_*`
    metadata bridge fully removed; `envelope.warnings[]` is single
    canonical user-visible surface) — landed 2026-06-19
  - **`novetest licenses` CLI verb** (NEW — landing in the twin
    Orchestration cycle dispatched in parallel with this brief; the
    Release tag waits for that merge before cutting)

**Closes the v0.1.2 carry surfaced at 2026-06-18 Windows install cycle's
cycle close** ("Manual Test recommended follow-up" §). CEO chose this
path explicitly at the 2026-06-18 session close (the carry was deferred
to "next session" = today).

The README's Windows install one-liner currently 404s against v0.1.1
(which has no Windows binary). v0.1.2 publication unblocks that surface.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — project-wide rules.
2. `.claude/agents/novetest-release-team.md` — your charter.
3. `agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md`
   — **Path A is operationally live**: `pyproject.toml::version` is
   the single source of truth; `src/novetest/__init__.py` already
   resolves dynamically via `importlib.metadata.version("novetest")`.
   **You do NOT touch `src/`. This is mechanical and load-bearing.**
4. `agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md`
   — the v0.1.1 cycle that established Path A. Mirror its mechanics
   for v0.1.2 (which is even simpler — just the version bump).
5. `agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md`
   §"3. The `gh` auth read-only situation is the new procedural reality"
   — gh push permissions are READ-only for the Release-team identity
   `yongjunshin`. The CEO pushes the version-bump commit, the v0.1.2
   tag, and any subsequent draft-release promotion. Your worktree
   prepares the commit; CEO executes the push.
6. `agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md`
   §"First-run latency bench: empirical result" — empirical evidence
   that release-test.yml dispatch produces the binding 4-cell build
   matrix. This cycle's release-test.yml run is the v0.1.2 binding
   gate.
7. `pyproject.toml` — verify current `version = "0.1.1"`. Your edit is
   `"0.1.1"` → `"0.1.2"`. Single line.
8. `.github/workflows/release-test.yml` — verify it still gates on
   tag-push for the draft Release creation, and on workflow_dispatch
   for the pre-tag empirical validation run.

## Scope (CEO-confirmed)

Sequential dependency on the parallel Orchestration cycle:

- **Step 1**: Orchestration merges `novetest licenses` CLI verb to
  `main`. (Their handoff signals readiness; Main Branch FF-merges per
  standard cycle.)
- **Step 2**: After their merge, you create a Release worktree off the
  updated `main` HEAD. Edit `pyproject.toml::version` `"0.1.1"` →
  `"0.1.2"`. Single 1-line diff.
- **Step 3**: File handoff. CEO pushes the worktree branch (gh
  auth read-only constraint). Main Branch FF-merges to `main`.
- **Step 4**: Pre-tag empirical validation — CEO dispatches
  `release-test.yml` on the merged main commit via
  `gh workflow run release-test.yml --ref main`. Verify 4-cell build
  matrix + install.sh + install.ps1 + first-run-latency-bench all
  GREEN. Cite the run URL.
- **Step 5**: CEO pushes annotated tag `v0.1.2` pointing at the
  pyproject-bump commit.
- **Step 6**: `release-test.yml` auto-fires on tag push, builds 4
  binaries (Linux x86_64, Linux aarch64, macOS universal2, Windows
  x86_64), creates the draft GitHub Release with 8 assets (4 binaries +
  4 `.sha256` sidecars).
- **Step 7**: CEO promotes draft to public via
  `gh release edit v0.1.2 --draft=false --notes-file <path>` (release
  notes path PM provides separately — see "Release notes draft" below).

Your worktree work is **steps 2-3 only**. Steps 4-7 are CEO actions.
You document them in the handoff so PM/CEO have a clear post-merge
runbook.

## Data contract

### `pyproject.toml` edit

```diff
 [project]
 name = "novetest"
-version = "0.1.1"
+version = "0.1.2"
 ...
```

Single line. Nothing else in `pyproject.toml` changes. No
`[tool.hatch.build.targets.wheel.force-include]` edits, no `[project.dependencies]`
edits, no `[project.optional-dependencies]` edits — even if you notice
something stale, surface it as a question rather than bundling.

### Envelope contract after the bump

```bash
uv pip install -e .  # if you have a local checkout
novetest --version --output json
```

Must report:

```json
{
  "command": "version",
  "ok": true,
  "schema": "novetest/v1",
  "data": {
    "installedVersion": "0.1.2",
    "platform": "<linux-x86_64|linux-aarch64|macos-universal2|windows-amd64>",
    "pythonVersion": "<3.11.x or 3.12.x>",
    "installLocation": "<absolute path to python interpreter>"
  },
  "errors": [],
  "warnings": []
}
```

The `installedVersion` field must be `"0.1.2"` exactly — empirical
proof that Path A's `importlib.metadata.version("novetest")` resolves
the bumped value correctly.

## Files to write / modify

### 1. MODIFY — `pyproject.toml`

Single 1-line edit per the diff above.

### 2. (Nothing else)

That is the entirety of the source-side work. Path A makes this
release the simplest possible cycle.

## Files NOT to touch

- `src/novetest/__init__.py` — Path A. **Never edit.** The
  `importlib.metadata` resolution handles version dynamically.
- `src/novetest/cli/app.py` — no version literal to update; the
  `version=__version__` parameter on `App(...)` is dynamic.
- Any other `src/**` or `tests/**`. If you find a bug, file a
  question to PM; do not bundle a fix into a release cycle.
- `.github/workflows/release-test.yml` — already tag-gated correctly.
- `NOTICES.md` — frozen for this release. Any third-party-dep update
  goes in a future cycle.
- `LICENSE` / `CLA.md` / `CCLA.md` / `CONTRIBUTING.md` — frozen.
- `README.md` — the Windows install one-liner is already correct on
  main; v0.1.2 publication is what makes it stop 404'ing.
- `agent-comms/decisions/**` — these accumulate forever.

## Verification commands (must-pass before reporting done)

These run in your isolated worktree against the bumped `pyproject.toml`:

```bash
# 1. Re-install in editable mode to pick up the bumped version
uv pip install -e .

# 2. Verify Path A resolves the new version dynamically
uv run novetest --version --output json | python3 -c 'import sys,json; e=json.load(sys.stdin); assert e["data"]["installedVersion"]=="0.1.2", e; print("VERSION OK:", e["data"]["installedVersion"])'

# 3. Verify the wheel METADATA also reports 0.1.2
uv build --wheel
unzip -p dist/novetest-0.1.2-*.whl novetest-0.1.2.dist-info/METADATA | grep "^Version:"

# 4. Verify NOTICES.md still ships in the wheel (regression guard for #8 from 2026-06-19)
unzip -l dist/novetest-0.1.2-*.whl | grep "NOTICES\.md"

# 5. Smoke the new licenses verb (depends on Orchestration cycle being merged first)
uv run novetest licenses --output json | python3 -c 'import sys,json; e=json.load(sys.stdin); assert e["ok"] and len(e["data"]["licenses"])==5; print("LICENSES OK")'

# 6. Full suite — should be byte-equivalent to pre-bump (no test touches version literal)
uv run pytest -q tests/unit tests/integration

# 7. mypy --strict GREEN
uv run mypy --strict src/novetest
```

## Definition of Done (8 bullets — PM ticks at cycle close)

- [ ] **#1 Version bumped**: `pyproject.toml::version == "0.1.2"`;
      no other line in `pyproject.toml` changed.
- [ ] **#2 No `src/` touched**: `git diff main -- src/` is empty
      (Path A binding).
- [ ] **#3 No `tests/` touched**: `git diff main -- tests/` is empty.
- [ ] **#4 Runtime envelope reports 0.1.2**: `novetest --version
      --output json` `data.installedVersion == "0.1.2"`.
- [ ] **#5 Wheel METADATA reports 0.1.2**: `unzip -p dist/*.whl
      *.dist-info/METADATA | grep ^Version:` returns `Version: 0.1.2`.
- [ ] **#6 NOTICES.md still ships in wheel**: regression guard for
      2026-06-19 Wave 1 #8 holds.
- [ ] **#7 `novetest licenses` verb operational**: empirical smoke
      against the merged-with-Orchestration main returns the 5-package
      envelope (this DoD is non-binding if Orchestration's cycle has
      not yet merged by the time you reach this verification — file
      handoff with this bullet noted as "deferred to post-merge with
      Orchestration").
- [ ] **#8 Full suite GREEN**: pytest pass count unchanged from
      pre-bump baseline; mypy --strict GREEN.

## Post-merge CEO runbook (you document in handoff)

For CEO's convenience, your handoff body should include a copy-pasteable
runbook for steps 4-7:

```bash
# Pre-tag empirical validation
gh workflow run release-test.yml --ref main
# Wait for completion; cite run URL in cycle-close history

# Tag
git fetch && git checkout main && git pull
git tag -a v0.1.2 -m "v0.1.2 - Windows install + human text + licenses verb + post-MVP polish"
git push origin v0.1.2

# Wait for release-test.yml on tag push to create draft release
# Verify draft has 8 assets (4 binaries + 4 .sha256)
gh release view v0.1.2

# Promote (release notes path supplied by PM)
gh release edit v0.1.2 --draft=false --notes-file <PM-supplied-notes-path>
```

PM will provide the release notes file path at cycle close.

## Release notes draft (PM owns; mirrored here so brief is self-contained)

PM will prepare and commit the release notes at
`design/release-notes/v0.1.2.md` (NEW file) AFTER your handoff lands
and CEO has dispatched the pre-tag empirical validation. The notes
follow the v0.1.0/v0.1.1 precedent: user-impact-focused, short,
ordered by user-observable significance.

Tone (CEO-confirmed Q4=iii at brief authoring):

- (i) Short, user-impact-focused → **selected**
- (ii) Detailed changelog → out
- (iii) PM drafts (i), CEO reviews → **selected workflow**

Skeleton PM will use:

```markdown
# v0.1.2

## Highlights

- **Windows install support**: `irm https://...install.ps1 | iex` now
  installs a working `novetest.exe` on Windows 10/11.
- **Human-readable text output**: `novetest <verb>` (default mode)
  now emits readable summaries instead of pretty-printed JSON. AI
  agents continue to use `--output json` for the byte-frozen contract.
- **Third-party licenses surface**: `novetest licenses` enumerates the
  5 third-party components Nove Test redistributes or links to.
  `--full` includes the verbatim Apache 2.0 + BSD 3-Clause license
  texts.
- **First-run latency budget**: every release is gated on a 25-second
  ceiling for cold-start `novetest --version` (current empirical:
  10.5s on Ubuntu).

## Internal polish

- Wheel NOTICES.md inclusion is now CI-probed (regression guard).
- Coverage-private path helpers promoted to a shared utility.
- Adapter warnings now flow exclusively through `envelope.warnings[]`
  (v1 metadata bridge sunset).
```

You do NOT write this file. PM does, at cycle close, post-merge.

## `gh` auth read-only constraint (PROCEDURAL REALITY)

Per 2026-06-18 Windows install cycle's learning §3, the
`yongjunshin` identity that the Release team session inherits has
**READ-only** permissions on `Nove-Lab/Nove-Test`. This means:

- You CAN: pull, fetch, clone, read PR/issue/release state, run local
  build/test.
- You CANNOT: push branches, push tags, create releases, promote
  drafts.

**Procedure**:

1. Work in your isolated worktree as normal.
2. Run all verification commands locally.
3. File the handoff at
   `agent-comms/handoffs/release-team-2026-06-22-v0.1.2-publication.md`
   noting "branch ready; awaiting CEO push".
4. CEO pushes your branch, FF-merges to main, dispatches release-test,
   pushes tag, promotes draft.

This is the same pattern Windows install cycle used (`c25fa2f` was
pushed by CEO). It works cleanly; no friction.

## Karpathy guidelines (mandatory invocation)

Before editing `pyproject.toml`, invoke the
`andrej-karpathy-skills:karpathy-guidelines` skill via the Skill tool.
Application:

1. **Think Before Coding** — confirm Path A is operationally live (it
   is; verified via `grep` for `_pkg_version` in `__init__.py`).
2. **Simplicity First** — single 1-line edit. No `[tool.poetry.version]`
   parallel field, no version-bump-script side effects, no
   `_version.py` injection. Just the literal `0.1.1` -> `0.1.2`.
3. **Surgical Changes** — `git diff main -- pyproject.toml` must show
   exactly ONE line changed (the `version` line) with zero whitespace
   noise.
4. **Goal-Driven Execution** — DoD #1 (version bumped) and DoD #4
   (envelope reports 0.1.2) are the binding empirical gates. Everything
   else is verification overhead.

## Reporting back to PM (in your handoff)

Standard handoff at `agent-comms/handoffs/release-team-2026-06-22-v0.1.2-publication.md`:

- "DoD bullets believed closed" with citation (each bullet -> commit
  hash + line).
- Verbatim output of verification command #2 (the runtime envelope) -
  empirical proof Path A resolves correctly.
- Verbatim output of verification command #3 (wheel METADATA grep) -
  empirical proof the build picks up the bumped version.
- Note any deviation (none expected - this is a 1-line edit).
- The post-merge CEO runbook (copy from §"Post-merge CEO runbook").
- Confirmation that the parallel Orchestration cycle's merge happened
  BEFORE your worktree was created (i.e., your worktree's base
  `main` HEAD already contains the licenses verb). If Orchestration
  has not merged yet when you're ready to start, surface a question to
  PM rather than racing them.

## Estimated effort

- Worktree creation + 1-line edit: ~5 min
- Local verification: ~10 min (mostly waiting on `uv build --wheel`
  and full pytest)
- Handoff drafting: ~15 min
- Total: ~30 min wall time, dominated by waiting on builds.

## Why this matters

1. **README is consistent again**: the Windows install one-liner stops
   404'ing the moment v0.1.2 has a Windows binary asset attached.
2. **Users get ~5 weeks of accumulated improvements**: human text,
   Windows pipeline, license verb, faster-first-run guarantee, wheel
   probe, internal cleanup. All quality-of-life.
3. **Release cycle is now operationally trivial**: Path A's promise
   ("future version bumps are 1-line") is empirically realized for
   the second consecutive release (v0.1.1 was the first; v0.1.2 is
   the proof-of-concept stabilization).

## Parallel cycle awareness

Twin Orchestration cycle: `novetest licenses` CLI verb at
`agent-comms/tasks/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md`.

**Merge order**: Orchestration FIRST; you SECOND. Their file
footprint does not touch `pyproject.toml::version`; their potential
`pyproject.toml::[tool.hatch.build.targets.wheel.force-include]` edit
(only if they take the importlib.resources path, which is the second
choice) is in a different section. If both touch `pyproject.toml`,
rebase / merge order is alphabetical-by-team per the 2026-06-09
Windows-CI fix triple precedent: orchestration -> release.

If Orchestration has not finished by the time you're ready to start
your worktree: stand by. File a question to PM if the wait exceeds
expected (~1 working day).

You are NOT blocked from PRE-AUTHORING your worktree branch with the
1-line edit applied - but the FF-merge step waits for Orchestration's
merge. PM coordinates with CEO if any sequencing collision surfaces.
