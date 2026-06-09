---
from: novetest-pm-team
to: all
type: history
created: 2026-06-09
slug: mvp-release-ready-positive-sign-off
cycle_window: 2026-06-09 (same-day flip — brief → handoff → merge → verification → findings)
related:
  - agent-comms/history/2026-06-09-mvp-release-readiness-assessment-with-windows-ci-blocker-surfaced.md
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - design/implementation-plan/foundations.md
  - design/implementation-plan/delivery-phasing.md
---

# MVP Release-Ready POSITIVE Sign-Off — Phase 0 closure milestone

## TL;DR

**MVP release-ready as of `8ae90cd`.** Same-day flip from yesterday's
NEGATIVE sign-off (`bd4d300`, gated by Windows × 3-Python chronic
red) to a POSITIVE sign-off, made possible by today's earlier
Windows-CI fix triple cycle (Coverage `4110645` + Localization
`edb78f8` + Run `a6ebd91` → `ci.yml` run `27187459586` 10/10 GREEN).
Pure empirical re-validation pass — zero `src/`, zero `tests/`, zero
`pyproject.toml`, zero `.github/workflows/`, zero `scripts/install.sh`,
zero `THIRD_PARTY_NOTICES.txt` touched. Comms-only cycle, single
Release-team slice, ~30 min wall time end-to-end.

**Manual Test verdict: PASSED — 8/8 scenarios + 8/8 critical edges.**
Sign-off structurally defensible.

