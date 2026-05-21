---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
created: 2026-05-21
slug: ci-maintenance
source-handoffs:
  - handoffs/release-team-2026-05-21-ci-maintenance.md
---

# Verification: CI maintenance — GHA action deprecations (Slice A)

## Merged commits

- `57cdf0d` — `ci: bump GHA actions to Node 24 runtime majors`
- `ed0992b` — `comms: handoff for release-team ci-maintenance (Slice A)`
- Rebased onto `main` then merged fast-forward. No conflict.

## Source handoff consumed

- `handoffs/release-team-2026-05-21-ci-maintenance.md` (Release team, status
  `ready-to-merge`).

## What changed

GitHub Actions `uses:` pins bumped to Node-24-runtime majors ahead of the
2026-06-02 Node 20 runtime retirement. CI-config only — no `src/`, no
`tests/`, no `pyproject.toml`.

- `.github/workflows/ci.yml` — 3 `uses:` pins bumped + a clarifying comment.
- `.github/workflows/release-test.yml` — 5 `uses:` pins bumped + a comment.

Final pin set: `checkout@v6`, `setup-node@v6`, `setup-uv@v7`,
`upload-artifact@v7`, `download-artifact@v8`, `action-gh-release@v3`,
`rust-toolchain@stable` (composite — unchanged, no JS runtime).

The `setup-uv@v3 -> @v7` bump also clears the `Unexpected input(s)
'python-version'` warning (`python-version` input did not exist before
`setup-uv@v4`).

## Verification steps for Manual Test

This slice has **no locally-runnable behaviour** — it changes only CI
workflow metadata. Verification is by static check + post-merge CI
observation.

1. YAML still parses (any OS):
   ```
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"
   ```
   Expect: no output / exit 0 for both.

2. No stale action pins remain:
   ```
   grep -rnE '@v[234]\b' .github/workflows/
   ```
   Expect: no matches (every JS action is now on its Node-24 major;
   `rust-toolchain@stable` is a composite action and is intentionally a
   `@stable` ref, not a `@vN` pin).

3. **Definitive signal — post-merge GHA `test` workflow:** expect
   **9/9 `test` cells green** (3 OS x 3 Python, matrix unchanged) and
   **zero deprecation warnings** in any cell's log. jest must still run as
   a real gate on all 9 cells — no `runner.os != 'Windows'` guard was
   reintroduced.

## Critical edge cases worth probing

- `release-test.yml` only runs on tag push / `workflow_dispatch`; its pins
  are statically verified here and will be exercised at the next release
  trigger — not by the post-merge `test` run.
- Confirm the CI matrix is still exactly 9 cells — no cell added or removed
  by this bump.

## Notes from the merge

- Clean rebase + fast-forward, no conflict.
- **Slice B deferred (PM action):** the non-blocking `tests/perf` CI lane
  was *not* shipped — at the time the Release task ran, `tests/perf/` was
  not yet on `main`. It now is (merged commit `5489c7e`, see
  `verifications/2026-05-21-coverage-compare-perf.md`), so PM can
  re-dispatch Slice B as a follow-up. This is a PM tracking item, not a
  Manual Test verification item.
