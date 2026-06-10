---
from: novetest-release-team
to: novetest-pm-team
type: handoff
status: complete
created: 2026-06-10
slug: release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag
related:
  - agent-comms/tasks/release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag.md
  - agent-comms/questions/release-team-2026-06-10-version-source-of-truth-architectural-followup.md
  - agent-comms/history/2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md
  - agent-comms/decisions/2026-06-10-license-apache-2.0-with-cla.md
---

# Release handoff — v0.1.1 first-public-facing release published as draft

## TL;DR

**Nove Test v0.1.1 first-public-facing release shipped as draft at
`9c16a36`.** Git tag pushed, `release-test.yml` GREEN, draft GitHub
Release exists with 6 assets attached, empirical smoke confirms
`"installedVersion": "0.1.1"` in the envelope — the Manual Test §"Nit
#2" wheel-version mismatch surfaced in the v0.1.0 cycle is empirically
closed.

v0.1.0 stays as the internal validation tag (`isDraft: true`, never
publicly promoted) per brief instructions; v0.1.1 is the user-facing
public release awaiting CEO promotion.

**Procedural exception**: the brief's stated "1-file change" premise
was empirically insufficient. CEO Option-A path approved Release team
scope extension to also bump `src/novetest/__init__.py:1`
(`__version__ = "0.0.0"` → `"0.1.1"`) — see §"Charter exception" below.
Architectural follow-up filed at
`agent-comms/questions/release-team-2026-06-10-version-source-of-truth-architectural-followup.md`
for PM to route (recommended: Path A — switch to `importlib.metadata`
in a future Orchestration cycle).

## Worktree / commits / branches

- **Code-slice worktree**: `/home/yjshin/dev/aispace/novetest-v0.1.1-bump`
- **Code-slice branch**: `release/v0.1.1-wheel-version-bump` (FF-merged into `main`)
- **Code-slice commit**: `9c16a36` — `release: bump wheel + runtime version to 0.1.1 for first public release`
- **Comms-slice worktree**: `/home/yjshin/dev/aispace/novetest-v0.1.1-handoff` (this handoff + WORKLOG + question + INDEX regen)
- **Comms-slice branch**: `release/v0.1.1-handoff`
- **Tags**:
  - `v0.1.0` (preserved, points at `348a198`) — internal validation tag
  - `v0.1.1` (new, points at `9c16a36`) — first public-facing release
- **Main HEAD progression**: `f17d508` → `9c16a36` (code slice) → (comms slice on FF-merge)

## File-level changes (3)

The slice modifies exactly 3 files, two by intent and one auto-resync.

### 1. `pyproject.toml` (1-line; brief §"File to modify")

```diff
 [project]
 name = "novetest"
-version = "0.0.0"
+version = "0.1.1"
 description = "AI-first testing orchestration that turns test execution into stored, comparable, reproducible evidence and recommendations."
```

This is the brief's explicit and only sanctioned source change.

### 2. `src/novetest/__init__.py` (1-line; CEO Option-A authorized)

```diff
-__version__ = "0.0.0"
+__version__ = "0.1.1"
```

**Charter exception**: `src/novetest/**` is normally forbidden for
Release team per `.claude/agents/novetest-release-team.md`. This edit
was specifically authorized by CEO via the Option-A path after Release
team surfaced that the brief's 1-file premise could not satisfy DoD #5.

