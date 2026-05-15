---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-15
slug: phase0-release-and-phase2-coverage-foundation
related:
  - handoffs/release-team-2026-05-15-phase0-ci-and-distribution.md
  - handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md
---

# Verification request: Phase 0 release tooling + Phase 2 coverage engine foundation

Two slices landed in this merge pass on `main`. They are independent and can be
verified in either order.

## Merged commits

- `74a6ce4` — `release: ship Phase 0 CI matrix, PyApp release pipeline, and install.sh`
- `dee3252` — `feat(coverage): add Phase 2 engine foundation — CoverageFactSet + 4 interfaces`

Both fast-forwarded onto `fe28479` (previous `main`). Linear history, no merge commits.

Source handoffs consumed:

- `agent-comms/handoffs/release-team-2026-05-15-phase0-ci-and-distribution.md`
- `agent-comms/handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md`

## Test gate (run by Main Branch after each merge)

| Step | Command | Result |
| --- | --- | --- |
| Baseline on `fe28479` | `uv run pytest -q tests/unit tests/integration` | 185 passed |
| After Release merge (`74a6ce4`) | same | 185 passed (release tests are out of default `testpaths`) |
| After Release merge | `uv run mypy` | clean — 41 source files |
| After Coverage merge (`dee3252`) | same pytest | **256 passed** (+71 from Coverage; +1 snapshot) |
| After Coverage merge | `uv run mypy` | clean — 49 source files |

## Conflict resolution notes

Only one conflict was hit during the merge sequence: `WORKLOG.md` at the
rebase of `worktree-phase2-coverage-foundation` onto the post-Release `main`.
Both branches wanted to be the newest entry. Resolved surgically by stacking
both entries (Coverage on top as the more recently landed slice, Release
immediately below). Both entry bodies are byte-identical to the originals;
only the position/separator changed.

No source code conflicts. `agent-comms/INDEX.md` auto-merged identically
(both branches bumped `Last regenerated` to 2026-05-15).

## What to verify

### Slice 1 — Phase 0 release tooling

This slice is heavy on CI/distribution plumbing that can only be fully
exercised on real GitHub Actions. Locally Manual Test can:

1. **`tests/release/test_install_script.py` against the in-tree script.**
   ```
   uv run pytest -q tests/release
   ```
   Expect: 3 passed (happy path, idempotent re-run, tampered-binary loud abort).
   This is NOT part of default `pytest -q` — `tests/release/` is intentionally
   out of `[tool.pytest.ini_options].testpaths` (so the baseline stays at 185).

2. **`scripts/install.sh` end-to-end smoke under POSIX sh.**
   Spin up a localhost HTTP server, point the script at a fake binary + sha256
   sidecar, install into a temp PREFIX, then re-run to confirm idempotence.
   Recommended one-liner:
   ```
   mkdir -p /tmp/nove-install-smoke && cd /tmp/nove-install-smoke
   echo "stub" > novetest-linux-x86_64
   sha256sum novetest-linux-x86_64 | awk '{print $1}' > novetest-linux-x86_64.sha256
   python3 -m http.server 9876 &
   NOVETEST_INSTALL_BASE_URL="http://127.0.0.1:9876" NOVETEST_INSTALL_PREFIX="$PWD/prefix" \
     dash /home/yjshin/dev/aispace/Nove-Test/scripts/install.sh
   kill %1
   ls -la prefix/   # should contain novetest, executable
   ```
   Expect: script downloads, verifies SHA-256, installs atomically, emits a
   PATH hint, exit 0.

3. **Tampered-binary path (the loud-abort guarantee).** Same setup, but
   corrupt the sidecar after generating it:
   ```
   echo "0000000000000000000000000000000000000000000000000000000000000000" > novetest-linux-x86_64.sha256
   ```
   Expect: script exits non-zero, stderr contains `SHA-256 MISMATCH` and
   surfaces both digests, and **nothing is written to the PREFIX directory**.

4. **YAML sanity-check on the two workflow files** (cannot run them; can
   confirm they parse):
   ```
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-test.yml'))"
   ```
   Expect: no exception.

What you CANNOT verify locally and should NOT be marked closed by Manual
Test: the 9-cell CI matrix actually green on real GHA runners, the PyApp
wrap actually producing a working binary per target, and the
`install-script-e2e` job round-tripping against the real PyApp-wrapped
binary. Those are CEO/PM concerns once the merge is pushed and the
release-test workflow is triggered.

### Slice 2 — Phase 2 coverage engine foundation

