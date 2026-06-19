---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-06-19
slug: notices-pip-deps-and-perf-bench-bundle
parallel_cohort:
  - agent-comms/tasks/run-team-2026-06-19-v1-metadata-channel-sunset.md
  - agent-comms/tasks/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md
related:
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - design/implementation-plan/foundations.md
  - NOTICES.md
  - .github/workflows/release-test.yml
---

# Task: NOTICES pip-dep expansion + first-run latency bench + wheel-NOTICES probe (Release-bundle)

## Mission

Three Release-team polish items bundled into one cycle because they
all touch Release-owned territory and have zero file overlap with the
parallel Wave 1 slices. Bundling avoids running two Release worktrees
concurrently and gives the v0.1.2 publication cycle a clean, fully-
audited release-surface foundation.

The three items, all originating from
`agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`
§"Future-cycle queue":

1. **#2a** — Expand `NOTICES.md` with full attribution for the pip-managed
   runtime deps (`cyclopts` Apache 2.0, `numpy` BSD-3-Clause).
2. **#5** — Add a first-run latency bench job to `release-test.yml`
   that measures the PyApp binary's first-run cost (CPython download
   on first invocation) against the foundations.md §559 documented
   "5-15 s" budget.
3. **#8** — Codify the wheel-NOTICES probe (Manual Test Recommendation
   §6 from the MVP sign-off cycle) as a build-step assertion in
   `release-test.yml` confirming the wheel ships `NOTICES.md` per
   Apache 2.0 §4(d).

## Context

### #2a — Current NOTICES.md state

The current `NOTICES.md` (54 lines) already lists `cyclopts` and
`numpy` under "Runtime dependencies" with project URL + license name +
copyright line, plus the fallback sentence "The full text of each
license is reproduced in the installed package metadata (pip-managed
under `*.dist-info/`). Distribution of those metadata files satisfies
the respective attribution clauses."

