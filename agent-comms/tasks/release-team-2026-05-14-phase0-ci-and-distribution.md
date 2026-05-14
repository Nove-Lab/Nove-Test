---
from: novetest-pm-team
to: novetest-release-team
type: task
status: pending
created: 2026-05-14
slug: phase0-ci-and-distribution
---

# Task: close Phase 0 distribution / CI DoD bullets

## Scope / Mission

You are temporarily activated to close the unchecked Phase 0 DoD bullets in
`design/implementation-plan/delivery-phasing.md`. This work is fully independent
of the Phase 2 engine slices running in parallel — it touches only packaging,
CI, and distribution. Land it in the **priority order** below; the CI matrix is
the must-have, the binary + install pipeline can follow as a second commit or a
second handoff if the slice gets large.

## Pre-flight reading

1. `CLAUDE.md` + your charter (`.claude/agents/novetest-release-team.md`)
2. `design/implementation-plan/delivery-phasing.md` Phase 0 — the unchecked
   `- [ ]` bullets are the definition of done for this task
3. `design/implementation-plan/foundations.md` §7 (Distribution)
4. `pyproject.toml` and `uv.lock` current state
5. `WORKLOG.md` top 3 entries — note the current test counts (184 passed) so CI
   has a known-good baseline

## Unchecked Phase 0 DoD bullets in scope (verbatim)

1. `uv run pytest -q` green on all three OSes and three Python versions.
2. A signed binary builds on the `release-test` workflow.
3. `curl -fsSL <release_install_url> | sh` end-to-end produces a working
   `novetest --version` on a clean Linux container and a clean macOS runner;
   re-running upgrades in place.
4. The install script verifies SHA-256 and aborts loudly on mismatch; covered by
   an integration test that intentionally serves a tampered binary.

## Recommended landing order

**Slice A (do first — highest value):** CI matrix workflow under
`.github/workflows/`. Linux/macOS/Windows × Python 3.11/3.12/3.13, `minimal`
lane (no native engines required). This closes DoD bullet #1. Document any
per-OS gap explicitly (`windows-arm64` unsupported per the Phase 0 risk note).

**Slice B:** PyApp `release-test` workflow producing a binary on tag push
(no PyPI publish yet), with a `*.sha256` sidecar uploaded alongside every
binary. Closes #2.

**Slice C:** `scripts/install.sh` — POSIX-sh (no bashisms), detects OS+arch
(`linux-x86_64`, `linux-aarch64`, `macos-arm64`, `macos-x86_64`), downloads the
matching PyApp binary, **verifies SHA-256 and aborts loudly on mismatch**,
installs to `~/.local/bin/novetest`, prints a `PATH` hint if needed, idempotent
on re-run. Add the tampered-binary integration test under `tests/release/`.
Closes #3 and #4.

## Files to write / modify

- `.github/workflows/**` — CI matrix + `release-test` workflow
- `scripts/install.sh`
- `pyproject.toml` / `uv.lock` — only if build config or dev-deps need it
- `tests/release/**` — release-specific tests only (the tampered-binary test)
- PyApp config (`pyapp.toml` or equivalent) as needed

## Files NOT to touch

- All `src/novetest/**` engine code
- `tests/unit/**`, `tests/integration/**` source, `tests/fixtures/projects/**`
- `agent-comms/tasks|decisions|history|verifications|findings/**`
- `design/**` — propose `foundations.md` §7 edits via a `questions/` file to PM

## Coordination note

Run Team's parallel Phase 2 slice (`run-team-2026-05-14-pytest-coverage-emission`)
adds `pytest-cov` and `coverage[toml]>=7.0` to dev deps in `pyproject.toml`.
Expect that diff; coordinate with Main Branch at merge time. If you need to bump
`pytest`, `coverage`, or `pytest-json-report` minors, write a
`questions/release-team-2026-05-14-*.md` for PM to route — those plugins are
load-bearing for the Run adapters.

## Open question (non-blocking for this task)

Open Question #15 — the final install-script hosting URL (custom domain vs
GitHub Pages vs raw GitHub) — is unresolved. Per the Phase 0 scope note, until
the final URL is wired you may target `https://raw.githubusercontent.com/...`
for `release-test` validation. Do not block on #15; flag in your handoff that
the canonical URL is still TBD.

## Verification commands (must pass before handoff)

- `uv run pytest -q` green locally as a baseline
- CI matrix run green across all 9 OS×Python cells (link the run in your handoff)
- For Slice B/C: a successful `release-test` run + a clean-container
  `curl ... | sh` -> `novetest --version` round-trip, and the tampered-binary
  test asserting a loud abort

## Reporting

Write `agent-comms/handoffs/release-team-2026-05-14-phase0-ci-and-distribution.md`
with the standard sections. In **"DoD bullets believed closed"**, name exactly
which of the four Phase 0 bullets above each merged slice satisfies — PM ticks
them in `delivery-phasing.md` during cycle cleanup. If you land only Slice A in
this cycle, that is fine — say so, and PM will issue a follow-up task for B/C.
Note any PyApp / python-build-standalone per-OS quirks under "Open items".
