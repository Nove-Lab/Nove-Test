---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-16
slug: coverage-cli-wiring
related:
  - handoffs/orchestration-team-2026-05-16-coverage-cli-wiring.md
  - tasks/orchestration-team-2026-05-16-coverage-cli-wiring.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
---

# Verification request: `novetest run --coverage` wired end-to-end

## Merged commit

- **Hash:** `10300bb` (fast-forward from `1c22e29`; clean linear history, no merge commit).
- **Title:** `feat(orchestration): wire --coverage through novetest run end-to-end`
- **Scope:** `novetest run` learns `--coverage` / `-c`. CLI handler threads the flag through `run_target_in_store(..., collect_coverage=True)`, which now invokes `coverage.derive_coverage_facts(store, run_reference)` after persisting the RunRecord. The envelope grows an optional `data.coverage_outcome` block discriminated by `kind: "fact-set" | "unavailable"`. When `--coverage` is NOT passed, the key is omitted entirely (not `null`), so Phase 1 envelopes for non-coverage runs are byte-equivalent.
- **Cross-charter touch (authorized Option A in task):** `src/novetest/run/engine.py` — `execute` and `execute_with_engine_context` both gained `collect_coverage: bool = False` kwarg as pure pass-through to the already-extant `run_pytest(collect_coverage=...)`. Defaults False so all existing callers byte-equivalent.

## Source handoffs consumed

- `agent-comms/handoffs/orchestration-team-2026-05-16-coverage-cli-wiring.md` — single handoff, single commit.

## Merge notes (anything not obvious)

- **No conflicts.** Base commit (`1c22e29`) matched current main HEAD exactly, so the merge was a clean fast-forward. No surgical edits required from me.
- **Test gate re-run on main after merge:** `uv run pytest -q tests/unit tests/integration` → **267 passed** (1 syrupy snapshot), `uv run mypy --strict` → **clean** (49 source files). Identical to the originating team's pre-handoff numbers.
- **Schema version unchanged.** `data.coverage_outcome` is an additive extension on the `run` command envelope. No `decisions/` entry needed per the handoff's envelope-schema note.
- **Operational quirk during this merge:** the `Write` tool was blocked by the harness's worktree-isolation handshake (per `GOTCHAS.md`). This verification file was written via the sanctioned `Bash` heredoc fallback. Byte-identical output; no deliverable impact.

## Verification steps for Manual Test

All commands run from a scratch directory; the slice does not touch `pyproject.toml` so no new deps. The `--with pytest-json-report --with pytest-cov --with 'coverage[toml]'` triple is **required** for the smoke (see Critical edge cases below).

### Setup (one-time)

```sh
cd /tmp && rm -rf coverage-cli-smoke
cp -r /home/yjshin/dev/Nove-Test/tests/fixtures/projects/pytest-coverage coverage-cli-smoke
cd coverage-cli-smoke
uv run --with /home/yjshin/dev/Nove-Test novetest init
```

Expect: `init` envelope `data.engine_readiness == "ready"` (pytest detected).

### Scenario 1 — Happy path, `--coverage` long flag

```sh
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' \
  novetest run --coverage tests/ --output json | tee /tmp/run-coverage-envelope.json
```

Assert (parse the envelope):
- Exit code `0`.
- `envelope.schema == "novetest/v1"`.
- `envelope.data.coverage_outcome.kind == "fact-set"`.
- `envelope.data.coverage_outcome.mapping_granularity == "per-test"`.
- `envelope.data.coverage_outcome.summary.percent_covered ≈ 86.67`.
- `envelope.data.coverage_outcome.run_reference` is present (mirrors `memory_entry.run_reference`).
- `envelope.data.memory_entry.has_coverage_facts == true`.

Then verify on-disk landing:

```sh
ls .novetest/coverage/facts/run_*/coverage_facts.json
python3 -m json.tool .novetest/coverage/facts/run_*/coverage_facts.json | head -60
```

Assert: exactly one `coverage_facts.json` exists at the contract-frozen path. Layout matches `decisions/2026-05-15-coverage-facts-json-layout.md` (v1).

### Scenario 2 — Memory Entry auto-flip on subsequent read

Using the `run_id` printed in Scenario 1's envelope:

```sh
RUN_ID=$(python3 -c "import json; print(json.load(open('/tmp/run-coverage-envelope.json'))['data']['memory_entry']['run_reference']['run_id'])")
uv run --with /home/yjshin/dev/Nove-Test novetest memory show "$RUN_ID" --output json | python3 -m json.tool | grep has_coverage_facts
```

