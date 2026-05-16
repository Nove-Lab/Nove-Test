---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: jest-adapter-phase1
related:
  - handoffs/run-team-2026-05-16-jest-adapter-phase1.md
  - tasks/run-team-2026-05-16-jest-adapter-phase1.md
  - history/2026-05-16-phase0-closure-partial.md
---

# Verification request: jest Native Engine adapter (Phase 2.5 entry)

## Merged commit

- **Hash:** `e0acce6` (rebased from worktree commit `204eb23` onto current main `6267542`; ff merge afterwards).
- **Title:** `feat(run): jest Native Engine adapter (Phase 2.5 entry, execution only)`
- **Scope:** First non-Python Native Engine adapter — execution only, no coverage. `novetest run` against a `package.json` workspace now selects jest, invokes `npx jest ... --json --outputFile=...`, normalizes the nested test tree into the engine-agnostic Run records, and ships a `tests/fixtures/projects/jest-basic/` SuT. `collect_coverage=True` is a **silent no-op** this slice (Coverage team's Istanbul-parser slice is the unblock). Adapter follows pytest-adapter's shape verbatim; engine_selector + readiness + engine + normalizer all extended to dispatch jest. Refactor: `run/normalizer.py` adopts the Option (a) internal-dispatch pattern (private `_normalize_pytest_payload` / `_normalize_jest_payload`).
- **Closes no `delivery-phasing.md` DoD bullet alone.** This is Phase 2.5 entry infrastructure (per task spec). Unblocks: (a) Coverage team's jest-Istanbul slice (silent-no-op → real coverage path), (b) Release-side CI matrix addition of `actions/setup-node@v4`, (c) future Vitest adapter (mirror this shape).

## Source handoffs consumed

- `agent-comms/handoffs/run-team-2026-05-16-jest-adapter-phase1.md` — single handoff, single commit.

## Merge notes

- **Rebase required (not fast-forward from declared base).** Worktree was branched from `3df9ec2`; I merged coverage-show-diff (`50c9170`) + its comms commit (`6267542`) onto main between Run's branch creation and my merge. Rebase of single commit `204eb23` onto `6267542` produced **one expected conflict in `WORKLOG.md`** — surgical resolution: kept both entries, jest on top (newest), coverage-show-diff below per the WORKLOG "newest on top" convention. No source/test conflicts. New rebased hash: `e0acce6`.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration` → **298 passed + 1 skipped** (267 pytest baseline + 11 coverage-show-diff + 21 jest unit/integration). The 1 skipped is `test_jest_basic_runs_and_returns_passed_record` — skips when `node`/`npx` or `node_modules/.bin/jest` is absent. Expected on Linux dev box / current CI matrix (no Node.js cell yet). `uv run mypy --strict` → **clean** (50 source files, +1 over baseline for `jest_adapter.py`).
- **Diff scope:** scope-clean — only `src/novetest/run/**`, `tests/{unit,integration}/run/**`, `tests/fixtures/projects/jest-basic/**`, WORKLOG, handoff. No `pyproject.toml`, no Coverage code, no Memory/Models code, no Orchestration code.

## Verification steps for Manual Test

**Critical pre-condition.** The jest integration test path requires Node.js + jest installed in the fixture workspace. If you do not have Node.js, **Scenarios 1-3 will skip** — that's the documented expected behavior, not a failure. Only Scenarios 4-5 are exercisable without Node.

### Scenario 0 — Confirm fixture skips cleanly without Node

```sh
cd /home/yjshin/dev/Nove-Test
which node || echo "(no node — skip path will trigger)"
uv run pytest -q tests/integration/run/test_jest_basic.py -v
```

Assert: 1 skipped (or 1 passed if you happen to have Node). If skipped, message names the missing dependency (`node`, `npx`, or `node_modules/.bin/jest`).

### Scenarios 1-3 — Require Node.js + jest in the fixture (optional)

If you can install Node (e.g., `nvm install --lts && nvm use --lts`):

```sh
cd /tmp && rm -rf jest-smoke
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/jest-basic jest-smoke
cd jest-smoke
npm install
uv run --with /home/yjshin/dev/Nove-Test novetest init --output json | python3 -m json.tool | head
```

**Scenario 1** — readiness reports jest as ready:
Assert: `data.engine_readiness.state == "ready"`, engine name `jest`, engine_version populated from `node_modules/jest/package.json`.

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest run __tests__/ --output json > /tmp/run-jest.json
cat /tmp/run-jest.json | python3 -m json.tool | head -40
```

**Scenario 2** — happy-path run produces engine-agnostic records:
Assert: exit `0`, `data.memory_entry.run_reference.engine == "jest"`, test count matches the 3 cases in `__tests__/math.test.js`, all `passed`, nodeids are `<file>::<title>` format.

**Scenario 3** — `--coverage` is silent no-op (NOT an error):
```sh
uv run --with /home/yjshin/dev/Nove-Test novetest run __tests__/ --coverage --output json > /tmp/run-jest-cov.json
```
Assert: exit `0`, `data.coverage_outcome.kind == "unavailable"` with `reason` indicating no native coverage payload (jest's coverage parser is Coverage team's next slice). NOT `"fact-set"`.

### Scenario 4 — pytest engine still works (cross-cycle regression)

```sh
cd /tmp && rm -rf jest-smoke-pytest
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-coverage jest-smoke-pytest
cd jest-smoke-pytest
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' \
  novetest run --coverage tests/ --output json | python3 -m json.tool | head -20
```

Assert: exit `0`, `data.coverage_outcome.kind == "fact-set"`, percent ≈ 86.67. (Confirms the normalizer refactor didn't break the pytest path.)

### Scenario 5 — Misconfigured jest workspace

Create a package.json without jest declared:
```sh
cd /tmp && rm -rf jest-misconfig && mkdir jest-misconfig && cd jest-misconfig
echo '{"name":"x","version":"1.0.0","scripts":{"test":"jest"}}' > package.json
uv run --with /home/yjshin/dev/Nove-Test novetest init --output json | python3 -m json.tool | head -30
```

Assert: `data.engine_readiness.state == "engine-misconfigured"` (or similar), issue text mentions jest not declared in `package.json` devDependencies.

## Critical edge cases

1. **Windows `.bat` path is CI-only.** Readiness probes both `node_modules/.bin/jest` and `.bin/jest.cmd`. Linux/macOS dev boxes exercise the no-extension path; Windows CI exercises `.cmd`. Manual Test on non-Windows host cannot probe `.cmd` branch.
2. **Normalizer refactor risk.** The Option (a) internal-dispatch refactor preserved pytest logic verbatim inside `_normalize_pytest_payload`. The 277-passing baseline from the prior cycle (267 + 10 from jest-related test rewrites + coverage-show-diff additions) is the smoke. If you have time, spot-check by running just `tests/unit/run/test_normalizer.py`:
   ```sh
   uv run pytest -q tests/unit/run/test_normalizer.py -v
   ```
   Assert: all cases pass, both pytest cases and the new jest cases.
3. **`npx jest` not-found heuristic is broad.** Per handoff Gotcha: `Cannot find module` substring matches both "Cannot find module 'jest'" (install-missing) and "Cannot find module './foo'" (SuT bug). False-positive downgrades `missing-plugin` to `unparseable-output` — still actionable, just less specific. Flag any false-positive you encounter.
4. **Per-test duration unit difference between adapters.** Jest's per-test `duration` is in **milliseconds**; pytest's per-phase is **seconds**. The per-engine normalizer paths handle the conversion locally. If you ever compose duration across engines in a downstream slice (e.g. `inspect`), do not assume parity.
5. **Cross-cycle envelope shape regression.** All previous CLI envelopes (`run`, `run --coverage`, `coverage show`, `coverage diff`) should remain byte-equivalent. Scenario 4 above probes one; if you have time, also spot-check that `novetest run tests/` without `--coverage` against `pytest-coverage` STILL omits `coverage_outcome` from `data` entirely (not `null`).

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-jest-adapter-phase1.md` with the standard format. Note any Scenario 1-3 skips (no Node) explicitly so PM can decide whether to commission a Node.js CI cell as the follow-up. The third slice merged this cycle (macos-universal2-transition) lands a separate verification.
