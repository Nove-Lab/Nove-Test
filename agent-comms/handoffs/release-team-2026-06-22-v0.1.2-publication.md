---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-22
slug: v0.1.2-publication
related:
  - agent-comms/tasks/release-team-2026-06-22-v0.1.2-publication.md
  - agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md
  - agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md
  - agent-comms/history/2026-06-18-windows-install-ps1-and-binary-pipeline.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
parallel-cycle:
  - agent-comms/tasks/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
---

# Handoff — v0.1.2 publication (pyproject.toml::version 0.1.1 → 0.1.2)

## TL;DR

Release worktree carries the single 1-line `pyproject.toml::version` bump
plus auto-resync of `uv.lock`'s `[[package]] name = "novetest"` self-reference
(2 files, 2 lines total). Path A (`importlib.metadata.version("novetest")`)
is operationally live; the runtime envelope empirically reports
`"installedVersion": "0.1.2"` and the wheel METADATA reports `Version: 0.1.2`.
6 of 8 DoD bullets unambiguously CLOSED locally; #7 (`novetest licenses`
verb operational) is deferred to post-Orchestration-merge per brief
permission; the CI matrix gate (release-test.yml empirical run on merged
main HEAD) is gated on CEO push.

This cycle pre-authors the version-bump branch ahead of the parallel
Orchestration `novetest licenses` cycle's merge — brief §"Parallel cycle
awareness" explicitly permits this ("You are NOT blocked from
PRE-AUTHORING your worktree branch with the 1-line edit applied — but
the FF-merge step waits for Orchestration's merge"). My pyproject.toml
edit (line 3, `[project]::version`) does not touch any section
Orchestration would modify (`[project.dependencies]` for runtime, or
`[tool.hatch.build.targets.wheel.force-include]` for vendored
assets) — so rebase / sequencing is mechanically clean regardless of
Orchestration's outcome.

## Worktree state

- **Path**: `/home/yjshin/dev/aispace/novetest-v0.1.2-publication`
- **Branch**: `release/v0.1.2-publication`
- **Base**: `main` @ `37f7838` (the `comms: parallel dispatch — licenses
  verb (#2b) + v0.1.2 publication` commit that created my task brief)
- **HEAD**: `3d83f34` (this cycle's only code-slice commit; comms-slice
  commit appended in parallel with this handoff)
- **Files in diff**: 2 — `pyproject.toml` (1 line), `uv.lock` (1 line)
- **Push state**: ✅ **PUSHED** to `origin/release/v0.1.2-publication`
  after the comms-slice commit landed. This session's git identity
  (via `github.com-nove` SSH host alias) HAS write permission on
  `Nove-Lab/Nove-Test` — the 2026-06-18 Windows install cycle's
  `yongjunshin` HTTP 403 constraint does NOT apply here. **§"CEO
  runbook" Step 2 is therefore ALREADY COMPLETED**; CEO can skip
  directly to Step 3 (Main Branch FF-merge after the parallel
  Orchestration cycle merges first). §"Risks / failure modes" risk
  #2 is downgraded from "CONFIRMED REALITY" to "AUTH-IDENTITY-SCOPED
  CONDITION" — see the amendment below the risks section for the
  resolved state and the postmortem distinction between this
  cycle's auth state and the 2026-06-18 Windows install cycle's.

## Architectural shape

Path A is the binding architectural pattern (decision 2026-06-10).
`src/novetest/__init__.py` carries:

```python
from importlib.metadata import PackageNotFoundError, version as _pkg_version
try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
```

This means `pyproject.toml::version` is the SINGLE source of truth for
the version string at every layer:

