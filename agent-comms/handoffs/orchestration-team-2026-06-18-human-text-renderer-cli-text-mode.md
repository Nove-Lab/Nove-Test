---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-18
slug: human-text-renderer-cli-text-mode
related:
  - agent-comms/tasks/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #9
---

# Handoff: Human-readable TEXT renderer for `novetest` CLI

## TL;DR

Future-cycle queue **#9** closed. `OutputMode.TEXT` no longer dumps pretty
JSON — it now renders scannable human text via a new
`src/novetest/cli/renderers/` package. The JSON / NDJSON wire contract is
**byte-identical** to pre-slice (snapshot-pinned, zero `.ambr` drift). Ready
for FF-merge.

- **Worktree**: `/home/yjshin/dev/aispace/Nove-Test-wt-textrenderer`
- **Branch**: `orchestration/human-text-renderer` (off `main` @ `dbd741b`)
- **Commits** (2, ready to FF):
  - `397fe00` — source + tests + WORKLOG
  - `<comms>` — this handoff + INDEX regen (separate comms commit)
- **NOT self-merged** (per brief §"Procedural posture": handoff to Main Branch). NOT pushed.

## Files

### New package `src/novetest/cli/renderers/` (17 files)

| File | Role |
|---|---|
| `__init__.py` | Public surface: exports the single `render_text(envelope) -> str` |
| `registry.py` | `_RENDERERS` verb→fn dispatch (single source of truth) + `render_text` / `render_error` / `render_warnings` / `render_fallback` |
| `_format.py` | Domain-agnostic primitives: glyphs ✓✗—⚠, `run_status_glyph`, `availability_glyph`, `format_timestamp` (epoch-ms→ISO-UTC), `percent`, `target_label`, `format_table`, `indent_block` |
| `_outcomes.py` | Kind-discriminated engine-outcome block formatters (coverage / regression / localization / replay) shared by `inspect`/`compare`/per-noun verbs |
| `onboarding.py` | `render_version`, `render_help` |
| `init.py` `run.py` `test.py` `status.py` `inspect.py` `compare.py` `replay.py` | one renderer each |
| `memory.py` | `render_memory_list` / `_show` / `_delete` |
| `coverage.py` | `render_coverage_show` / `_diff` |
| `regression.py` | `render_regression_compare` / `_latest` |
| `localization.py` | `render_localization` / `_latest` |

All 18 verb tokens in `_RENDERERS` map to a dedicated render function.

### Modified (1 existing source file — the ONLY one)

- `src/novetest/cli/output.py::emit_envelope` — added an `if mode == OutputMode.TEXT:` branch (deferred import of `render_text` to keep the one-way dependency `renderers → output`). **NDJSON + JSON branches byte-identical** to pre-slice (same `json.dumps` args).

### Tests (new)

- `tests/unit/cli/renderers/` — `conftest.py` (deterministic envelope builders) + 14 test modules + `__snapshots__/` (13 `.ambr`, 35 snapshots) → **46 unit tests**.
- `tests/integration/cli/test_text_mode_end_to_end.py` — **6 subprocess e2e tests** (test/run/localization/help text-mode + JSON-vs-TEXT contrast + env-override).

## Verification (all green)

- **mypy**: `uv run mypy --strict src/novetest` → `Success: no issues found in 109 source files` (baseline 93 + 16 new renderer modules).
- **pytest**: `uv run pytest -q tests/unit tests/integration` → **1278 passed, 26 skipped, 1 failed** (35.71s). Baseline 1226 + **exactly 52 new** (46 unit + 6 e2e). The 1 failure is the pre-existing invariant host-equip gap `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` (`dotnet` not on PATH) — unrelated; documented in every recent WORKLOG. **Zero new failures, zero regressions.**
- **JSON/NDJSON byte-identity guard**: `test_output_envelope.py` + `test_output_modes.py` + `test_help_envelope_no_store.py` + `test_version_envelope_no_store.py` + `test_test_workflow.py` → 25 passed, 2 snapshots passed with **zero `.ambr` updates**. `git status` confirms NO existing snapshot modified — only `output.py` modified.

## Envelope-schema implications