The full architectural context: `src/novetest/__init__.py::__version__`
is a hardcoded literal, separate from `pyproject.toml::version`. The
CLI imports `__version__` at `src/novetest/cli/app.py:10` and the
envelope emitter reads it at
`src/novetest/orchestration/onboarding/identity.py:38`. No
`dynamic = ["version"]` mechanism exists in pyproject.toml, so the two
sources are independent. To make the envelope report
`installedVersion: "0.1.1"` (DoD #5, the load-bearing gate), BOTH
literals had to change.

This is filed for architectural follow-up at
`agent-comms/questions/release-team-2026-06-10-version-source-of-truth-architectural-followup.md`
— PM picks a path forward to prevent this duality from biting future
release briefs.

### 3. `uv.lock` (auto-resync; 1 line)

```diff
 [[package]]
 name = "novetest"
-version = "0.0.0"
+version = "0.1.1"
 source = { editable = "." }
```

`uv` auto-resynced the lockfile during `uv run mypy`/`uv build`. Not
deliberately edited; included in the commit because the lockfile would
have been left dirty otherwise.

## Verification results (DoD-aligned)

### Local (worktree @ `9c16a36`)

| DoD # | Check | Result |
|---|---|---|
| 1 | `pyproject.toml::version = "0.1.1"` diff | Verified — clean 1-line diff per §1 above |
| 2 | `uv build --wheel` filename | `novetest-0.1.1-py3-none-any.whl` produced at `/tmp/v011-wheel/` |
| 3 | `uv run mypy --strict src/novetest` | **Success: no issues found in 93 source files** (unchanged baseline) |
| 4 | `uv run pytest -q tests/unit tests/integration` | **1226 passed + 26 skipped + 1 failed** in 31.56s. The 1 failure is the pre-existing dotnet-host-equip failure (`test_xunit_v3_deferral_emits_envelope_warning_via_adapter` — `dotnet` not on PATH). Pre-edit and post-edit pytest runs were identical, confirming the `__init__.py` literal change has zero test surface impact. Delta vs brief expectation (1229+23): this dev host's host-equip skips diverge from the brief's reference host by ±3 (host-skip variance, not regression). |
| 5 | `uv run novetest --version --output json` envelope | **`"installedVersion": "0.1.1"`** ✓ — the LOAD-BEARING gate is satisfied. Verbatim envelope in §"Empirical CI envelope" below. |

### CI / pipeline (post-tag-push)

**`release-test.yml` run `27254232188`** on tag `v0.1.1`
(`9c16a36689806712be88b9930d6ad9309c2b1743`), trigger `push`:
<https://github.com/Nove-Lab/Nove-Test/actions/runs/27254232188>

| DoD # | Job | Conclusion |
|---|---|---|
| 8 | `build (linux-x86_64)` | success |
| 8 | `build (linux-aarch64)` | success |
| 8 | `build (macos-universal2)` | success |
| 8 | `install.sh end-to-end (linux-x86_64)` | success |
| 8 | `draft GitHub Release` | success |

**5/5 GREEN** end-to-end. The `release` job fired because of the
tag-push trigger and created the draft per
`softprops/action-gh-release@v3`.

### Draft GitHub Release `v0.1.1`

```json
{
  "isDraft": true,
  "name": "v0.1.1",
  "tagName": "v0.1.1",
  "assets": [
    {"name": "novetest-linux-aarch64",            "size": 6186080},
    {"name": "novetest-linux-aarch64.sha256",     "size": 89},
    {"name": "novetest-linux-x86_64",             "size": 6715840},
    {"name": "novetest-linux-x86_64.sha256",      "size": 88},
    {"name": "novetest-macos-universal2",         "size": 12185184},
    {"name": "novetest-macos-universal2.sha256",  "size": 92}
  ]
}
```

DoD #9 satisfied — `isDraft: true` + 6 assets attached. Asset byte
sizes are **identical** to v0.1.0's published sizes (the binary
container layout from PyApp + python-build-standalone is
size-stable across version-string-only deltas), well within the brief's
±5% tolerance.

### v0.1.0 preservation (brief §"v0.1.1 tag push procedure" step 7)

```
$ git tag --list | grep v0.1
v0.1.0
v0.1.1

$ gh release view v0.1.0 --json isDraft,name,tagName --jq '.'
{"isDraft":true,"name":"v0.1.0","tagName":"v0.1.0"}
```

**v0.1.0 draft release NOT deleted; internal validation tag preserved.**
CEO decides at v0.1.1 promotion time whether to delete v0.1.0 for
tidiness or keep as historical record.

### Empirical mirror-smoke (DoD #10)

Following the same auth-mirror pattern as v0.1.0 cycle (draft asset
URLs are auth-gated until public promotion):