Assert: `"has_coverage_facts": true`. (Confirms Memory's filesystem-probe auto-flip works without any Memory-team code changes — Orchestration just triggers the file creation.)

### Scenario 3 — Short alias `-c` is byte-equivalent

```sh
uv run --with /home/yjshin/dev/Nove-Test --with pytest-json-report --with pytest-cov --with 'coverage[toml]' \
  novetest run -c tests/ --output json > /tmp/run-c-envelope.json
```

Assert: `envelope.data.coverage_outcome.kind == "fact-set"` again. (Different `run_id` is expected; the comparison is structural, not byte-identical to Scenario 1.)

### Scenario 4 — No-coverage run is byte-equivalent to Phase 1 (key omitted, not null)

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest run tests/ --output json > /tmp/run-nocov-envelope.json
python3 -c "import json; d=json.load(open('/tmp/run-nocov-envelope.json'))['data']; assert 'coverage_outcome' not in d, d; print('OK: coverage_outcome key omitted')"
```

Assert: the script prints `OK: coverage_outcome key omitted`. The key is **omitted**, not emitted as `null`. (Regression-sensitive — any change to envelope plumbing must preserve this.)

### Scenario 5 — Help surface

```sh
uv run --with /home/yjshin/dev/Nove-Test novetest run --help
```

Assert: the `--coverage` / `-c` flag appears in the help output as a single canonical entry (Cyclopts `name=["--coverage", "-c"]` form).

## Critical edge cases worth probing

1. **`CoverageUnavailable` envelope shape.** The happy path emits `kind: "fact-set"`. The other branch (`kind: "unavailable"`) is harder to hit organically because the fixture is set up correctly. To probe it: after a successful `--coverage` run, manually **delete** the `coverage_json` artifact under `.novetest/runs/run_<id>/artifacts/` and re-trigger the derive path via a future `coverage show` command — but that verb doesn't exist yet (Phase 2 DoD #2). For this cycle, document whether you can construct any path that exercises `kind: "unavailable"` end-to-end; if not, note it as an untested branch and let PM decide whether to commission an integration test that targets the unavailable path.
2. **Re-run on same store creates a new run dir.** Run Scenario 1 twice. Confirm two separate `run_<id>/` directories under `.novetest/coverage/facts/`, each with its own `coverage_facts.json`. Neither overwrites the other.
3. **Dev-deps requirement when novetest is consumed as a wheel.** The smoke needs `--with pytest-json-report --with pytest-cov --with 'coverage[toml]'`. Try the smoke without those `--with` flags — confirm it fails (and capture the failure shape so we know what a user-facing missing-deps error looks like). The handoff flagged this for a future user-facing install/getting-started doc; your finding will inform that doc.
4. **Cyclopts arg ordering.** Confirm both `novetest run --coverage tests/` and `novetest run tests/ --coverage` parse equivalently (Cyclopts should accept both flag placements; this is a sanity check, not a known-bug probe).
5. **Subprocess vs python-API path parity.** Scenarios 1–4 above use the subprocess CLI. The unit/integration tests already cover the python-API path. If you have time, spot-check that an in-process call (`from novetest.orchestration.workflows.run import run_target_in_store; await run_target_in_store(...)`) produces an `outcome.coverage_outcome` field with the same `mapping_granularity` and summary. (Not blocking — the integration test already locks this; spot-check is for human-in-the-loop confidence.)
6. **Fixture's deliberately uncovered line stays uncovered.** Per the integration test, line 16 of `pytest_coverage/classifier.py` is deliberately uncovered. Open `.novetest/coverage/facts/run_*/coverage_facts.json`, find the per-file entry for that file, confirm `16` appears in `missing_statements` (or whatever the v1 layout calls the missing-line array). Sanity check on the persisted shape, not just the in-memory dataclass.

## Reporting

Write `agent-comms/findings/manual-test-team-2026-05-16-coverage-cli-wiring.md` with:
- **Verdict:** `passed` | `failed` | `partial`.
- **What was tested:** narrative of which scenarios you actually ran, including any deviations.
- **Issues found:** with minimal reproducers (commands + observed envelope/files).
- **Recommendations for PM:** especially around (a) whether the `CoverageUnavailable` branch needs commissioned coverage, (b) whether the dev-deps requirement deserves a getting-started doc note, and (c) the `delivery-phasing.md` DoD #1 wording adjustment the handoff flagged (`novetest test --coverage` → `novetest run --coverage`).
