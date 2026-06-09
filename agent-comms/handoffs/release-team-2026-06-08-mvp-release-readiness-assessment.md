---
from: novetest-release-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-06-08
slug: mvp-release-readiness-assessment
related:
  - agent-comms/tasks/release-team-2026-06-08-mvp-release-readiness-assessment.md
  - agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md
  - agent-comms/decisions/2026-05-14-install-script-hosting-url.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-05-16-phase0-release-and-phase2-entry.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# Handoff — MVP Release-Readiness Assessment (Phase 1+3 done; Phase 2 routed out)

## Worktree

- Branch: `release/mvp-readiness-assessment`
- Path: `/home/yjshin/dev/aispace/novetest-mvp-release-readiness-assessment`
- Based on `main` head `bd4d300` (`comms: brief MVP release readiness assessment for Release team`)
- Files written:
  - `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md` (this file)
  - `agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md` (routes the one blocker out to PM)
  - `WORKLOG.md` (assessment entry)
  - `agent-comms/INDEX.md` (regenerated)
- Files NOT written (deliberately — task said "blocker만 본 슬라이스에서 fix" and the blocker fix surface is engine-team forbidden territory for this team): no `src/**`, no `tests/**`, no `pyproject.toml`, no `.github/workflows/**`, no `scripts/install.sh`, no `THIRD_PARTY_NOTICES.txt`. Justification per-file is laid out in the assessment matrix below.

## TL;DR