This slice adds the Coverage engine library — entity model, parser,
persistence, derive, retrieval, compare, availability. **No CLI surface
yet**; everything is Python-API. The user-visible side effects therefore
need driver code. Verify:

1. **Test suite shape & count.**
   ```
   uv run pytest -q tests/unit/coverage tests/unit/models/test_coverage_fact_set.py
   ```
   Expect: 71 passed (17 model + 54 engine). All under one second on a
   modest laptop.

2. **mypy on the new modules.**
   ```
   uv run mypy
   ```
   Expect: clean — 49 source files under `--strict`.

3. **Public surface smoke.** From the repo root:
   ```
   uv run python -c "from novetest.coverage import derive_coverage_facts, get_coverage_facts, compare_coverage_facts, check_coverage_availability; from novetest.models import CoverageFactSet, CoverageSummary, FileCoverage; print('imports OK')"
   ```
   Expect: prints `imports OK`, exits 0.

4. **Parser round-trip on the checked-in fixture.** Drop the following into
   a temporary Python script and run with `uv run python <script>`:
   ```python
   import json
   from pathlib import Path
   from novetest.coverage.parser import parse_coverage_json
   payload = json.loads(
       Path("tests/unit/coverage/fixtures/sample_coverage.json").read_text()
   )
   facts = parse_coverage_json(payload, engine_name="pytest", ecosystem="python", run_reference=None)
   print(facts.mapping_granularity, facts.summary.percent_covered, len(facts.files))
   ```
   Expect: `per-test`, a non-zero float, 2.
   (Adjust the `run_reference=None` if the signature requires a positional
   `RunReference`; the parser's exact contract is the source of truth.)

5. **Availability lockstep against Memory's flag.** This is the
   charter-mandated invariant — covered by
   `tests/unit/coverage/test_availability.py::test_availability_agrees_with_memorys_has_coverage_facts_flag`,
   but worth eye-balling: when `coverage_facts.json` exists under
   `<store>/coverage/facts/run_<id>/`, `check_coverage_availability(...)`
   must report `facts_persisted=True` AND Memory's
   `get_memory_entry_availability(...)` must report `has_coverage_facts=True`.
   When the file is absent, both must report `False`.

## Critical edge cases to probe

- **Install script: PATH hint suppression when PREFIX is already on PATH.**
  Re-run install.sh with `PATH="$PREFIX:$PATH"` exported and confirm the
  PATH-hint stanza is NOT emitted. Conversely, with a fresh PREFIX not on
  PATH, it MUST be emitted.
- **Install script under `dash`, not just `bash`.** Run the script under
  `/usr/bin/dash` to exercise the POSIX-only paths (`${var+x}`,
  `case ":${PATH}:" in *":${PREFIX}:"*`, no `[[`). Release team verified
  this; spot-check it.
- **Coverage parser permissiveness.** Strip each top-level key from
  `tests/unit/coverage/fixtures/sample_coverage.json` one at a time and feed
  to `parse_coverage_json` — required fields must surface
  `CoverageJsonParseError`; optional ones must default gracefully.
- **Coverage parser context-suffix handling.** The fixture's `contexts`
  uses `<nodeid>|run`-style keys. Confirm the parsed `line_contexts` does
  NOT carry the `|<phase>` suffix and the empty-string context is dropped.
- **Coverage compare with mismatched granularity.** Build two
  `CoverageFactSet`s, one `per-test` and one `aggregate`, and pass to
  `compare_coverage_facts`. Per the handoff this MUST NOT short-circuit;
  the result should carry both granularities on the delta.

## End-to-end gap (intentional)

The Coverage engine *consumes* a `coverage.json` produced by the pytest
adapter. The Run Team's `pytest-coverage-emission` slice (which produces
that `coverage.json`) is **NOT in this merge pass** — see
`agent-comms/questions/main-branch-team-2026-05-15-run-team-pytest-coverage-emission-uncommitted.md`
for the blocker. Once that slice lands, end-to-end will look like:

```
novetest init
novetest run pytest --coverage tests/fixtures/projects/pytest-coverage/
# coverage.json appears under .novetest/run/artifacts/run_<ulid>/native/
# Then a derive step emits coverage_facts.json under
# .novetest/coverage/facts/run_<ulid>/
```

Until Run lands, the Coverage engine can only be exercised via Python API
against the checked-in fixture (probes 1–5 above).

## Reporting back

Manual Test should write findings to
`agent-comms/findings/2026-05-15-phase0-release-and-phase2-coverage-foundation.md`
covering each numbered probe above, plus any unexpected behavior.