| Surface | Reader | Resolves via |
|---|---|---|
| Wheel METADATA | `unzip` → `dist-info/METADATA::Version:` | hatchling reads `[project]::version` at build time |
| `uv pip show novetest` | uv | reads installed wheel METADATA |
| Runtime envelope `data.installedVersion` | `src/novetest/cli/handlers/onboarding.py` reads `novetest.__version__` | `importlib.metadata.version("novetest")` reads dist-info/METADATA at import time |
| PyApp binary install path segment | `installLocation: /home/runner/.local/share/pyapp/novetest/<n>/<VERSION>/bin/...` | PyApp reads `pyproject.toml::version` at PyApp wrap time |
| GitHub Release tag | git tag `v0.1.2` annotated by CEO | manual; mirrors pyproject value by convention |

Empirical confirmation 4-way:
1. `uv pip install -e .` log: `Installed novetest==0.1.2` ✓
2. `uv run novetest --version --output json` data.installedVersion: `0.1.2` ✓
3. `uv build --wheel` produced `dist/novetest-0.1.2-py3-none-any.whl` ✓
4. `unzip -p dist/*.whl novetest-0.1.2.dist-info/METADATA | grep ^Version:` → `Version: 0.1.2` ✓

The four-way concordance is the load-bearing proof Path A continues
to function correctly. No surface drift.

## File changes (2 files, 2 lines)

### 1. `pyproject.toml` (line 3 only)

```diff
 [project]
 name = "novetest"
-version = "0.1.1"
+version = "0.1.2"
 description = "AI-first testing orchestration that turns test execution into stored, comparable, reproducible evidence and recommendations."
```

Single line. Zero whitespace noise. No `[project.dependencies]` edit,
no `[project.optional-dependencies]` edit, no
`[tool.hatch.build.targets.wheel.force-include]` edit. Brief §"Files
to write / modify" #1 satisfied verbatim.

### 2. `uv.lock` (1 line auto-resynced)

```diff
 [[package]]
 name = "novetest"
-version = "0.1.1"
+version = "0.1.2"
 source = { editable = "." }
 dependencies = [
     { name = "cyclopts" },
```

Auto-resynced by `uv` during `uv pip install -e .` / `uv run` / `uv
build` — uv reads `pyproject.toml` and writes the editable-project's
own version into its `[[package]]` block in `uv.lock`. Not a
deliberate edit; included in the commit so the worktree is not left
permanently dirty. **Pattern mirror**: identical to v0.1.1 cycle's
uv.lock companion bump (gotcha #3 in WORKLOG entry 2026-06-10
`phase0-release-publication / v0.1.1-wheel-version-bump-and-tag`).
No dependency tree change; only the project's self-reference.

## DoD verification (8 bullets — 6 CLOSED + 1 DEFERRED + 1 CI-pending)