```sh
$ curl -fsSL https://raw.githubusercontent.com/Nove-Lab/Nove-Test/v0.1.1/scripts/install.sh \
    -o /tmp/v011-smoke/install.sh
$ wc -l /tmp/v011-smoke/install.sh
224 /tmp/v011-smoke/install.sh   # v0.1.1 install.sh fetched cleanly from raw.gh CDN

$ gh release download v0.1.1 -R Nove-Lab/Nove-Test \
    -p 'novetest-linux-x86_64*' -D mirror/v0.1.1
# [drops novetest-linux-x86_64 6,715,840B + novetest-linux-x86_64.sha256 88B]

$ python3 -m http.server 28101 >&/tmp/http.log &     # fixture
$ NOVETEST_INSTALL_BASE_URL=http://127.0.0.1:28101 \
    NOVETEST_INSTALL_VERSION=v0.1.1 \
    NOVETEST_INSTALL_PREFIX=/tmp/v011-smoke/install-prefix \
    ./install.sh
Installing novetest (linux-x86_64, v0.1.1) into /tmp/v011-smoke/install-prefix
  binary: http://127.0.0.1:28101/v0.1.1/novetest-linux-x86_64
  sha256: http://127.0.0.1:28101/v0.1.1/novetest-linux-x86_64.sha256
SHA-256 verified (f563662a1b579067cedb62632080e7c52b82cd4698fae044aa30a225be984c29).
Installed: /tmp/v011-smoke/install-prefix/novetest

$ sha256sum mirror/v0.1.1/novetest-linux-x86_64
f563662a1b579067cedb62632080e7c52b82cd4698fae044aa30a225be984c29  mirror/v0.1.1/novetest-linux-x86_64
$ cat mirror/v0.1.1/novetest-linux-x86_64.sha256
f563662a1b579067cedb62632080e7c52b82cd4698fae044aa30a225be984c29  novetest-linux-x86_64
```

Local SHA-256 = published sidecar SHA-256 byte-identical. **v0.1.1's
SHA-256 (`f563662a1...`) DIFFERS from v0.1.0's
(`3d152e7b70c54d08...`)** despite identical asset byte-sizes — confirms
the rebuild baked the new `__version__` string into the binary
(structurally, the version string is the only delta in the entire
build input, so any byte difference in the artifact must trace back to
it).

Binary execution on this dev host fails with glibc 2.39 mismatch
(Ubuntu 22.04 ships glibc 2.35; the binary is built on ubuntu-latest =
Ubuntu 24.04 with glibc 2.39). This is the same expected-behavior
documented in the v0.1.0 cycle's handoff §"Surface B-2"; not a release
defect.

### Empirical CI envelope (load-bearing evidence)

The CI `install-script-e2e` job `80485446943` on ubuntu-latest ran
the same install + execute flow and returned a clean `novetest/v1`
envelope with `installedVersion: "0.1.1"`. Verbatim from the CI job
log at timestamp `2026-06-10T05:02:09.90Z`:

