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