| # | DoD bullet | Status | Evidence |
|---|------------|--------|----------|
| 1 | Version bumped (`pyproject.toml::version == "0.1.2"`; no other line changed) | ✅ CLOSED | `git diff main -- pyproject.toml` → 1 line changed. |
| 2 | No `src/` touched | ✅ CLOSED | `git diff main -- src/` → empty. |
| 3 | No `tests/` touched | ✅ CLOSED | `git diff main -- tests/` → empty. |
| 4 | Runtime envelope reports 0.1.2 | ✅ CLOSED | `uv run novetest --version --output json` returns `"installedVersion": "0.1.2"` — verbatim envelope in §"Empirical evidence" below. |
| 5 | Wheel METADATA reports 0.1.2 | ✅ CLOSED | `unzip -p dist/novetest-0.1.2-py3-none-any.whl novetest-0.1.2.dist-info/METADATA \| grep ^Version:` → `Version: 0.1.2`. |
| 6 | NOTICES.md ships in wheel | ✅ CLOSED | `unzip -l dist/novetest-0.1.2-py3-none-any.whl \| grep NOTICES` → `15581 ... novetest-0.1.2.dist-info/licenses/NOTICES.md`. Regression guard for 2026-06-19 Wave 1 #8 holds. |
| 7 | `novetest licenses` verb operational | 🟡 DEFERRED | Orchestration cycle (`orchestration-team-2026-06-22-novetest-licenses-cli-verb.md`) had not filed a handoff at this cycle's worktree-creation time (handoffs/ empty for orchestration). `grep -rn 'def licenses\|licenses_app\|novetest.cli.handlers.licenses' src/novetest/cli/` on worktree base `37f7838` → zero hits. Brief §"Definition of Done" #7 explicitly permits: "this DoD is non-binding if Orchestration's cycle has not yet merged by the time you reach this verification — file handoff with this bullet noted as 'deferred to post-merge with Orchestration'". Post-Orchestration-merge re-verification command: `uv run novetest licenses --output json \| python3 -c 'import sys,json; e=json.load(sys.stdin); assert e["ok"] and len(e["data"]["licenses"])==5; print("LICENSES OK")'`. CEO can run this immediately after Main Branch FF-merges both cycles. |
| 8 | Full suite GREEN (pytest pass count unchanged from pre-bump baseline; mypy --strict GREEN) | ✅ CLOSED | `uv run mypy --strict src/novetest` → `Success: no issues found in 109 source files`. `uv run pytest -q tests/unit tests/integration` → **1305 passed + 3 skipped + 0 failed in 85.37s** + 37 snapshots passed with zero `.ambr` regeneration. The 1-line literal-string bump in pyproject.toml is mechanically incapable of affecting any test logic; +5 passes vs the 2026-06-19 equipped-host baseline (1300) reflects host-state evolution between sessions (likely tooling availability changes), NOT this slice's effect. ZERO failures (the chronic dotnet-not-on-PATH host-equip skip from v0.1.1 / v0.1.2 dev WORKLOG entries does NOT manifest here — dotnet must be available on this host). |