**MVP is NOT release-ready as of `bd4d300`.** There is exactly one
release-blocker: **`ci.yml` is red on Windows × all 3 Python versions
(20 failing tests, chronic state since 2026-06-01)**. The fix surface
lives entirely outside Release-team writable scope — across Coverage,
Localization, and Run teams' `src/` + `tests/`. Routed to PM via the
sibling question file. The OTHER half of the release pipeline (PyApp
binary build matrix + install.sh end-to-end + SHA-256 verify) **is
empirically green at HEAD** — verified by a fresh workflow_dispatch
of `release-test.yml` triggered at the start of this slice (run
[`27176266868`](https://github.com/Nove-Lab/Nove-Test/actions/runs/27176266868)).

## Sign-off statement

> **MVP NOT release-ready as of `bd4d300`.**
>
> **Blocker (1)**: Phase 0 DoD #1 (`uv run pytest -q` green across 3 OSes
> × 3 Python versions) — empirically STALE. CI matrix has been red on
> all 3 Windows cells for 8 days (since `53f7920`, 2026-06-01). 20
> distinct test failures per Windows cell, identical across Python
> 3.11 / 3.12 / 3.13. Fix surface is forbidden territory for Release
> team (`src/novetest/**` + `tests/unit/**` + `tests/integration/**`).
> Routed to PM via `agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md`.
>
> **Non-blockers, empirically green at HEAD**: Phase 0 DoD #2 (signed
> binary build), #3 (curl-pipe-sh end-to-end), #4 (SHA-256 verify +
> tampered-binary integration test). Verified live in
> `release-test.yml` run [27176266868](https://github.com/Nove-Lab/Nove-Test/actions/runs/27176266868)
> dispatched on HEAD: all 3 PyApp targets built clean, `.sha256`
> sidecars generated, install.sh clean+idempotent install both
> returned a valid `novetest/v1 --version` envelope.

## Assessment matrix

| # | Item (per task §"Phase 1") | Status | Detail |
|---|----------------------------|--------|--------|
| 1.1 | CI matrix `ci.yml` (3 OS × 3 Python = 9 cells) | **🔴 BLOCKER** | Linux × 3 + macOS × 3 = 6 cells GREEN. Windows × 3 = 3 cells RED. 20 distinct pytest failures per Windows cell (identical across Python 3.11/3.12/3.13). Failure split: 5 Coverage parser tests (cross-drive `Path.relative_to` ValueError + Windows path-separator assertion), 4 Localization B2-2 path-normalization tests (just landed today; Windows drive-prefix loss), 11 Run/JUnit tests (10 Windows OS-gate not handled by tests per decision `2026-06-03-junit-console-launcher-vendor.md` §R5 + 1 subprocess `UnicodeDecodeError` cp1252→utf-8 mismatch). **Chronic state since 2026-06-01**: 30+ consecutive red runs on every main-push since `53f7920` (cargo LCOV dispatch) / `4cb5d48` (typed metadata slot on NativeResult). Last GREEN: `26709211984` (2026-05-31). Fix surface is `src/novetest/{coverage,localization}/**` + `tests/{unit,integration}/{coverage,localization,run}/**` — all forbidden under Release team charter. Routed out to PM via sibling question. |
| 1.2 | PyApp binary build matrix (`release-test.yml`) | **✅ GREEN at HEAD** | Triggered fresh `workflow_dispatch` at start of this slice (run [`27176266868`](https://github.com/Nove-Lab/Nove-Test/actions/runs/27176266868) on HEAD `bd4d300`). All 3 cells built successfully: `linux-x86_64` 1m42s, `linux-aarch64` 1m22s, `macos-universal2` 2m51s (lipo-fused fat binary, both `aarch64-apple-darwin` + `x86_64-apple-darwin` slices). All 3 produced `.sha256` sidecars via `sha256sum` (Linux) / `shasum -a 256` (macOS) per the `Compute SHA-256 sidecar` step. Example: `linux-x86_64` SHA-256 = `d226d9dc0ba18d1aa7a80934f37023668089767291547f7083265e65c1b80c29` (captured live in the install-script-e2e verify log). Bin smoke test (`novetest --version --output json` + `novetest --help --output json`) returned valid `novetest/v1` envelopes on every cell. Compared to 5/16 closure (3m4s total): builds slightly faster now (likely caching warmup); no surprise from JUnit JAR vendoring (+2.7 MB) or numpy production dep added 2026-05-28. Action-major bumps from 5/21 (`checkout@v6`, `setup-uv@v7`, `upload-artifact@v7`, `download-artifact@v8`, `softprops/action-gh-release@v3`) are all honoured by the runtime; zero Node-20-deprecation warnings (compare 5/16 run which carried many). |
| 1.3 | install.sh end-to-end | **✅ GREEN at HEAD** | `install-script-e2e` job in run `27176266868` ran 15s on Ubuntu 24.04 runner against the freshly-built `linux-x86_64` binary. Clean install: `Installing novetest (linux-x86_64, dev) into /home/runner/work/_temp/novetest-install` → `SHA-256 verified (d226d9dc0ba18d1aa7a80934f37023668089767291547f7083265e65c1b80c29).` → `Installed: ...novetest` → `novetest --version --output json` returned `{"installedVersion": "0.0.0", "pythonVersion": "3.11.9", ...}` (PyApp first-run CPython download + wheel extract working — `3.11.9` matches the `PYAPP_PYTHON_VERSION: 3.11` env). Idempotent re-install: ran the same sequence a second time, both green. POSIX-sh compatibility (no bashisms, dash/ash/macOS-bash 3.2 verified per `scripts/install.sh` header). The Linux smoke is the only one the workflow runs end-to-end — macOS install.sh path is exercised by `tests/release/test_install_script.py` instead (runs as a separate `pytest (release smoke)` step on `macos-latest` × 3 Python versions in `ci.yml`, all 6 cells green). |
| 1.4 | Production / dev deps | **✅ PASS (1 minor finding)** | Production deps (`pyproject.toml [project] dependencies`): exactly 2 — `cyclopts>=3.0` (unchanged since Phase 0 inception) + `numpy>=1.26` (added 2026-05-28 in `bbb0356` for SBFL hot-path vectorization per Phase 4 entry). Both are pure Python; both are pulled by PyApp at first-run time via pip-install against the bundled wheel, NOT byte-bundled into the binary. No additions since 2026-05-28 (11 days). Dev deps: 7 total — `pytest>=8.0`, `pytest-asyncio>=0.23`, `syrupy>=4.6`, `mypy>=1.10`, `pytest-json-report>=1.5.0`, `pytest-cov>=5.0`, `coverage[toml]>=7.0`. The last 2 (`pytest-cov`, `coverage[toml]`) were added during the pytest-coverage-emission slice on 5/14; pinned at consistent minor-floor with charter guidance. **Minor finding (non-blocker)**: `numpy` is a sizable transitive (~15-30 MB wheel) that PyApp pulls at first-run; no functional regression observed in build smoke (`novetest --version` returned cleanly), but the first-run latency tradeoff documented in foundations §7 ("5-15s while CPython downloads") may now skew higher with numpy in the resolution set. Worth a follow-up cycle to measure if MVP user-experience care is warranted; not release-blocking. |
| 1.5 | THIRD_PARTY_NOTICES.txt | **🟡 PARTIAL (non-blocker)** | The mandate from `decisions/2026-06-03-junit-console-launcher-vendor.md` §3 is met: `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` exists, is shipped into the wheel via the `[tool.hatch.build.targets.wheel.force-include]` block in `pyproject.toml`, and covers the EPL-2.0 vendored JUnit Console Launcher JAR with: artifact coords (`org.junit.platform:junit-platform-console-standalone:1.11.4`), license name + URL (EPL-2.0 + `https://www.eclipse.org/legal/epl-2.0/`), source URL (`https://github.com/junit-team/junit5`), and a pinned SHA-256 `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`. **Verified empirically**: `sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar` returns the byte-identical hash. There is no root-level `/THIRD_PARTY_NOTICES.txt` — that's CORRECT per the decision (§3 specifies the vendored-dir location as canonical; the decision establishes the "vendored-asset pattern" of one NOTICES file per `_vendor/` directory). **What's missing (deferred per task non-blocker classification)**: `cyclopts` (Apache 2.0) + `numpy` (BSD-3-Clause) — both production deps but NOT byte-bundled into the binary (pip-fetched at first-run). Strict legal interpretation says binary-embedded blobs require attribution; pip-fetched deps don't (the user's pip-cache surfaces them). For an extra-careful v1, fold into a Tier-2 NOTICES surface in a polish cycle. **Also not done (Orchestration team territory)**: the `novetest --licenses` CLI surface mandated by decision §3 ("MUST surface this notice file's contents") is not yet wired. Not a Release-team file — flag for PM to route to Orchestration in a follow-up cycle. |
| 1.6 | Phase 0 unchecked DoD bullet re-check | **🔴 BULLET #1 STALE; others empirically green at HEAD** | `design/implementation-plan/delivery-phasing.md` Phase 0 §"Definition-of-done" lists 6 bullets; all show `[x]`. Empirical re-validation at HEAD `bd4d300`: **DoD #1** (`uv run pytest -q` green on 3 OSes × 3 Pythons) — **STALE**. Was checked 2026-05-16 against a 5/16 head commit; broke 2026-06-01 (8 days red on Windows since). PM call on un-tick / stale-marker — see question file for the 3 options. **DoD #2** (signed binary builds on `release-test`) — **GREEN at HEAD** per run `27176266868`. **DoD #3** (`curl-pipe-sh ... | sh` end-to-end on clean Linux/macOS) — **GREEN at HEAD** per `install-script-e2e` job (Linux verified live; macOS verified via `ci.yml`'s `pytest (release smoke)` step across 3 cells). **DoD #4** (SHA-256 verify + loud abort + tampered-binary integration test) — **GREEN at HEAD** per the install-script verify log (`SHA-256 verified` line) + `tests/release/test_install_script.py::test_install_aborts_loudly_when_sha256_mismatches` still in tree + last covered live on the 2026-05-16 closure pass; the test was hardened on 5/21 (commit `12cf04d`, `encoding="utf-8"` jest-charmap fix). **DoD #5** (`-v`/`-h` envelopes in a `.novetest/`-free dir) — not re-validated in this slice (Orchestration team territory; out of scope per task §"Out of scope"). **Net: 1 of 5 nominally-checked bullets is stale; PM owns the tick.** |

## Files / surfaces deliberately NOT touched, with justification

| File / surface | Why not touched | Where the work belongs |
|---|---|---|
| `src/novetest/coverage/**` (5 failing tests) | Release team `forbidden` directory per charter | Coverage team follow-up cycle |
| `src/novetest/localization/**` (4 failing tests, today's B2-2 work) | Release team `forbidden` directory per charter | Localization team follow-up cycle |
| `tests/unit/{coverage,localization,run}/**`, `tests/integration/{localization,run}/**` (all 20 failures) | Release team `forbidden` directory per charter ("you may add release-specific tests under `tests/release/` only") | Coverage / Localization / Run team follow-up cycles |
| `pyproject.toml` | No new deps needed; no version-bump warranted; the existing config is correct (`force-include` honoured by Hatchling; deps frozen since 5/28) | Not needed |
| `.github/workflows/**` | The workflows themselves are functioning correctly. `ci.yml` is correctly running all 9 cells and surfacing failures; `release-test.yml` is correctly producing binaries on HEAD. The chronic Windows red is a test-content defect, not a workflow defect. Touching `continue-on-error: true` on Windows cells would hide regressions, not fix them — PM would need to formally weaken the matrix contract (see DoD posture options in the question file) | Not needed unless PM rules option 3 (re-scope DoD) |
| `scripts/install.sh` | No defect surfaced. The install-script-e2e job ran 15s clean+idempotent on the freshly-built HEAD binary. SHA-256 verify, mktemp+trap-cleanup, rename(2) atomic install, idempotent upgrade path, PATH hint — all working | Not needed |
| `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` | Empirically validated: file exists at decision-mandated location, ships in wheel via `force-include`, SHA-256 in file matches JAR byte-for-byte (`b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`) | Not needed for MVP; polish cycle to expand for cyclopts/numpy as non-blocker (see §"Follow-up cycle candidates") |
| `tests/release/test_install_script.py` | Empirically green on Linux/macOS via `ci.yml` (skipped on Windows by `pytestmark` per pre-existing OS gate). Was hardened 5/21 with `encoding="utf-8"`. No regression observed | Not needed |
| `.claude/hooks/**` | No CI hooks need updating; pre-commit hook for WORKLOG continues to work (this handoff doesn't stage `src/` or `tests/`) | Not needed |
| `design/implementation-plan/foundations.md` §7 (Distribution) | The text accurately reflects the empirical state at HEAD; no edit needed. If PM rules "re-scope DoD #1 to Linux+macOS" (the third option in the question file), §7 would need an amendment, but that would be a PM-led doc cycle, not a Release-team commit | Not needed in this slice; PM-led if option 3 |

## Phase 2 (critical-path fix) — empirically performed in this slice

Per task §"Phase 2 — Critical-path fix (gap이 있다면)" — fix only the
blockers; non-blockers split into follow-up cycles.

The one blocker (Windows CI red) has fix surface entirely outside
Release team's writable scope. There is no Release-team file I can
edit that fixes it. Per charter §"During work":

> "If a dep change might affect engine behavior: write
> `agent-comms/questions/release-team-<date>-<slug>.md` for PM to route."

The same routing pattern applies to any release-blocker whose fix
surface is forbidden. Filed as
`agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md`
with: failure inventory by category (A–E), proposed fix shapes per
category, suggested cycle layout (parallel triple matching the B2
shape), and the three PM-call-options on Phase 0 DoD #1 bookkeeping.

Phase 2 thus completed by **routing rather than fixing** — which is
the charter-compliant action for this surface.

## Phase 3 (sign-off) — empirically performed in this slice

Per task §"Phase 3 — Sign-off" — establish empirical evidence at HEAD
for the release pipeline halves Release team CAN clear:

- **PyApp binary build matrix at HEAD `bd4d300`** — verified live via
  `release-test.yml` run [`27176266868`](https://github.com/Nove-Lab/Nove-Test/actions/runs/27176266868). All 3
  cells green. Artifacts uploaded: `novetest-linux-x86_64`,
  `novetest-linux-aarch64`, `novetest-macos-universal2`, each with
  `.sha256` sidecar.
- **install.sh end-to-end at HEAD** — same run, `install-script-e2e`
  job green: 15s round-trip; SHA-256 verified; clean install + idempotent
  re-install both returned valid `novetest/v1 --version` envelope; PyApp
  first-run CPython 3.11.9 download + wheel extract working.
- **Vendored JAR SHA-256 integrity** — `sha256sum` on local checkout
  matches the NOTICES file byte-for-byte
  (`b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`).

The sign-off statement is in §"Sign-off statement" above.

## DoD bullets believed closed by this slice

Per charter end-of-work convention ("DoD bullets believed closed" —
PM territory to actually tick).

This slice closes **none** of Phase 0's nominally-checked DoD bullets,
because all 5 already showed `[x]` (5/16 closure). It does however
**empirically re-validate 3 of those 5 against HEAD** (DoD #2, #3,
#4), and **surfaces #1 as stale**. PM action:

1. Decide DoD #1 bookkeeping (un-tick / stale-marker / re-scope; 3
   options laid out in question file).
2. Optionally annotate DoD #2, #3, #4 with a "re-validated at HEAD
   2026-06-08 against `bd4d300` via release-test.yml run
   `27176266868`" stale-marker. Cleaner audit-trail; not mandatory.

## Follow-up cycle candidates (PM queue)

Per task §"Follow-up cycle candidates" header in handoff.

### Blocker-clearing cycles (must land before MVP)

3 mutually disjoint cycles. Suggested PM grouping: a single parallel-triple
matching the 6/8 B2 UX-normalization shape. Sequential is also fine.

| # | Cycle | Team | Surface | Effort | Files touched |
|---|-------|------|---------|--------|---------------|
| 1 | `coverage-windows-parser-fixes` | Coverage | `src/novetest/coverage/cobertura_parser.py`, `src/novetest/coverage/derive_xunit.py`, `src/novetest/coverage/lcov_parser.py` (+ tests) | ~1-2 h | 3 src + 3 unit tests |
| 2 | `localization-windows-path-normalization-fix` | Localization | `src/novetest/localization/failure_proximity.py::_normalize_to_workspace_relative` (+ tests) | ~1 h | 1 src + 1 unit + 1 integration |
| 3 | `run-junit-windows-os-gate-test-fix` | Run | `tests/unit/run/{test_junit_readiness.py, adapters/test_junit_adapter.py}`, `tests/integration/run/test_junit_{gradle,maven,warnings}.py` | ~1-2 h | 0 src + 4 test files (test-only) |

§"Failure inventory" in the question file pins the fix shape per
category. Cycles 1+2 touch native adapter source; cycle 3 is test-only.
PM's brand-new (untracked-in-this-worktree) decision
`2026-06-08-equip-and-exercise-default-verification-posture.md` likely
interacts with §2.5 equip-and-exercise gating for these cycles — fold
in when shaping the briefs.

### Non-blocker polish cycles (post-MVP-acceptable)

| # | Cycle | Team | Surface | Why non-blocker |
|---|-------|------|---------|-----------------|
| 4 | `expand-third-party-notices-to-pip-deps` | Release | `src/novetest/run/adapters/_vendor/THIRD_PARTY_NOTICES.txt` OR a new sibling NOTICES surface | `cyclopts` + `numpy` pip-fetched at first-run, not byte-bundled in binary. Permissive licenses; attribution polish not strict legal requirement |
| 5 | `wire-novetest-licenses-cli` | Orchestration | `src/novetest/cli/**` to add `novetest --licenses` subcommand surfacing the `_vendor/THIRD_PARTY_NOTICES.txt` contents | Decision `2026-06-03-junit-console-launcher-vendor.md` §3 mandate; not enforced by any current test; polish for v1 |
| 6 | `pyapp-first-run-latency-bench-with-numpy` | Release | Measure `novetest --version` cold-start time post-numpy-add vs pre, document in foundations §7 (or amend the 5-15s figure) | UX, not correctness. Documentation can lag |
| 7 | `windows-install-ps1-and-binary-pipeline` | Release | `scripts/install.ps1`, `.github/workflows/release-test.yml` (add `windows-x86_64` cell) | OQ#16 (deferred per `delivery-phasing.md`). Foundations §7 explicitly says "Windows is a follow-up via parallel `install.ps1`; not a Phase 0 blocker" |

## Worklog entry text

```markdown
## 2026-06-09 — phase0-release-readiness / mvp-empirical-revalidation-and-routing

- Landed: MVP release-readiness assessment slice for HEAD `bd4d300`. Phase 1 assessment matrix covering 6 surfaces (CI matrix / PyApp binary / install.sh e2e / deps / NOTICES / Phase 0 DoD re-check). Phase 2 critical-path fix = ROUTING (single blocker has fix surface outside Release-team writable scope → filed `questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md` for PM disposition). Phase 3 empirical sign-off = `release-test.yml` run `27176266868` dispatched on HEAD, all 3 PyApp targets built clean (`linux-x86_64` 1m42s, `linux-aarch64` 1m22s, `macos-universal2` 2m51s) with `.sha256` sidecars, `install-script-e2e` job green in 15s (clean install + idempotent re-install both returned valid `novetest/v1 --version` envelope, SHA-256 verified live = `d226d9dc0ba18d1aa7a80934f37023668089767291547f7083265e65c1b80c29`). Sign-off: **NOT release-ready as of `bd4d300`** — blocker = CI matrix red on Windows × all 3 Python versions × 20 distinct test failures (chronic 8 days since `53f7920` cargo LCOV / `4cb5d48` typed metadata slot). Fix surface = Coverage (5 tests, cross-drive `Path.relative_to` ValueError + LCOV separator literal) + Localization (4 tests, today's B2-2 `_normalize_to_workspace_relative` drive-prefix loss) + Run (11 tests, 10 unhandled JUnit Windows-OS-gate per decision `2026-06-03-junit-console-launcher-vendor.md` §R5 + 1 subprocess `UnicodeDecodeError` jest-charmap class). No `src/`, no `tests/`, no `pyproject.toml`, no `.github/workflows/`, no `scripts/install.sh`, no `THIRD_PARTY_NOTICES.txt` touched (all charter-forbidden for the fix surface OR empirically defect-free). Three follow-up cycles proposed in handoff §"Follow-up cycle candidates" (Coverage Windows parser fixes / Localization Windows path normalization / Run JUnit Windows OS-gate test fix); suggested PM shape = parallel triple matching 6/8 B2 shape. Non-blocker polish cycles also enumerated (NOTICES expansion to pip deps; `novetest --licenses` CLI wire-in per Orchestration; first-run latency bench post-numpy; OQ#16 Windows install.ps1).
- Verified: `release-test.yml` run [27176266868](https://github.com/Nove-Lab/Nove-Test/actions/runs/27176266868) GREEN on HEAD `bd4d300` (3 binary cells + install-script-e2e + draft-release-skipped-by-design); `sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar` returns `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc` matching the in-file pin; `git log --follow ... pyproject.toml` confirms NO new production deps since `bbb0356` (2026-05-28 numpy add for SBFL); `gh api ... actions/jobs/80040568794/logs` confirmed the 20-test Windows failure inventory (5 Coverage / 4 Localization / 11 Run) reproduces identically on the latest CI run at HEAD; `gh run list --workflow ci.yml --limit 60` confirmed last GREEN `ci.yml` run was `26709211984` on 2026-05-31, first RED was `26711267224` on commit `d4ebafa` — 30+ consecutive red runs across 8 days.
- Left open: **DoD bullets believed closed (PM verifies + ticks)**: zero new bullets closed in this slice (all 5 Phase 0 bullets already showed `[x]` from 5/16). HOWEVER **3 of those 5 (DoD #2, #3, #4) empirically re-validated at HEAD** in this slice — PM may want a stale-marker on those rows. **DoD #1 surfaced as stale** — PM owns un-tick / stale-marker / re-scope (3 options laid out in question §"Phase 0 DoD #1 posture question"). **Forbidden-territory work routed via question** — 3 follow-up cycles (Coverage Windows + Localization Windows + Run JUnit Windows test gate) must land before MVP per the blocker classification.
- Gotcha: 3 pinned. (1) **Last green CI run was 8 days ago — chronic state, not recent regression**. Every push since `d4ebafa` (2026-06-01) carried Windows red. PM may want to introduce a "CI gate enforcement" decision so the next 8 days don't carry the same drift; otherwise teams routinely land slices that compound the Windows-red surface (the B2-2 Localization slice today added 4 more without anyone catching it). (2) **`continue-on-error: true` on Windows cells would HIDE regressions, not FIX them**. The chronic state is tempting to paper over by un-gating Windows, but that weakens DoD #1's contract without amending the doc. The right path is to fix the underlying defects (which are real cross-platform bugs that would hit real Windows users with `D:` drive setups) OR formally re-scope DoD #1. (3) **The just-landed B2-2 Localization slice (commit `51ea1b6` from today 2026-06-08) authored on a Linux host and never tested on Windows added 4 of the 20 failures**. The brief's §"Gotcha #2" explicitly noted "Path.resolve() deliberately NOT called on either side of the relative_to comparison ... a future cycle adds resolve() if Manual Test surfaces a real-host symlink scenario where the absolute-fallthrough confuses operators." That "future cycle" is the Localization Windows path normalization follow-up (cycle 2 in my §"Follow-up cycle candidates") — the operator surfacing it is Windows CI, not Manual Test. Slices authored on Linux without Windows pre-flight are the recurring defect class; addressable by either equip-and-exercise extending to Windows (PM's untracked 2026-06-08 decision likely covers this) OR by pre-merge `gh workflow run ci.yml` on the worktree branch.
- Next: Handoff at `agent-comms/handoffs/release-team-2026-06-08-mvp-release-readiness-assessment.md`. Sibling question at `agent-comms/questions/release-team-2026-06-08-ci-matrix-windows-red-blocks-mvp.md` routes the blocker out to PM. PM reads both, decides routing (parallel triple? sequential? hotfix?), dispatches the 3 follow-up cycles, decides DoD #1 bookkeeping (un-tick / stale-marker / re-scope). Once all 3 cycles land + CI matrix turns green, RELEASE TEAM RE-ACTIVATES for a Phase-3 sign-off pass (re-run release-test.yml on the post-fix HEAD; verify CI matrix all-green; declare MVP release-ready and update this handoff's sign-off statement). The non-blocker polish cycles (NOTICES expansion / `novetest --licenses` wire-in / first-run latency bench / Windows install.ps1 OQ#16) are PM-discretionary, post-MVP-acceptable.
```

(Above goes verbatim at the top of `WORKLOG.md` per the project's
"newest entry on top" convention. The PreToolUse `check-worklog-before-commit.sh`
hook only fires when staging `src/` or `tests/`; this slice stages
neither, so no hook gate. Appending anyway per charter §"At end of
work" narrative-value clause.)

## Reporting back (charter §"Reporting back")

- **Worktree**: `release/mvp-readiness-assessment` at
  `/home/yjshin/dev/aispace/novetest-mvp-release-readiness-assessment`,
  based on `main` head `bd4d300`. Self-contained; FF-mergeable.
- **Files**: 4 — this handoff, the question file, the WORKLOG entry, the
  regenerated `INDEX.md`. ZERO source / tests / config / workflow / install-script /
  NOTICES touched.
- **CI matrix result**: 6/9 green (Linux × 3 + macOS × 3), 3/9 red
  (Windows × 3) per `gh run list --workflow ci.yml --limit 1` at HEAD;
  20 distinct test failures per Windows cell.
- **install-script E2E result**: GREEN at HEAD via `release-test.yml`
  run `27176266868`'s `install-script-e2e` job; 15s round-trip; SHA-256
  verified live; clean + idempotent install both returned valid
  `novetest/v1 --version` envelope.
- **Release-pipeline surprises**: None. All 3 PyApp build cells +
  install-script-e2e ran clean on HEAD without retry, without
  intervention, without any pyapp/python-build-standalone quirk
  surfacing. The 5/16 closure's action-major-bump warnings (Node 20
  deprecation; `setup-uv@v3` unexpected `python-version` input) are
  fully resolved at HEAD — zero workflow annotations on the fresh run.
  The macOS-universal2 lipo-fuse path (added 5/15-16, exercises both
  `aarch64-apple-darwin` + `x86_64-apple-darwin` cross-compile +
  `lipo -create`) continues to work; binary size unmeasured here but no
  upload-artifact size warning surfaced. The JUnit JAR vendoring (~2.7 MB)
  is bundled into the wheel via Hatchling `force-include` and survives
  the PyApp wrap — verified by `novetest --version` returning a valid
  envelope (the JAR isn't exercised at version time, but the wheel
  resolution succeeded which means the JAR is reachable via
  `importlib.resources` once the JUnit adapter probes it).

## What this handoff explicitly says NO to

- Patching `continue-on-error: true` onto Windows cells. That would hide
  the regression class rather than surface it. PM owns whether to weaken
  the contract.
- Dropping Windows from the matrix. Same.
- Editing `src/novetest/{coverage,localization,run}/**` or `tests/{unit,integration}/**`
  to fix the 20 failures. Forbidden territory; engine teams' work.
- Bumping any production dep. The 2-dep production surface
  (`cyclopts`, `numpy`) is correct at HEAD.
- Adding `cyclopts` / `numpy` to `THIRD_PARTY_NOTICES.txt` in this
  slice. Non-blocker; post-MVP polish.
- Re-running `ci.yml` on this worktree branch. Would not help — branch
  is identical to main HEAD; the same 20 failures would reproduce.
- Pushing this worktree's branch to GitHub. Out of charter; Main Branch
  team merges via FF.
