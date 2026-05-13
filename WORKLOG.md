# Worklog

Cross-agent handoff log. Newest entry on top. One entry per session that touches `src/` or `tests/`.

See `CLAUDE.md` → "Multi-Agent Worklog Harness" for the rules. The `PreToolUse` hook at `.claude/hooks/check-worklog-before-commit.sh` blocks `git commit` of `src/`+`tests/` changes that do not stage this file.

**Entry format:**

```
## <YYYY-MM-DD> — <phase> / <area>
- Landed: <what merged, with file paths>
- Verified: <command(s) run and result>
- Left open: <unfinished slice or follow-up>
- Gotcha: <surprise that future-you needs to know; or "none">
- Next: <suggested next step for the next agent>
```

When this file exceeds ~200 lines, move entries older than the current phase into `design/archive/worklog-<phase>.md` and link from the top.

---

## 2026-05-13 — phase1 / memory-engine

- Landed: `src/novetest/utils/ulid.py` (Crockford-base32 encoder/decoder, `generate_ulid` / `extract_timestamp_ms` / `date_path_for_timestamp_ms`); `src/novetest/memory/project_store.py` (`ProjectStore` dataclass + `create_project_store` / `locate_project_store` / `get_project_store_state` + `ProjectStoreCorruptError`), implementing memory contract §1 against the file-only layout in `foundations.md` §4; `src/novetest/memory/store.py` implementing the Phase 1 subset of §2 — `store_run_evidence`, `retrieve_run_evidence`, `list_run_history`, `delete_run_evidence`, `get_memory_entry_availability`; `src/novetest/memory/__init__.py` public re-exports. Tests: `tests/unit/utils/test_ulid.py` (8), `tests/unit/memory/test_project_store.py` (16), `tests/unit/memory/test_store.py` (17).
- Verified: `uv run pytest -q` → 128 passed (87 Phase 0 + 41 new). `uv run mypy` → clean on 28 source files under `--strict`. New tests exercise the engine-subdirectory skeleton, idempotent re-init (preserves a sentinel `record.json` under `memory/runs/...`), walk-up `locate_project_store` with stop-at-first semantics, `NOVETEST_HOME` pinning, `record.json` round-trip via `RunRecord.to_dict()`/`from_dict()`, tombstone-via-`rename` plus in-place `status: tombstoned` mutation, list-history newest-first across both live and tombstoned, and availability-flag computation that flips when peer engines drop the expected derived-fact files on disk.
- Left open: **No Phase 1 DoD bullet in `delivery-phasing.md` is fully closed by this commit alone** — every bullet is gated on either the Run engine slice (Task 2) or the CLI/orchestration wiring slice (Task 3) per today's split. Checkboxes are intentionally untouched. Intentionally out of scope this session: `memory/find_runs_for_target` and `memory/find_latest_analyzable_run` — they are in the Memory contract Section 2 but NOT in Phase 1 "Interfaces in scope" (delivery-phasing.md Phase 1); Regression (Phase 3) and Localization (Phase 4) introduce them. The `NativeResult` parameter on `store_run_evidence` from the contract is collapsed to just `run_record` at the Python API level since `RunRecord.artifact_paths` already encodes the native-artifact handles the contract speaks of; revisit if the Run/orchestration slice surfaces a need.
- Gotcha: `NOVETEST_HOME` is interpreted as **the path to the `.novetest/` directory itself**, not the parent workspace — `locate_project_store` reads it and returns the handle directly without doing the walk. Tests passing `env={NOVETEST_HOME: str(store.path)}` work; tests pointing it at a workspace root will not. The `_resolve` path-lookup helper derives the date directory from `RunReference.created_at` (epoch ms) rather than parsing the ULID, so unit-test run_ids like `"01HXYZ"` (not a full 26-char ULID) round-trip correctly; the foundations-level invariant that the ULID prefix encodes `created_at` still holds when the Run engine generates real ULIDs via `utils.ulid.generate_ulid`. `delete_run_evidence` mutates `RunRecord.status` to `"tombstoned"` and stamps `metadata["tombstoned_at"]`; downstream code that asserts on `status` values should treat `"tombstoned"` as a sentinel rather than a real engine outcome.
- Next: the CLI/orchestration slice (Task 3 in today's plan) can now wire `novetest init` to `memory.create_project_store` and `novetest memory list|show|delete` / `novetest status` to the corresponding Memory functions, then build the `uninitialized` envelope on `locate_project_store(...) is None`. The Run-engine slice (Task 2, parallel session) is independent and does not import anything from `memory/`. The combined integration tests in `tests/integration/` are gated on Task 3.

---

## 2026-05-11 — phase0 / cli-onboarding-envelope

- Landed: `src/novetest/cli/output.py` (envelope dataclass, exit-code constants, NDJSON/JSON emitters, `--output` / `NOVETEST_OUTPUT` / TTY resolution); `src/novetest/orchestration/onboarding/identity.py` (`report_cli_identity`) and `command_surface.py` (`describe_command_surface`) — neither touches the filesystem or any Project Store lookup; `src/novetest/cli/app.py` rewritten to register all 14 documented subcommands as not-implemented stubs that emit envelope + exit 2, and to intercept top-level `-v` / `-h` (in any position relative to `--output`) **before** Cyclopts parsing. Tests under `tests/unit/cli/` (5 files, 39 cases) and `tests/integration/cli/` (3 files + conftest, 25 cases including a syrupy snapshot for the help envelope).
- Verified: `uv run pytest -q` → 87 passed; `uv run mypy` → clean (25 source files, `--strict`). Manual smoke: `python -m novetest --version --output json` / `--help --output json` / `memory list` / `test --help` all behave per Phase 0 DoD.
- Left open: text-mode renderers (Phase 0 text mode currently falls back to pretty JSON — acceptable per `foundations.md` §2 for now); structured envelope for *subcommand*-level `--help` (Cyclopts emits its native text help with ANSI for `<sub> --help`, which is fine for DoD #3's "exit 0" requirement). Per-OS / per-Python CI matrix (DoD #1) is the CI workflow slice, not this one. PyApp release + `install.sh` (DoD #4–#6) are out of scope here.
- Gotcha: Cyclopts 4.11 does **not** auto-register `--output` as a global option; we strip `--output[=]value` from argv inside `main()` before calling `app(args)` so it works in any position. Resolved mode is stashed in a module-level `_active_mode` that stubs read — keep this in mind if you ever introduce concurrent CLI invocations in-process (tests use subprocess, not in-process). `pyproject.toml` `[tool.pytest.ini_options]` was tightened: `testpaths = ["tests/unit", "tests/integration"]` and `norecursedirs = ["tests/fixtures"]` — otherwise pytest tried to collect the SuT projects under `tests/fixtures/projects/` and exploded on their `from pytest_basic.math_utils import ...` lines.
- Next: Slice B (Phase 1 entry) — `memory/store.py` + `memory/project_store.py` (file-only per the updated `foundations.md` §4), `novetest init` workflow wiring `create_project_store` + `run/assess_engine_readiness`, `locate_project_store` walk-up, and the `uninitialized` envelope for operating commands invoked outside an initialized store. The fixture `empty-no-engine/` is the readiness input.

---

## 2026-05-11 — phase0 / domain-models

- Landed: `src/novetest/models/run_reference.py`, `run_record.py`, `test_result.py`, `memory_entry.py`, plus `models/__init__.py` re-exports; matching unit tests under `tests/unit/models/`. All four entities are `@dataclass(slots=True, frozen=True)` with hand-rolled `to_dict()` / `from_dict()` and a v1 `schema_version` field per `foundations.md` §4–§5.
- Verified: `uv run pytest tests/unit/models -q` → 27 passed; `uv run mypy` → clean (21 files, `--strict`).
- Left open: no DoD bullet in `delivery-phasing.md` closes on models alone — every Phase 0/1 bullet also depends on CLI/Memory/Run code that has not yet landed, so `delivery-phasing.md` checkboxes are intentionally untouched. Per the (concurrently staged) file-only-persistence pivot in `foundations.md` §4 / `delivery-phasing.md` / `index.md`, there is no SQLite or `memory/migrations/` work owed in Phase 1; `record.json` written by Memory will use these dataclasses' `to_dict()` directly.
- Gotcha: `TestResult` clashes with pytest's `Test*` auto-collection. Suppressed with `__test__: ClassVar[bool] = False`. If you ever rename the entity, drop the marker. Native Engine context is inlined onto `RunRecord` (`engine_name` / `engine_version` / `ecosystem`) rather than a separate dataclass — v1 has no behavior that requires it to round-trip on its own.
- Next: the Phase 1 Project Store + `memory/create_project_store` slice can now consume these models as the wire format for `memory/runs/YYYY/MM/DD/run_<ulid>/record.json`. The Phase 5 derived SQLite cache (when it lands) should source its `schema_version` value from each model's `CURRENT_SCHEMA_VERSION` ClassVar so the JSON-as-source-of-truth invariant stays honest.

---

## 2026-05-11 — phase1 / fixtures

- Landed: `tests/fixtures/projects/pytest-basic/`, `tests/fixtures/projects/pytest-failing/`, `tests/fixtures/projects/empty-no-engine/` — each with own `pyproject.toml`, README, and (for the pytest fixtures) a small package + tests. No `novetest` import in any fixture.
- Verified: file-tree only. The fixtures are SuT inputs; they will be exercised once Phase 1's `run/assess_engine_readiness` + `run/execute` + integration tests land. `pytest-failing/pytest_failing/counter.py` carries an intentional off-by-one — README documents it as the fixture's contract.
- Left open: no `inspect` / `memory` / integration test wiring (intentional — that's the other parallel sessions). No DoD bullets ticked in `delivery-phasing.md`: every Phase 1 DoD bullet also depends on CLI/Memory/Run code that has not yet landed.
- Gotcha: the pytest fixtures use `pythonpath = ["."]` in `[tool.pytest.ini_options]` so tests can import the local package without an install step. Per `foundations.md` §6, child pytest invocations into these fixtures must set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `cwd=` the fixture root so the parent dev venv's plugins do not leak in.
- Next: CLI + Memory + Run engine slices can now point at these fixtures for integration tests. The `empty-no-engine/` fixture is the input for the `engine-missing` readiness DoD bullet.

---

## 2026-05-11 — phase0 / harness

- Landed: this file + `CLAUDE.md` harness section + DoD checkboxes in `design/implementation-plan/delivery-phasing.md` + `.claude/hooks/check-worklog-before-commit.sh` + `.claude/settings.json`.
- Verified: file structure only — hook will be exercised on the first real commit of `src/`/`tests/` changes.
- Left open: nothing.
- Gotcha: the hook intercepts `git commit` invoked through Bash; it does not see commits made from outside Claude Code. Treat the human as trusted there.
- Next: pick the top unchecked DoD bullet in `delivery-phasing.md` Phase 0 and start that slice.