```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/runner/.local/share/pyapp/novetest/7904589091198436804/0.1.1/bin/python3",
    "installedVersion": "0.1.1",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.9",
    "verifiedAt": "2026-06-10T05:02:09.887867Z"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Two observable confirmations:

1. **`"installedVersion": "0.1.1"`** — the load-bearing DoD #5 gate is
   satisfied at the empirical-evidence layer (CI-built binary, not just
   local wheel install).
2. **`installLocation` PyApp path** now contains `/0.1.1/` segment
   (was `/0.0.0/` in v0.1.0's envelope) — PyApp's version-aware install
   path mechanism reflects the bump too. Two independent confirmations
   that the version flowed through every layer (pyproject → wheel
   METADATA → PyApp project_version → CLI envelope).

CI ran the flow TWICE (clean install + idempotent re-install). Both
runs returned structurally identical envelopes (modulo `verifiedAt`).

## DoD bullets believed closed (PM verifies + ticks)

| # | Bullet | Status | Evidence |
|---|---|---|---|
| 1 | `pyproject.toml::version = "0.1.1"` 1-line diff | **CLOSED** | `9c16a36`; diff in §"File-level changes" #1 |
| 2 | `uv build --wheel` produces `novetest-0.1.1-py3-none-any.whl` | **CLOSED** | filename verified at `/tmp/v011-wheel/` |
| 3 | `mypy --strict` clean (93 source files) | **CLOSED** | Success: no issues found in 93 source files |
| 4 | `pytest` baseline maintained | **CLOSED** | 1226 + 26 + 1 (pre-existing dotnet-host-equip); identical to pre-edit baseline |
| 5 | `uv run novetest --version --output json` returns `installedVersion: "0.1.1"` | **CLOSED** | Local + CI both confirm; verbatim envelopes above |
| 6 | FF-merged to `main`; cite merge SHA | **CLOSED** | `f17d508..9c16a36` FF; main HEAD = `9c16a36` |
| 7 | `v0.1.1` annotated git tag pushed | **CLOSED** | `git tag --list` shows `v0.1.1`; pushed via `git push origin v0.1.1` |
| 8 | `release-test.yml` GREEN on `v0.1.1` | **CLOSED** | Run `27254232188` 5/5 GREEN; URL above |
| 9 | Draft `v0.1.1` exists with 6 assets | **CLOSED** | `gh release view v0.1.1` snapshot above |
| 10 | Empirical mirror-smoke returns `installedVersion: "0.1.1"` | **CLOSED** | Both local mirror-smoke (Surface A install.sh fetch + Surface B install + SHA-256 verify) AND CI install-script-e2e envelope (verbatim above) confirm |
| 11 | WORKLOG entry | **CLOSED** | This commit's `WORKLOG.md` prepend |
| 12 | Handoff at this path | **CLOSED** | This file |
| 13 | `tools/regen_comms_index.py` | **CLOSED** | Run as part of this commit |

### Phase-0 DoD re-validation contribution

This slice re-validates (no new ticks; all already `[x]`):

- Phase 0 §"Definition-of-done" #1 (ci matrix) — triggered post-merge
  by both the code-slice and comms-slice pushes; PM cites in
  cycle-close history
- Phase 0 §"Definition-of-done" #4 (release-test.yml GREEN at v0.1.1
  tag) — run `27254232188`
- Phase 0 §"Definition-of-done" #5 (install-script-e2e job runs
  successfully) — job `80485446943` GREEN
- Phase 0 §"Definition-of-done" #6 (SHA-256 verification fires
  correctly) — SHA `f563662a1...` verified by install.sh; matches
  published sidecar byte-identically

### NEW closure (NOT in current `delivery-phasing.md` DoD)

- v0.1.0 cycle's Manual Test §"Nit #2" wheel-version mismatch nit
  — empirically resolved
- v0.1.1 milestone: first public-facing Nove Test release tag exists
  with verified-clean version envelope (awaiting CEO promotion)

## Charter exception (pinned)

**This slice contains 1 line of `src/novetest/__init__.py` that is
nominally outside Release team's writable surface.** The edit was
specifically authorized by CEO via Option-A path after Release team
surfaced the brief's premise bug. The exception covers exactly:

- **Scope**: `src/novetest/__init__.py:1` literal string change only
  (`__version__ = "0.0.0"` → `"0.1.1"`)
- **Trigger**: DoD #5 load-bearing gate unsatisfiable without it
- **Reason**: PM brief assumed `pyproject.toml::version` was the
  single source of truth for `installedVersion`; empirically false
  due to absent `dynamic = ["version"]` mechanism

For PM disposition: a follow-up architectural decision should codify
either (a) the duality is intentional and Release team has a standing
charter exception for `__version__` literal bumps, or (b) the duality
is closed via `importlib.metadata.version()` migration (recommended).
Question file at
`agent-comms/questions/release-team-2026-06-10-version-source-of-truth-architectural-followup.md`
proposes Path A / B / C with detailed pros and cons.

## Failure modes encountered (vs. brief's anticipated list)

| Brief failure mode | Encountered? | Disposition |
|---|---|---|
| #1 CI matrix transient flake | **N/A this slice** | No `ci.yml` red yet observed on code-slice push (`9c16a36`); comms-slice push may trigger a fresh `ci.yml` run that PM cites in cycle-close history |
| #2 release-test.yml asset byte-size drift | **No** | v0.1.1 sizes byte-identical to v0.1.0 sizes (no drift); SHA-256 differs as expected |
| #3 CDN propagation lag for draft assets | **No** | `gh release download` (auth-gated) returned assets immediately after `release` job completion |
| #4 `uv build` failing on `"0.1.1"` | **No** | PEP 440 fully compliant; built cleanly |
| #5 glibc mismatch on dev host | **YES** (expected per v0.1.0 cycle) | Mitigated via CI install-script-e2e envelope citation; not a release defect |

Plus **one surprise** not anticipated by the brief — see §"Charter
exception" above and the architectural follow-up question file.

## Out of scope (per brief §"Out of scope")

Per brief §"Out of scope" and §"Failure modes" guidance:

- **README promotion to repo root** — PM territory; handled in PM
  cycle-close per brief
- **v0.1.0 draft release deletion** — preserved; CEO discretion at
  v0.1.1 promotion time
- **DNS routing / Cloudflare setup / homepage hosting** — Amendment
  2026-06-10 of the install-script-hosting-url decision; CEO ops
- **CLA Assistant bot OAuth setup** — still post-v0.1.1
- **THIRD_PARTY_NOTICES expansion** — no new runtime deps; ships as
  per v0.1.0
- **Any decision document modifications** — none
- **Any test surface modifications** — none
- **Any other adapter / engine / fixture changes** — none

Two additional out-of-scopes pinned by this slice's path:

- **Architectural follow-up on version source-of-truth duality** —
  filed as a separate question for PM routing; not blocking this
  cycle's close
- **Codification of the Option-A charter exception as a standing
  policy** — folded into the architectural follow-up question; PM
  picks the path (codify-exception OR fix-architecturally)

## Cycle close direction (per brief §"Cycle close direction")

After Manual Test verifies this handoff AND PM cycle-closes:

1. **CEO promotes draft GitHub Release `v0.1.1` to public** via
   GitHub UI or `gh release edit v0.1.1 --draft=false` — **THE actual
   public launch moment**.
2. **CEO decides whether to delete the v0.1.0 draft release** (tidy)
   or keep as internal validation historical record.
3. **PM promotes README v3** (`design/marketing/README-v0.1.1-draft.md`)
   to repo root `README.md` in cycle-close commit per brief.
4. **PM dispatches Orchestration team** for the architectural
   follow-up per the question file's Path A (recommended): switch
   `__version__` to `importlib.metadata.version("novetest")` so
   future release cycles need only the 1-line pyproject.toml change.
5. **PM may distill into a small history entry** capturing the bump
   + first-public-promotion moment + the architectural finding.

## Reporting back (per charter §"Reporting back")

- **Worktree path / branch / commit SHAs (pre-bump + post-bump)**:
  - Pre-bump main HEAD: `f17d508`
  - Post-bump main HEAD: `9c16a36` (code slice)
  - Code-slice worktree: `/home/yjshin/dev/aispace/novetest-v0.1.1-bump` on `release/v0.1.1-wheel-version-bump`
  - Comms-slice worktree: `/home/yjshin/dev/aispace/novetest-v0.1.1-handoff` on `release/v0.1.1-handoff`
- **Verbatim diff of `pyproject.toml`**: §"File-level changes" #1
- **Verbatim diff of `src/novetest/__init__.py`**: §"File-level changes" #2 (CEO Option-A exception)
- **`mypy --strict` result**: Success: no issues found in 93 source files
- **`pytest` result**: 1226 passed + 26 skipped + 1 pre-existing dotnet-host-equip failure in 31.56s
- **`uv build` filename**: `novetest-0.1.1-py3-none-any.whl`
- **Local `--version --output json` envelope**: `installedVersion: "0.1.1"` ✓
- **`ci.yml` post-merge run number**: PM cites in cycle-close history (DoD-equivalent of last cycle's pattern; both code-slice and comms-slice merges trigger fresh `ci.yml` runs)
- **`release-test.yml` run number + URL for v0.1.1 tag**:
  - Run `27254232188`
  - <https://github.com/Nove-Lab/Nove-Test/actions/runs/27254232188>
  - 5/5 jobs GREEN; total ~3m
- **`gh release view v0.1.1` output**: §"Draft GitHub Release v0.1.1" above; isDraft=true; 6 assets
- **Empirical smoke command + envelope**: §"Empirical mirror-smoke" and §"Empirical CI envelope" above; verbatim envelope from CI job `80485446943`
- **WORKLOG entry text**: in this commit
- **Confirmation v0.1.0 draft NOT deleted**: §"v0.1.0 preservation" above
- **Release-pipeline surprises**: ONE pinned — the brief's load-bearing DoD #5 could not be satisfied with the brief's stated 1-file scope; CEO authorized Option A (scope extension) in-cycle; architectural follow-up filed as a question for PM disposition

## Closure

This slice's deliverable is **v0.1.1 first-public-facing Nove Test
release tag published as draft, with the v0.1.0 wheel-internal version
mismatch nit empirically closed**. The product is now ready for public
launch — only CEO promotion remains. The procedural exception (Release
team `src/novetest/__init__.py` 1-line edit) is documented and the
architectural follow-up question is filed for PM to route.