This sentence is **technically sufficient** for Apache 2.0 §4(d) +
BSD-3-Clause clause 1 because pip ships the license text alongside the
wheel METADATA. The expansion that's missing — and that decision
`2026-06-03-junit-console-launcher-vendor.md` §3's `novetest --licenses`
CLI surface (the Wave 2 follow-up #2b) will need to consume — is the
**verbatim license text inlined into NOTICES.md** so a single file is
the canonical attribution surface, not a `*.dist-info/` scan.

Apache 2.0 §4(d) example (paraphrased): if You distribute the Work, You
must include a copy of the License in every place the Work is
distributed. Inlining is the safer interpretation; pointing at
`*.dist-info/` is a defensible weaker interpretation. The
`--licenses` CLI verb (Wave 2 #2b) will read from NOTICES.md as the
single source of truth.

### #5 — First-run latency context

`foundations.md §559`:
> "Tradeoff: first-run latency (5-15 s while CPython downloads).
> Acceptable for a CLI installed once. Document in README."

This refers to the PyApp binary's behavior on **first invocation** —
PyApp downloads python-build-standalone CPython at first run, caches
it under `~/.local/share/pyapp/...`, and reuses the cache on
subsequent runs. The "5-15 s" figure is from PyApp upstream documentation
+ ad-hoc local timing during Phase 0 build cycles; it has never been
empirically pinned in CI.

`numpy` was added as a runtime dep during Phase 4 Localization
(SBFL formulas need `numpy.typing.NDArray`); the wheel size grew
correspondingly. The "post-numpy" qualifier on this item means: confirm
the documented budget still holds with the post-Localization wheel
size, and capture the metric in CI for trend visibility.

### #8 — Wheel-NOTICES probe context

`agent-comms/history/2026-06-10-v0.1.0-license-and-tag-publication.md`
§"Out of scope per brief §'Out of scope', deliberately not done"
(via the 2026-06-10 v0.1.0 license cycle's Manual Test Recommendation
§6): "add `uv build --wheel && unzip -l dist/*.whl | grep NOTICES` to
a future Release verification surface, or codify as a distinct
integration test."

The current `release-test.yml::build` job runs `uv build --wheel` as
part of its PyApp wrap pipeline but does not assert that the resulting
wheel includes `NOTICES.md`. Hatchling's `pyproject.toml` config (see
`[tool.hatch.build]` + `[tool.hatch.build.targets.wheel]`) controls
this. The assertion is a 1-line `unzip -l` + `grep NOTICES` in a new
build step, OR — preferred — a distinct CI step that runs after the
wheel build and before the PyApp wrap.

## Scope

### Files to modify (3)

| File | Change | Item |
|---|---|---|
| `NOTICES.md` | Inline the verbatim Apache 2.0 license text (single copy at the bottom, referenced by both `cyclopts` and any future Apache-2.0 dep) + inline the verbatim BSD-3-Clause text customized with numpy's copyright. Restructure: keep the existing per-package summary blocks; remove the "pip-managed under *.dist-info/" disclaimer sentence (since the verbatim text is now inlined); add a "License texts" section at the bottom containing the two full license texts. Total file size grows from ~54 lines to ~280-320 lines depending on formatting. The Apache 2.0 verbatim text source: <https://www.apache.org/licenses/LICENSE-2.0.txt>. The BSD-3-Clause numpy text source: <https://github.com/numpy/numpy/blob/main/LICENSE.txt> (or the version pinned in the lockfile — use the released stable copy). | #2a |
| `.github/workflows/release-test.yml` | Two changes to the `build` matrix-job: (a) add a new step "Probe wheel NOTICES inclusion" between the `uv build --wheel` step and the PyApp wrap step; the step runs `unzip -l dist/*.whl \| grep -E "NOTICES.md\|NOTICES.txt"` and exits non-zero if no match (use bash `set -o pipefail`); applies to all 4 matrix cells. (b) Add a NEW job `first-run-latency-bench` (parallel to `install-script-e2e`, `install-ps1-e2e`) that runs on `ubuntu-latest` only (single-OS sufficient — PyApp's CPython download path is identical cross-OS modulo URL templating), needs the linux-x86_64 binary from `build`, performs a clean install (no warm PyApp cache), times the first `novetest --version` invocation via `time` (with `RUSAGE_SELF` capture if needed), then times a second invocation, logs both wall-clock values + the delta to stdout, and asserts the first-run wall is ≤ 25 s (give a comfortable margin over the 15 s documented upper bound; first-run download speed varies by GHA runner network). The job is added to `release.needs` to gate the draft release on the bench passing. | #5 + #8 |
| `design/implementation-plan/foundations.md` | Append a sentence to the §559 first-run-latency paragraph noting "Empirically pinned by CI bench on every release-test.yml run since 2026-06-19; current value: ~<X> s on ubuntu-latest GHA runners (CI log <run_id>)" — PM fills in `<X>` and `<run_id>` at cycle close from the actual bench output. This handoff just notes the placeholder location; Release team does NOT need to wait for the bench number before handing off. | #5 cycle-close polish |

### Files NOT to modify

- `src/novetest/**` — zero source-code touches. This is pure Release-territory polish.
- `tests/**` — zero test touches. The CI assertions are in the YAML, not in pytest.
- `pyproject.toml` — Hatchling's wheel-content config already includes `NOTICES.md` via the default `[tool.hatch.build.targets.wheel].include` settings; do not modify unless the probe step at DoD #4 reveals NOTICES.md is missing from the wheel (then `pyproject.toml::[tool.hatch.build.targets.wheel].include` would need to add `NOTICES.md` explicitly — surface to PM if encountered).
- `scripts/install.sh` / `scripts/install.ps1` — out of scope.
- README.md — the first-run latency observation already exists in README per the 2026-06-09 user-doc cycle; do not duplicate.
- Any decision file — these three items are operational follow-ups to existing decisions; no new policy needed.

## Definition of Done

1. **#2a**: `wc -l NOTICES.md` reports ≥ 280 lines (was 54); the Apache 2.0 LICENSE text is byte-identically present from "Apache License Version 2.0" through the final "limitations under the License." (use `diff <(curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt) <(awk '/Apache License/,/limitations under the License./' NOTICES.md)` returns empty); the BSD-3-Clause text is byte-identically present with numpy's exact copyright header.
2. **#2a**: The per-package summary blocks for `cyclopts` and `numpy` cross-reference the inlined license text via section anchors (e.g., "License text: [Apache License 2.0](#apache-license-20)" / "[BSD 3-Clause License](#bsd-3-clause-license)").
3. **#8**: `release-test.yml::build.steps` includes a "Probe wheel NOTICES inclusion" step that runs `unzip -l dist/*.whl | grep -E "NOTICES\\.(md|txt)"` and exits non-zero on no match. The step is positioned AFTER `uv build --wheel` and BEFORE the PyApp wrap step. Applies to all 4 matrix cells (linux-x86_64, linux-aarch64, macos-universal2, windows-x86_64).
4. **#5**: `release-test.yml` defines a new job `first-run-latency-bench` (or similar name) with: `needs: [build]`, `runs-on: ubuntu-latest`, steps that (a) download the linux-x86_64 PyApp binary from the build job's artifact upload, (b) execute `novetest --version` with clean PyApp cache + capture wall-clock, (c) execute `novetest --version` a second time with warm cache + capture wall-clock, (d) log both values + delta, (e) `exit 1` if first-run wall > 25 s. The `release` job's `needs:` array is extended to include `first-run-latency-bench`.
5. **CI evidence**: `gh workflow run release-test.yml --ref <branch>` triggered against the worktree branch returns 6/6 jobs green (4 build cells + install-script-e2e + install-ps1-e2e + first-run-latency-bench). CEO push gate may apply per 2026-06-18 cycle's gh-auth precedent — handoff documents whether the run is local-empirical or CEO-driven.
6. Handoff lists the bench's measured first-run wall-clock + delta values so PM can fill in the foundations.md §559 sentence at cycle-close.

## Verification posture

- **Host**: equipped (per `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md` §1 SHOULD tier — Release team non-adapter slice). Local validation = (a) `wc -l NOTICES.md` + visual diff against the upstream license texts; (b) `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"` parses without error; (c) optional: build the wheel locally via `uv build --wheel` + manually run `unzip -l dist/*.whl | grep NOTICES`.
- **CI matrix verdict criterion (per §4 amendment 2026-06-19)**: this slice modifies `.github/workflows/release-test.yml` which IS path/OS-sensitive per §4.1 #2 (touches `.github/workflows/`). The §4 MUST fires — handoff MUST cite a `release-test.yml` workflow_dispatch run + the `ci.yml` matrix run on the post-merge HEAD. The `ci.yml` matrix run is unchanged (this slice touches release-test.yml only, not ci.yml), so the citation is a sanity-check that ci.yml still green on merge HEAD.

## Out of scope

- **#2b** (`novetest --licenses` CLI verb) — Wave 2 follow-up; do NOT add the CLI verb in this cycle. The verb reads from NOTICES.md (this cycle's output) and lives in Orchestration territory.
- **THIRD_PARTY_NOTICES.txt** (vendored JAR, at `src/novetest/run/adapters/_vendor/`) — unchanged. The existing file at that path covers the JUnit Console Launcher EPL 2.0 attribution per decision 2026-06-03; do NOT modify or move it.
- **PyApp + python-build-standalone attribution** — already documented in NOTICES.md under "Install-time bootstrap"; do NOT expand inline since these are not embedded in the wheel itself (they're downloaded by the PyApp binary, attribution per the foundations.md install-matrix design).
- **Authenticode / codesigning** — out of scope (no cert provisioned, per 2026-06-18 Windows cycle).
- **NFR-COV-002 perf lane** in `ci.yml` — unchanged. The first-run latency bench is a DISTINCT job in `release-test.yml`, not an extension of the existing `ci.yml::perf` lane.
- **Wheel-version bump** — do NOT bump `pyproject.toml::version`. v0.1.2 publication is a separate Wave 3 cycle.

## Failure modes (anticipated)

1. **Wheel-NOTICES probe fails immediately**: if `unzip -l dist/*.whl | grep NOTICES` returns no match, Hatchling is not including NOTICES.md in the wheel. The fix is to add `NOTICES.md` to `pyproject.toml::[tool.hatch.build.targets.wheel].include` (or whatever Hatchling field controls the included files). This crosses into pyproject.toml territory — surface to PM via question file if encountered. The 2026-06-10 license cycle's history notes Hatchling embedded LICENSE at `*.dist-info/licenses/LICENSE` via PEP 639 — NOTICES.md is a regular file at repo root, may not be auto-included.
2. **First-run latency bench exceeds 25 s threshold**: GHA runner network variance is non-trivial. If the bench fails on one run but succeeds on a re-run, the threshold may need raising. Do NOT lower the threshold below 30 s without surfacing to PM — the foundations.md "5-15 s" budget is the contract. If the wall consistently exceeds 25 s, that's a regression signal, not a bench-tuning problem.
3. **GHA runner does NOT have a clean PyApp cache between job steps**: GHA runners are ephemeral but the `~/.local/share/pyapp/` may persist across steps in the same job (since both steps run on the same runner). Insert `rm -rf "$HOME/.local/share/pyapp/"` between the install step and the first `--version` invocation to guarantee a cold cache.
4. **`first-run-latency-bench` job permissions**: the new job needs to download the build artifact via `actions/download-artifact@v4` (or matching major). Use the same action version as `install-script-e2e` to keep the workflow file consistent.

## Procedural posture

- **Branch**: `release/notices-and-perf-bench-bundle` off `main` HEAD (currently `a2679a0`).
- **Worktree**: per Release team standard worktree root.
- **Handoff target**: Main Branch (standard worktree → FF-merge flow).
- **WORKLOG entry**: NOT required (this touches only `NOTICES.md` + `.github/workflows/` + `design/implementation-plan/foundations.md` — none of these are in `src/` or `tests/`, so the WORKLOG hook does not fire). Confirmed via CLAUDE.md → PM charter "post-flight checklist" rules.
- **Handoff file**: `agent-comms/handoffs/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md` with "DoD bullets believed closed" list per CLAUDE.md convention.

## Parallel cohort awareness

This slice runs in **Wave 1 parallel** with two other team cycles + 1 PM-internal task. File-footprint matrix:

| Slice | Owned area | Conflict with this slice? |
|---|---|---|
| Run: v1 metadata-channel sunset | `src/novetest/run/adapters/dotnet_adapter.py`, `tests/unit/run/adapters/test_dotnet_adapter.py` | None ✓ |
| Coverage: `workspace_relpath` utility promotion | `src/novetest/utils/`, `src/novetest/coverage/`, `src/novetest/localization/` | None ✓ |
| PM (no dispatch): CI verdict meta-decision amendment | `agent-comms/decisions/` (already merged in cycle dispatch commit) | None ✓ |

Standard FF-merge order is alphabetical-by-team (Coverage → Release → Run) per 2026-06-09 Windows-CI fix triple precedent.

## Estimated effort

~1 cycle. ~250 LOC NOTICES.md (mostly verbatim license text — copy from upstream URLs), ~80 LOC YAML (new bench job + probe step + needs-extension), ~3 LOC foundations.md placeholder. Single-author; no cross-team coordination needed.