**Delivery-phasing impact**: Phase 0 §"Definition-of-done" was already
7/7 `[x]` from yesterday's cycle-close commit; this slice empirically
re-validated 4 of the 7 (#1 ci matrix, #4 signed binary, #5
curl-pipe-sh, #6 SHA-256 verify+abort) at current HEAD. No new ticks
this cycle. **MVP scope is now structurally 100% complete in the
design-doc audit trail** (37/39 checkboxes `[x]`; the 2 `[ ]` are
explicitly post-MVP MCP integration).

## Cycle arc — same-day NEGATIVE → POSITIVE flip

| Time (UTC, 2026-06-09) | Event | Artifact |
|---|---|---|
| ~00:00 | First MVP release-readiness assessment cycle dispatched | `bd4d300` PM brief |
| ~00:39 | `release-test.yml` run `27176266868` on `bd4d300` GREEN | (anchor for yesterday's positive sub-claim) |
| ~05:00 | NEGATIVE sign-off filed: `release-test.yml` GREEN but `ci.yml` Windows × 3-Python chronic RED since 2026-06-01 (20 failures) | yesterday's history entry |
| ~05:30 | Windows-CI fix triple dispatched (Coverage + Localization + Run parallel) | 3 parallel briefs |
| ~06:11 | Windows-CI fix triple closure: `ci.yml` run `27187459586` on `871a278` 10/10 GREEN (first all-green matrix on `main` since 2026-05-31) | `a036815` cycle close |
| ~07:59 | `ci.yml` run `27192323843` on `8ae90cd` (Release re-dispatch brief commit) 10/10 GREEN | (anchor for today's sign-off bullet 1) |
| ~12:26 | `release-test.yml` run `27206024411` on `8ae90cd` GREEN (Release team's empirical re-trigger) | (anchor for today's sign-off bullet 2-4) |
| ~21:50 | Release team handoff filed: POSITIVE sign-off statement at `fee8c3d` | `fee8c3d` |
| ~21:55 | Main Branch merge + verification request at `b3af8ac` | `b3af8ac` |
| ~22:18 | Manual Test findings filed: PASSED 8/8 + 8/8 | (this cycle's findings) |
| ~22:30+ | PM cycle-close (this entry + transient cleanup) | (this commit) |

The "26-day Phase 0 close" arc (2026-05-14 inception → 2026-06-09
positive sign-off) collapses neatly into yesterday's negative-flag
intervention + today's parallel-triple fix + today's positive flip —
a 3-cycle resolution of a 9-day chronic Windows-CI red.

## Sign-off statement (binding, copied from merged handoff)

> **MVP release-ready as of `8ae90cd`.** All Phase 0 DoD bullets
> empirically green:
>
> 1. `uv run pytest -q` green on 3 OSes × 3 Python via `ci.yml` run
>    `27192323843` on `8ae90cd` — 10/10 jobs SUCCESS (9 matrix cells
>    + non-blocking `perf` lane). Backup citation: `27187459586` on
>    `871a278` (Windows-CI fix triple closure moment, also 10/10 GREEN).
> 2. Signed binary builds via `release-test.yml` run `27206024411`
>    on `8ae90cd` (re-dispatched 2026-06-09 12:26 UTC) — 3 PyApp
>    targets built + 3 `.sha256` sidecars.
> 3. `curl -fsSL <release_install_url> | sh` end-to-end green —
>    `install-script-e2e` job on the same run, clean install +
>    idempotent re-install both returning a valid `novetest/v1
>    --version` envelope.
> 4. SHA-256 verify + tampered-binary abort test green — the
>    `pytest (release smoke)` step on `ci.yml` run `27192323843`
>    (Linux + macOS cells; Windows skipped per pytestmark, OQ#16
>    post-MVP) exercises `test_install_succeeds_when_sha256_matches`
>    + `test_install_aborts_loudly_when_sha256_mismatches`.
> 5. `novetest -v` and `novetest -h` envelopes structurally correct
>    — see footnote §1 below for the corrected citation surface.
>
> Vendored JUnit Console Launcher EPL 2.0 attribution per decision
> `2026-06-03-junit-console-launcher-vendor.md` §3 byte-identically
> valid: `sha256sum src/novetest/run/adapters/_vendor/junit-platform-console-standalone-1.11.4.jar`
> = `b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc`
> matches the pinned NOTICES SHA-256.

## Footnote §1 — Sign-off bullet 5 citation drift (Manual Test Obs §1)

Manual Test flagged a citation drift in the merged handoff bullet 5:

- **What the handoff says** (line 49-56 of the merged file):
  > "the test gate IS the snapshot equality check on `version_envelope`
  > + `help_envelope`" via `tests/integration/cli/test_envelope_snapshots.py`
- **What actually exists at the merged tip**:
  - `tests/integration/cli/test_help_envelope_no_store.py` — 3 tests
    including `test_help_envelope_snapshot` (syrupy, covers
    `help_envelope`)
  - `tests/integration/cli/test_version_envelope_no_store.py` — 3
    tests, all **direct-assertion** style on `--version` envelope
    shape (**no syrupy snapshot for `version_envelope`**)
  - `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`
    — the lone syrupy snapshot, covering `help_envelope` only

**Why this is documentation drift, not a regression**: DoD #7 reads
"`novetest -v` and `novetest -h` return their structured envelopes
in a directory tree that contains no `.novetest/` anywhere in the
ancestor chain." Both envelopes ARE exercised on every matrix cell
of `ci.yml` run `27192323843` (10/10 GREEN); the surface mechanism
is asymmetric (syrupy snapshot for `help`, direct assertion for
`version`) but the DoD bullet is met empirically. The sign-off's
factual claim ("both envelopes structurally correct on every matrix
cell") holds; the citation just points to the wrong filename and
overstates the snapshot mechanism for `version_envelope`.

**Disposition**: footnote here (Manual Test Recommendation §1 option
b). Preserves the handoff verbatim (sign-off-as-deliverable framing),
creates a permanent audit-trail breadcrumb, incurs zero process
irregularity (handoffs are normally retired untouched).

## Load-bearing learnings (for future agents)

### L1 — Same-day NEGATIVE → POSITIVE flip pattern is viable comms shape

The "deliverable IS the sign-off" framing (yesterday's negative
findings doc, today's Release brief, today's Release handoff)
enables collapsing a multi-day re-validation arc into a single
~30-minute comms-only cycle whenever the blocker fix lands the same
day. The shape is reproducible:

1. PM dispatches a Release brief for "empirical re-validation pass"
   immediately after a blocker-fix cycle closes.
2. Release runs `gh workflow run release-test.yml --ref main` +
   re-queries `ci.yml` + checks vendored-artifact SHA-256 sums.
3. Release handoff carries the literal sign-off statement (bound to
   the current HEAD SHA) + 4-task validation evidence.
4. Manual Test verifies sign-off **integrity** (not product-state —
   the sign-off IS the product-state claim, Manual Test just checks
   it's structurally defensible).
5. PM cycle-close with footnote for any citation drifts.

Total wall time from blocker-fix close → POSITIVE sign-off close:
**~16 hours** (06:11 UTC Windows-CI fix triple close → 22:30 UTC PM
cycle-close), of which ~1 hour was active Release team execution
(brief written at 20:51 UTC; handoff filed at 21:50 UTC; ~1 hour
active work + workflow_dispatch wait time).

### L2 — Citation hygiene: handoff file paths SHOULD be verified before authoring

Manual Test surfaced two related drifts in the sign-off chain:
1. **Sign-off bullet 5** cites a non-existent file path
   (`tests/integration/cli/test_envelope_snapshots.py`) and overstates
   syrupy coverage.
2. **Verification doc Scenario E** mirrored the same wrong path
   verbatim from the source handoff (Main Branch authored without
   re-verifying file existence).

The drift was caught only at the Manual Test step (3rd-line of
defense). Future authoring convention (Manual Test Recommendation §2):

> Authors of handoffs / verification docs / cycle briefs SHOULD `ls`
> or `grep` any file paths / test class names cited from upstream
> sources before mirroring them. If the path doesn't resolve, flag
> the discrepancy rather than mirroring verbatim.

This is **not codified as a binding decision** (no
`agent-comms/decisions/` entry filed for this) — the cost of the
drift was zero (sign-off PASS regardless; just a documentation
footnote), and a SHOULD-tier guidance in history is sufficient.
If a future cycle hits a higher-cost citation drift (e.g., wrong
workflow run number, wrong commit SHA), PM may escalate to a
formal decision.

### L3 — MVP scope structurally 100% complete

This sign-off is the **closing bracket of Phase 0** — the last DoD
bullet (or rather, the empirical re-validation that the 7
already-`[x]` bullets are all still green at current HEAD).
`delivery-phasing.md` checkbox arithmetic at HEAD:

- **37 / 39** = `[x]`
- **2 / 39** = `[ ]` — both post-MVP MCP integration:
  - "An MCP-aware agent can invoke each tool and consume the JSON
    envelope identical to what the CLI emits."
  - "Snapshot tests cover at least one MCP tool round-trip per
    sub-product."

The 2 unchecked are **deliberately deferred to post-MVP** per
`delivery-phasing.md` Phase 7 (MCP transport, post-MVP).

**Structurally**, every MVP-scoped phase (0, 1, 2, 2.5, 3, 4, 5, 6)
is closed in the design-doc audit trail. The product is
release-ready — only operational steps (tag publication + GitHub
Releases upload) remain before user-visible release.

## DoD impact

**Zero new bullets ticked this cycle.** Per Release handoff §"DoD
bullets believed closed": "**No new DoD bullets are claimed-closed
by this slice.** The 7 bullets were already `[x]` from yesterday's
cycle-close commit." This slice's structural achievement is
**empirical re-validation of the release pipeline at current HEAD**
+ **sign-off statement flip** — the cycle's deliverable IS the
positive sign-off, not new code or DoD progression.

The 4 bullets empirically re-validated by this slice (already `[x]`,
re-confirmed green at `8ae90cd`):
- #1 `pytest -q` green on 3 OSes × 3 Python (via `27192323843`)
- #4 signed binary builds (via `27206024411`)
- #5 curl-pipe-sh end-to-end (via `27206024411::install-script-e2e`)
- #6 install script SHA-256 verify + tampered abort (via `27192323843`
  Linux+macOS cells)

The 3 transitively-green bullets (covered by same `ci.yml` matrix run):
- #2 `--output json --help` envelope (CLI contract tests)
- #3 `test --help` exit-0 + stub-exit-2 (CLI contract tests)
- #7 `-v`/`-h` envelopes (env tests; see footnote §1 for surface
  detail)

## Future-cycle queue (carried forward from handoff §"Future-cycle hooks")

PM-acknowledged backlog (not auto-queued; CEO sequences):

1. **Release tag `v0.1.0` publication** + GitHub Releases artifact
   upload cycle — separate CEO command. This is the actual user-
   visible release, distinct from "release-ready" status that this
   cycle just achieved. Expected ~10 min wall time; PM brief filed
   when CEO opens the release-publication cycle.
2. **THIRD_PARTY_NOTICES pip-dep expansion** (`cyclopts` Apache 2.0
   + `numpy` BSD-3-Clause) + **`novetest --licenses` CLI surface**
   (decision `2026-06-03-junit-console-launcher-vendor.md` §3
   mandate). Post-MVP polish; Release team + Orchestration team.
3. **v1 metadata-channel sunset** — post-MVP cleanup per
   `2026-06-06-adapter-warning-surface-v1-metadata-channel.md`.
4. **Windows install.ps1 + binary pipeline** (Open Q #16) — post-MVP
   per `foundations.md` §7. Release team.
5. **First-run latency bench post-`numpy`** — perf NFR follow-up.
   Release team.
6. **`src/novetest/utils/path_utils.py::workspace_relpath` utility**
   — centralize scenario A pattern across Coverage + Localization
   (per `2026-06-09-windows-ci-fix-triple-coverage-localization-run.md`
   PM disposition #3). Cross-team cleanup.
7. **Meta-decision amendment for CI matrix verdict criterion** —
   fold into `2026-06-08-equip-and-exercise-default-verification-
   posture.md` as explicit clause (per Windows-CI fix triple history
   PM disposition #2).
8. **(Optional) Wheel-NOTICES probe codification** (Manual Test
   Recommendation §6) — add `uv build --wheel && unzip -l dist/*.whl
   | grep NOTICES` to a future Release verification surface, or
   codify as a distinct integration test. Low priority.

### Addendum — items surfaced post-cycle during user-doc work (2026-06-09 evening)

Two additional candidates surfaced during the `design/user-doc/`
authoring session that ran after this cycle closed (commits
`271417a` → `4fb4e2e`). Recorded here so the canonical Future-cycle
queue is the single source of truth:

9. **Human-readable text renderer** — `src/novetest/cli/output.py`
   currently emits pretty-printed JSON for `OutputMode.TEXT` (same
   payload as `JSON` mode, only `indent=2`). The `foundations.md`
   §"Output Modes" design intent ("AI agents will set
   `NOVETEST_OUTPUT=json`; humans get pretty output by default")
   implies a true human-rendered surface (tables, color, a single
   "3/3 passed" summary line per verb) that is currently absent.
   Scope: per-verb renderers under `src/novetest/cli/handlers/` or
   a sibling `cli/renderers/` module, plus a feature-detection
   matrix for ANSI/TTY. Orchestration team territory.
   Estimated effort: 1-2 cycles. Surfaced 2026-06-09 during
   user-doc commit `2d5a0af`; mentioned in `install.md §2`,
   `advanced-cli-memo.md §"Output format override"`, and
   `README.md §"One MVP product gap worth knowing about up front"`
   as a known post-MVP polish item.
10. **(Optional) Workspace-level orchestrator (`novetest workspaces
    test`)** — a Bazel/Nx/Turborepo-style convenience wrapper for
    polyglot monorepos. Walks down from CWD to find every
    `.novetest/` subdirectory, executes `novetest test` in each as
    a subprocess, aggregates exit codes and emits a meta-envelope
    wrapping per-workspace results. Design A from the polyglot
    discussion in `languages.md §"Working with a polyglot
    repository"`; zero schema changes anywhere (each per-workspace
    `.novetest/` keeps its single-engine assumption intact).
    Orchestration team territory; estimated 1-2 weeks; sequence
    after v0.1.0 if user feedback surfaces polyglot UX requests.
    Surfaced 2026-06-09 during user-doc commit `4fb4e2e`;
    reasoning lives in `languages.md` polyglot section.

## Cycle transcript (commits)

- `bd4d300` — PM brief: MVP release readiness assessment (2026-06-08
  evening; yesterday's cycle inception)
- `91ef953` — Release: MVP release-readiness assessment + Windows-CI
  blocker routing (NEGATIVE sign-off)
- `486c1df` — verification (mvp release-readiness assessment)
- `230420c` — close release-readiness assessment + dispatch Windows
  CI fix triple
- `4110645` / `edb78f8` / `a6ebd91` — Windows-CI fix triple slices
- `c9af08c` / `c1424bd` / `871a278` — Windows-CI fix triple
  verifications
- `a036815` — close Windows CI fix triple cycle (10/10 ci.yml GREEN)
- `8ae90cd` — PM brief: Release re-dispatch — MVP release-ready
  POSITIVE sign-off (this cycle inception)
- `fee8c3d` — Release handoff: POSITIVE sign-off at `8ae90cd`
- `b3af8ac` — verification (release MVP release-ready POSITIVE
  sign-off at `fee8c3d`)
- `<this commit>` — PM cycle-close (this entry + transient cleanup)

## Closure

The cycle deliverable is captured. MVP release-ready status is
**officially achieved** as of `8ae90cd`. The product passes every
Phase 0 binding gate empirically at current HEAD; the only remaining
work to put a user-visible release artifact into the world is the
operational release-tag publication cycle (Future-cycle queue #1),
which is a separate CEO command.
