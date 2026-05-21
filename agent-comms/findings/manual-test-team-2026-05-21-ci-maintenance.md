---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
created: 2026-05-21
slug: ci-maintenance
verifies: verifications/2026-05-21-ci-maintenance.md
verdict: passed
---

# Findings: CI maintenance — GHA action deprecations (Slice A)

## Verdict: passed

## What was tested (plain language for the CEO)

GitHub's hosted CI runners are retiring the older "Node 20" engine on
2026-06-02. Any GitHub Action still built on it would stop working. The
Release team bumped all of our CI workflow action references to their newer
"Node 24" versions ahead of that deadline. This change touches only CI
configuration files — no product code, no tests — so there is nothing to run
locally; verification is a static inspection of the two workflow files plus a
check that the CI test matrix was not accidentally altered.

Everything checks out. The two workflow files are syntactically valid, every
action is on the version the Release team declared as final, the test matrix
is still exactly the same 9 combinations, and the cross-platform jest test
gate was not weakened.

## Commands run + observed output

1. **YAML still parses** — both files load cleanly:
   ```
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
   → ci.yml OK exit=0
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"
   → release-test.yml OK exit=0
   ```

2. **Action pin inventory** — `grep -rnE 'uses:' .github/workflows/` confirms
   the live pin set exactly matches the verification request's "Final pin set":
   - `actions/checkout@v6` (ci.yml + release-test.yml)
   - `actions/setup-node@v6` (ci.yml)
   - `astral-sh/setup-uv@v7` (ci.yml + release-test.yml)
   - `actions/upload-artifact@v7` (release-test.yml)
   - `actions/download-artifact@v8` (release-test.yml, x2)
   - `softprops/action-gh-release@v3` (release-test.yml)
   - `dtolnay/rust-toolchain@stable` (composite — intentionally a `@stable`
     ref, no JS runtime, correctly unchanged)

3. **CI matrix unchanged** — `ci.yml` still declares
   `os: [ubuntu-latest, macos-latest, windows-latest]` x
   `python-version: ["3.11", "3.12", "3.13"]` = **exactly 9 cells**. No cell
   added or removed.

4. **jest gate not weakened** — the comment block at `ci.yml:44-50` confirms
   "Applied to all 9 matrix cells: jest is a real CI gate cross-OS" and that
   the historical `if: runner.os != 'Windows'` guard is not present. jest runs
   as a real gate on all 9 cells.

## Issues found

**None that affect the CI configuration.** One observation about the
*verification request's instructions* (not the merged change):

- **Verification step 2's grep is over-broad — produces a false positive.**
  The request says run `grep -rnE '@v[234]\b' .github/workflows/` and "Expect:
  no matches". In practice it returns 3 lines:
  - `ci.yml:78` and `release-test.yml:79` — comment prose mentioning the old
    `@v3` of setup-uv (historical explanation, not a pin).
  - `release-test.yml:276` — `softprops/action-gh-release@v3`, which **is the
    intended final pin** (the request's own "Final pin set" lists
    `action-gh-release@v3`).

  The regex `@v[234]` matches the legitimately-current `@v3`, so it can never
  return "no matches" while `action-gh-release` is correctly pinned. This is a
  defect in the verification *instruction*, not in the CI config. The actual
  intent — "no stale pins remain" — is satisfied: every action is on the
  major the Release team declared final.

## Recommendations for PM

- **Tick the CI-maintenance slice as verified-passed** for the locally-checkable
  scope. CI config is correct and complete.
- **Definitive signal still pending:** the post-merge GHA `test` workflow must
  show 9/9 cells green with zero deprecation warnings. Manual Test cannot
  observe GHA runs — PM (or whoever has CI access) should confirm the run for
  commit `57cdf0d`/`ec5c891` before fully closing.
- **Slice B follow-up:** the verification request notes the non-blocking
  `tests/perf` CI lane was deferred — `tests/perf/` is now on `main` (commit
  `5489c7e`), so PM can re-dispatch Slice B to the Release team.
- Minor: if future verification requests use a "no stale pins" grep, scope the
  regex to *below* the current major (e.g. exclude the known-good pins) so it
  cannot false-positive on a legitimately-current `@v3`.