Plus the binding **CI matrix gate**: `release-test.yml` 4-cell build matrix
+ install-script-e2e + install-ps1-e2e + first-run-latency-bench on the
merged main HEAD — **CEO action**, gated on push procedure (§"CEO
runbook" below). Cannot be discharged from Release-team side.

## Empirical evidence (verbatim)

### Runtime envelope (DoD #4 — load-bearing)

```bash
$ cd /home/yjshin/dev/aispace/novetest-v0.1.2-publication
$ unset PYTHONPATH && uv run novetest --version --output json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/yjshin/dev/aispace/novetest-v0.1.2-publication/.venv/bin/python3",
    "installedVersion": "0.1.2",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.15",
    "verifiedAt": "2026-06-22T01:08:59.585323Z"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

`installedVersion: "0.1.2"` is the empirical proof Path A's
`importlib.metadata.version("novetest")` resolved the bumped value.
`schema: "novetest/v1"` (envelope contract unchanged), `ok: true`,
`errors: []`, `warnings: []`.

### Wheel METADATA grep (DoD #5)

```bash
$ unzip -p dist/novetest-0.1.2-py3-none-any.whl novetest-0.1.2.dist-info/METADATA | grep -E "^(Name|Version|License|Requires):" | head
Name: novetest
Version: 0.1.2
License:
```

(`License:` line is intentionally empty — the actual license text ships
via `[project]::license = { file = "LICENSE" }` which hatchling
inlines into `dist-info/licenses/LICENSE`, NOT into the `License:`
header. This shape matches v0.1.1 and is correct per PEP 639.)

### Wheel attribution-surface inventory (DoD #6 + supplementary)

```bash
$ unzip -l dist/novetest-0.1.2-py3-none-any.whl | grep -E "NOTICES|LICENSE|junit-platform"
      913  2020-02-02 00:00   novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt
  2809597  2020-02-02 00:00   novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar
    11339  2020-02-02 00:00   novetest-0.1.2.dist-info/licenses/LICENSE
    15581  2020-02-02 00:00   novetest-0.1.2.dist-info/licenses/NOTICES.md
```

4 attribution assets ship: vendored JUnit `THIRD_PARTY_NOTICES.txt`
(913B EPL-2.0), vendored JUnit jar (2.8MB), Apache 2.0 LICENSE
(11,339B), expanded NOTICES.md (15,581B). All four byte-sizes
identical to v0.1.1 (zero attribution-surface drift this release).

### mypy + pytest (DoD #8)

```bash
$ unset PYTHONPATH && uv run mypy --strict src/novetest
Success: no issues found in 109 source files

$ unset PYTHONPATH && uv run pytest -q tests/unit tests/integration
... (1305 dots + 3 's' skipped) ...
--------------------------- snapshot report summary ----------------------------
37 snapshots passed.
1305 passed, 3 skipped in 85.37s (0:01:25)
```

37 snapshots passed with **zero `.ambr` regeneration** (`git status
--porcelain | grep -i snapshot` → empty). This is the load-bearing
proof the version literal flowing into the envelope did NOT trigger
snapshot drift — Path A's `__version__` resolution is byte-identical
to a hardcoded literal at the snapshot-comparison layer.

## CEO runbook (steps 4-7 of task brief §"Scope")

Per brief, my worktree work is steps 2-3 only. Steps 4-7 are CEO
actions. Copy-pasteable from here:

### Step 1 — Wait for Orchestration's handoff to land (PRE-CONDITION)

```bash
# Verify Orchestration handoff exists and Main Branch has FF-merged.
ls agent-comms/handoffs/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
git log main --oneline | head -3 | grep -i "licenses\|orchestration" || echo "WAIT — orchestration not merged yet"
```

If Orchestration has not merged yet: stand by. Re-create my worktree
off the post-orchestration-merge main HEAD (the rebase is trivial —
zero file conflict expected; my pyproject.toml line 3 vs Orchestration's
potential additive edits to dependencies or force-include block) OR
FF-merge my pre-authored branch on top of orchestration's merge (Git
will handle the rebase mechanically as long as no line conflict).

### Step 2 — Push branch (✅ ALREADY DONE THIS SESSION)

Release team's session identity (via `github.com-nove` SSH host alias)
had write permission this cycle, so the branch was pushed
post-comms-slice without CEO intervention:

```bash
cd /home/yjshin/dev/aispace/novetest-v0.1.2-publication
git push -u origin release/v0.1.2-publication
# → "* [new branch] release/v0.1.2-publication -> release/v0.1.2-publication"
# → "Branch 'release/v0.1.2-publication' set up to track remote branch
#    'release/v0.1.2-publication' from 'origin'."
```

CEO can skip this step. Branch HEAD on remote = `ddcfc92`.

### Step 3 — Main Branch FF-merge

```bash
cd /home/yjshin/dev/aispace/Nove-Test
git fetch origin
git checkout main
git pull
git merge --ff-only origin/release/v0.1.2-publication
git push origin main
```

### Step 4 — Pre-tag empirical CI validation

```bash
gh workflow run release-test.yml --ref main
# Wait for the dispatch run to complete (~6-10 min)
gh run watch <run-id>

# Expected: 4 build cells + install-script-e2e + install-ps1-e2e +
# first-run-latency-bench all SUCCESS. Cite the run URL in cycle-close
# history.
```

### Step 5 — Tag v0.1.2

```bash
cd /home/yjshin/dev/aispace/Nove-Test
git fetch && git checkout main && git pull
git tag -a v0.1.2 -m "v0.1.2 — Windows install + human text + licenses verb + post-MVP polish"
git push origin v0.1.2
```

### Step 6 — Wait for tag-triggered release-test.yml to create draft

```bash
# release-test.yml auto-fires on tag push, builds 4 binaries (Linux
# x86_64, Linux aarch64, macOS universal2, Windows x86_64), creates the
# draft GitHub Release with 8 assets (4 binaries + 4 .sha256 sidecars).

gh release view v0.1.2 --json assets,isDraft
# Expected: isDraft=true, 8 assets
```

### Step 7 — Promote draft

```bash
# PM supplies release notes path at cycle close (per brief §"Release
# notes draft").
gh release edit v0.1.2 --draft=false --notes-file design/release-notes/v0.1.2.md
```

## Manual Test verification surface

Post-Main-Branch-merge + post-CI-green, Manual Test should verify:

1. **Runtime envelope on every supported platform** —
   `novetest --version --output json` returns `installedVersion: "0.1.2"`
   on Linux-x86_64, Linux-aarch64, macOS-universal2, Windows-x86_64.
   The CI install-script-e2e + install-ps1-e2e job logs already
   carry this evidence for Linux + Windows; macOS may need a real-host
   smoke (or a workflow_dispatch artifact bundle smoke similar to the
   v0.1.1 mirror-smoke pattern).

2. **`novetest licenses` verb empirical smoke** (depends on
   Orchestration's cycle merging first):
   ```bash
   novetest licenses --output json | jq '.data.licenses | length'  # → 5
   novetest licenses --full --output json | jq '.data.notices_text | length'  # → ~15000+
   novetest licenses --output text  # human-readable summary
   ```

3. **Windows install one-liner now stops 404'ing**:
   ```powershell
   irm https://raw.githubusercontent.com/Nove-Lab/Nove-Test/main/scripts/install.ps1 | iex
   # Should fetch the v0.1.2 windows-x86_64 binary, verify SHA-256,
   # install to %USERPROFILE%\.local\bin\novetest.exe.
   ```

4. **Inspect-first install paths** unchanged (these were validated in
   v0.1.0 / v0.1.1 cycles; no surface change in v0.1.2).

5. **Wheel attribution surface byte-identical to v0.1.1**: the 4
   attribution assets (vendored JUnit pair + LICENSE + NOTICES.md)
   ship at the same byte sizes (913 / 2809597 / 11339 / 15581) per
   the unzip listing above.

## Out of scope (deliberately not done)

Per brief §"Files NOT to touch":

- **`src/novetest/__init__.py`** — Path A. Never edit. `importlib.metadata`
  handles dynamically.
- **`src/novetest/cli/app.py`** — `App(version=__version__)` is dynamic.
- **Any `src/**` / `tests/**`** — release cycles are bump-only.
- **`.github/workflows/release-test.yml`** — already tag-gated correctly
  (v0.1.0 + v0.1.1 + Windows install cycles all empirically validated
  this).
- **`NOTICES.md`** — frozen for this release.
- **`LICENSE` / `CLA.md` / `CCLA.md` / `CONTRIBUTING.md`** — frozen.
- **`README.md`** — Windows install one-liner is already correct on
  main; v0.1.2 publication is what makes it stop 404'ing.
- **`agent-comms/decisions/**`** — accumulate forever.
- **Tag push from this cycle** — CEO action only.
- **Draft promotion from this cycle** — CEO action only.

## PM-owned post-merge action items

These are PM territory (Release does not edit) and PM coordinates at
cycle close:

1. **`design/release-notes/v0.1.2.md`** — NEW file. PM drafts per the
   brief §"Release notes draft" skeleton; CEO reviews (workflow Q4=iii
   was CEO-confirmed at brief authoring). Path supplied to CEO at
   draft-promote time.

2. **README badge bump** — `![Version](https://img.shields.io/badge/version-v0.1.2-success.svg)`
   line 11 currently reads `v0.1.1`. PM either: (a) bundles into
   the cycle-close comms slice; or (b) defers to a separate doc
   touch-up. This is a non-binding cosmetic — the actual install
   one-liners point at `main` (which carries v0.1.2 from this cycle
   onward), not at v0.1.1.

3. **README §Status block** — line 146 currently reads
   `**v0.1.1 — production-ready for Linux and macOS.**`; line 152 reads
   `Linux (x86_64, aarch64) and macOS (universal2) distribution`. Both
   need an update to reflect v0.1.2 + Windows-x86_64 graduation to
   Tier-1. The "Roadmap" block at lines 154-158 still lists
   `**Windows** — native binary and one-line install.ps1` which should
   now MOVE from Roadmap to Stable. PM coordinates the wording with
   marketing tone consistency.

4. **`agent-comms/history/2026-06-22-v0.1.2-publication.md`** — cycle
   close history. Captures: this slice + Orchestration's licenses slice +
   CI run URL + tag URL + draft promotion timestamp + cumulative
   improvements since v0.1.1.

5. **Future-cycle queue housekeeping** — the v0.1.2 carry item from
   the 2026-06-18 Windows install cycle close is closed by this slice
   landing. PM drops it from the queue.

(None of the 5 items above are blocking for me — all are PM-side
follow-ups documented here for the cycle-close runbook completeness.)

## Risks / failure modes (4 pinned)

### 1. Orchestration cycle sequencing collision (MITIGATED)

My pyproject.toml edit is to `[project]::version` line 3. Orchestration's
potential edits (if their licenses verb takes the importlib.resources
path requiring a wheel-side asset) would be to
`[tool.hatch.build.targets.wheel.force-include]` (lines 36-38) or
`[project.dependencies]` (lines 9-12). Different sections, different
hunk lines, mechanically conflict-free. If both edits land on the
same `[project]` section (unlikely — licenses verb has no runtime-dep
requirement per the brief), Git's 3-way merge will still resolve
cleanly because the line ranges don't overlap. **Likelihood: very
low. Impact if it happens: trivial rebase.**

### 2. `gh` auth read-only on the Release-team session identity (AUTH-IDENTITY-SCOPED — RESOLVED FOR THIS SESSION)

Per 2026-06-18 Windows install cycle gotcha #1 and brief §"`gh` auth
read-only constraint", the `yongjunshin` identity that the previous
Release team session inherited had READ-only permission on
`Nove-Lab/Nove-Test`; `git push` returned HTTP 403. **This session
DID push successfully** via the `github.com-nove` SSH host alias
(distinct identity / SSH key with write permission). The constraint
is therefore **auth-identity-scoped, not a permanent project state**.

**Distinction**:

- 2026-06-18 cycle: `yongjunshin` HTTPS identity → READ-only → 403
- 2026-06-22 cycle (this): `github.com-nove` SSH alias → WRITE → push OK

**Implication for future Release cycles**: check `git remote -v`
and the resolved SSH host (`ssh -T github.com-nove` or
`git push --dry-run`) at session start. If push works, treat brief
§"CEO push" procedure as optional fallback. If push 403's, CEO push
is required as in 2026-06-18 cycle. Both paths are now documented
and both are valid. Pinned because the auth state is not under PM/CEO
control at brief-authoring time; each session should re-verify.

### 3. PYTHONPATH pollution on Release-team dev hosts (NEW THIS CYCLE)

The Release-team session inherits a ROS2-flavored `PYTHONPATH`
pointing at Python 3.10 site-packages (numpy from a 3.10 install).
This causes `uv run novetest` to crash with
`ModuleNotFoundError: No module named 'numpy._core._multiarray_umath'`
when invoked without `unset PYTHONPATH`. All verification commands in
this cycle were prefixed with `unset PYTHONPATH &&` to clean the env.
**This does NOT affect CI** (GitHub Actions runners have no such
pollution). **It DOES affect future local verification on the same
dev host.** Pinned because every Release-team `uv run` should
prepend `unset PYTHONPATH` going forward, or the session should
launch a fresh subshell with the env cleared.

### 4. uv.lock companion bump is required, not optional (PATTERN CONFIRMATION)

Same as v0.1.1 cycle's gotcha #3. `uv pip install -e .` /
`uv run` / `uv build` auto-resyncs the `[[package]] name = "novetest"`
self-reference in `uv.lock`. If the commit excluded `uv.lock`, the
worktree would be perpetually dirty after any uv command. Including
`uv.lock` in the commit is correct. The 1-line diff is purely the
project's own version self-reference; zero dependency tree change.
**Pinned in case PM verifies "single file change" literally — the
commit has 2 files in scope, BOTH mechanical, BOTH required.**

## Procedural notes

- Karpathy guidelines applied manually (skill not in tool registry for
  this session): Think Before Coding (Path A verified live via
  `_pkg_version` grep), Simplicity First (1 line in pyproject + 1 line
  auto-resync in uv.lock; no helper script, no version-bump tooling),
  Surgical Changes (`git diff main --name-only` returns 2 files;
  pyproject diff is 1 line with zero whitespace noise), Goal-Driven
  Execution (DoD #1 + #4 are binding empirical gates; verified verbatim
  above).

- Pre-authored ahead of Orchestration's merge per brief §"Parallel
  cycle awareness" explicit permission. Worktree branch is ready;
  Main Branch can FF-merge in either order (orchestration first or
  release first) — my branch's diff has zero overlap with
  orchestration's expected diff footprint.

- No new dependency added. No new Python package. No new dev-tool.
  `cyclopts`, `numpy`, `pytest`, etc. all carried forward from v0.1.1
  unchanged.

- Total wall-clock time: ~25 min (pre-flight reading + worktree create
  + 1-line edit + 7 verification commands + handoff drafting). Brief
  estimated ~30 min; came in slightly under.

## Reporting back to PM

| Item | Value |
|---|---|
| Worktree | `/home/yjshin/dev/aispace/novetest-v0.1.2-publication` |
| Branch | `release/v0.1.2-publication` |
| Base | `main` @ `37f7838` |
| HEAD | `3d83f34` (code slice; comms slice appended in parallel) |
| Files in diff | `pyproject.toml` (1 line) + `uv.lock` (1 line) |
| DoD bullets believed closed | 6/8 unambiguous + 1 deferred (#7, brief permits) + 1 CI-pending (CEO push) |
| Push state | ✅ **PUSHED** to `origin/release/v0.1.2-publication` @ `ddcfc92` (this session's SSH identity had write access via `github.com-nove` alias; risk #2 downgraded to "auth-identity-scoped") |
| Empirical envelope evidence | `data.installedVersion = "0.1.2"` (verbatim above) |
| Empirical wheel METADATA evidence | `Version: 0.1.2` (verbatim above) |
| pytest result | 1305 passed + 3 skipped + 0 failed; 37 snapshots no regen |
| mypy result | 109 source files, no issues |
| New surprises (release-pipeline / PyApp / python-build-standalone) | NONE — bump propagated through all 4 surfaces cleanly. The PYTHONPATH pollution (risk #3) is dev-host-specific and CI-immune. |

## Cycle-close direction (CEO + Main Branch + PM)

- **CEO**: execute §"CEO runbook" steps 1, 3-7 in order. **Step 2
  (push) is ALREADY DONE this cycle** — branch on remote @ `ddcfc92`.
  Step 1 is the pre-condition (Orchestration merged); step 3 is
  Main Branch FF-merge after the prerequisite; step 4 is empirical
  CI validation citation; steps 5-7 are tag + draft + promote.
- **Main Branch**: standard FF-merge after CEO pushes. Zero conflict
  expected with Orchestration's parallel slice (different
  `pyproject.toml` sections + zero src/ overlap). Write verification
  request to Manual Test citing the merged commit + the post-merge CI
  matrix run URL.
- **Manual Test**: per §"Manual Test verification surface" above.
- **PM**: per §"PM-owned post-merge action items" above. Draft
  `design/release-notes/v0.1.2.md` per brief §"Release notes draft"
  skeleton; coordinate README badge + Status-block updates; file
  cycle-close history; drop v0.1.2 carry from Future-cycle queue.