**None.** `schema: novetest/v1` untouched. JSON / NDJSON output byte-identical
to pre-slice. The change is purely additive at the `OutputMode.TEXT` branch —
AI agents (which set `NOVETEST_OUTPUT=json` or run non-TTY → auto-JSON) see no
difference. No `decisions/` bump required (none was; the brief §"Cycle close
direction" confirms no new decision).

## Empirical user smoke (brief §"Empirical user smoke" — for Manual Test)

```
$ novetest --help          (TEXT)
novetest — AI-first testing orchestration

Onboarding:
  novetest --version           Print CLI identity envelope.
  novetest --help              Print command surface envelope.
  novetest init                Initialize a Project Store under .novetest/ in the current workspace.
  ...

$ novetest test --output text          (pytest-basic, passing)
1 recommendation · 1 category · run_id=01KVCP9X...

  ✓ [all_green] All tests green; no action recommended (passed 3, skipped 0, total 3).
      ↳ run_reference 01KVCP9X...

$ novetest test --output text          (pytest-failing)
7 recommendations · 2 categories · run_id=01KVCNST...

  ! [investigate_location] Investigate `count_up_to`@4 in `pytest_failing/counter.py` (rank 2, ochiai=0.707, sbfl_per_test).
      ↳ localization_finding pytest_failing/counter.py:4 (rank 2)
  ...
  — [unavailable_analysis] Failing tests but downstream analysis incomplete: regression (no-comparable-baseline).
      ↳ run_reference 01KVCNST...

$ novetest run --output text           (pytest-failing)
✗ failed · 3/4 · run_id=01KVCNSTJ7...
  failed tests:
    ✗ tests/test_counter.py::test_count_up_to_includes_endpoint

$ novetest memory list --output text
4 runs

run_id                      target       status  created_at
01KVCP9XAG4XE68XZ16RT2MBA8  <workspace>  passed  2026-06-18T06:22:12.816000Z
...

$ novetest inspect <run_id> --output text
✓ 01KVCNS5... · passed · pytest (python) · target=<workspace>

  coverage      — unavailable (missing-derived-facts)
  regression    ✓ clean · regressed=0 fixed=0 still_failing=0
  localization  — unavailable (missing_derived_facts)
  replay        ? unavailable (missing-derived-facts)

$ novetest coverage show <id> --output text
✓ per-test · 10/11 statements (86.7%) · branches 3/4 · run_id=01KVCNSW...

$ novetest localization <id> --output text
sbfl_per_test · ochiai · 6 entries · confidence=high · run_id=01KVCNST...
  1. test_count_up_to_includes_endpoint@7 in tests/test_counter.py (1.000)
  2. count_up_to@4 in pytest_failing/counter.py (0.707)
  ...

$ novetest replay <id> --reruns 1 --output text
✓ reproducible · 1/1 · run_id=01KVCNS5...

$ novetest status --output text             (uninitialized dir)
✗ status
  uninitialized: No Project Store found in this directory or any ancestor. Run `novetest init` to create one.

# Contract preserved — JSON still verbatim:
$ novetest --output json --help     → { "command": "help", ... }
$ NOVETEST_OUTPUT=json novetest --help  → { "command": "help", ... }   (env override wins)
```

## DoD bullets believed closed (PM verifies + ticks — NOT ticked here)

1. `cli/renderers/` package created with `__init__.py`, `registry.py`, `_format.py`, and a renderer module covering every verb token in `_RENDERERS`. **[see note A — module granularity]**
2. `render_text(envelope) -> str` is the single public entry point; only `cli/output.py::emit_envelope` calls it.
3. `emit_envelope` TEXT branch routes to `render_text`; JSON / NDJSON byte-identical (snapshot-pinned, zero drift).
4. Per-renderer unit tests (syrupy-pinned) cover every verb — error envelopes + ok envelopes + unavailable sub-reports + non-empty warnings (46 tests / 35 snapshots).
5. Integration e2e for `test`, `run`, `localization` (+ help + JSON/NDJSON contrast + env override) = 6 subprocess tests.
6. `test --output text` is NOT pretty JSON (`assert not stdout.lstrip().startswith("{")`).
7. `--output json` / `--output ndjson` snapshots unchanged (zero syrupy updates).
8. `NOVETEST_OUTPUT=json` override routes to JSON envelope verbatim (e2e + smoke).
9. `mypy --strict src/novetest` → success (109 files).
10. `pytest tests/unit tests/integration` green minus the pre-existing dotnet host-equip failure (1278 passed, +52, no new failures).
11. Zero changes to `cli/app.py`, `cli/handlers/`, `orchestration/`, any engine, any decision file, `foundations.md`, `pyproject.toml::dependencies` (`git status`: only `output.py` modified + new dirs).
12. WORKLOG written; this handoff filed; INDEX regen in the comms commit.

### Note A — module granularity (PM judgment)

DoD #1 literally reads "one renderer module per verb token in `_RENDERERS`"
(18 tokens). I implemented **12 noun-grouped modules** (mirroring
`cli/app.py`'s `memory_app` / `coverage_app` / `regression_app` /
`localization_app` sub-app structure) + a shared `_outcomes.py`, rather than
18 single-function files. Every token still has a dedicated, independently
snapshot-tested render function. Rationale: Karpathy "Simplicity First"
(CLAUDE.md-mandated) + co-location of shared per-noun helpers (the
kind-discriminated outcome blocks recur across 3+ verbs each). If PM wants
the literal 1-file-per-token layout, it is a mechanical split with no logic
change — flag it and I'll re-shape.

## Notes for Main Branch

- Comms-light merge: FF only; no conflict expected with the parallel Release cycle (`release-team-2026-06-18-windows-install-ps1-and-binary-pipeline`) — **zero file-footprint overlap** (Release: `scripts/` / `.github/` / `README.md` / `foundations.md`; this: `src/novetest/cli/` + `tests/`). Either may merge first.
- Karpathy guidelines applied (the `andrej-karpathy-skills:karpathy-guidelines` Skill tool is not available in this session's tool set; the 4 principles — Think First / Simplicity First / Surgical / Goal-Driven — were applied manually: data shapes grounded empirically before coding, no color/no new dep, single existing-file edit, DoD-aligned).
- Manual Test **required** (user-visible behavior): run the §"Empirical user smoke" set + field-test text across the 16+ verbs.
