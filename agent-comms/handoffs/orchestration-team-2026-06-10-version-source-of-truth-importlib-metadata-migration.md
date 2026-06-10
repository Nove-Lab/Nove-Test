---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: pending
created: 2026-06-10
slug: orchestration-team-2026-06-10-version-source-of-truth-importlib-metadata-migration
related:
  - agent-comms/tasks/orchestration-team-2026-06-10-version-source-of-truth-importlib-metadata-migration.md
  - agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md
---

# Handoff: migrate `src/novetest/__init__.py::__version__` to `importlib.metadata.version()`

## TL;DR

`src/novetest/__init__.py` now resolves `__version__` dynamically from package
METADATA via `importlib.metadata`, with a PEP-440 `"0.0.0+local"` fallback for
source-checkout-without-install. `pyproject.toml::version` is the single source
of truth at every layer. **Single-file source change.** Byte-transparent: the
`--version` envelope still reports `installedVersion: "0.1.1"`, mypy clean, pytest
baseline held, snapshots pass without regeneration.

**Self-merge ALREADY DONE** per CEO `일괄` dispatch + brief §"Procedural posture".
FF-merged `novetest-version-importlib-metadata` → `main`: `7b079d0..6ff6dde`.
Main Branch's normal FF-merge step is therefore a no-op; this handoff is primarily
for PM (DoD verify/tick) and Manual Test (verify the `--version` surface). **Not
pushed** (no push was requested).

## Worktree / branch / commit

- Worktree: `/home/yjshin/dev/aispace/Nove-Test-wt-version` (removed post-handoff)
- Branch: `novetest-version-importlib-metadata` (off `main` tip `7b079d0`)
- Source commit: `6ff6dde` — `version: resolve __version__ via importlib.metadata (single source of truth)`
- Merged to `main` via `git merge --ff-only` → `main` now at `6ff6dde`
- A follow-up comms commit on the same branch carries this handoff + regenerated INDEX (also FF-merged).
- Source commit files (2): `src/novetest/__init__.py` (+9/-1), `WORKLOG.md` (+10)

## Verbatim source change

Before (entire file):
```python
__version__ = "0.1.1"
```

After (entire file):
```python
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    # Source checkout without installation; fallback for development.
    # The `+local` suffix is a PEP 440 local-version identifier that
    # clearly signals "uninstalled development state".
    __version__ = "0.0.0+local"
```

The current file had **no** module docstring, so none was added (the brief's
"Replace with" block shows a docstring only as illustrative context for "keep it
if present"). Surgical: only the single `__version__` assignment was replaced.

## Verification (all commands + outputs)

### `--version` envelope — BEFORE vs AFTER (byte-identical `installedVersion`)

BEFORE (pre-edit, main venv):
```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/yjshin/dev/aispace/Nove-Test/.venv/bin/python3",
    "installedVersion": "0.1.1",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.15",
    "verifiedAt": "2026-06-10T05:41:24.317924Z"
  },
  "errors": [], "ok": true, "schema": "novetest/v1", "warnings": []
}
```

AFTER (post-merge, main venv): identical except the timestamp/location env fields —
```
"installLocation": "/home/yjshin/dev/aispace/Nove-Test/.venv/bin/python3",
"installedVersion": "0.1.1",
```
`installedVersion` is **byte-identical** (`0.1.1`). The value now comes from package
METADATA at runtime rather than a hardcoded literal; `novetest` is editable-installed
(`uv pip show novetest` → `Version: 0.1.1`, `Editable project location: <repo>`), so
`importlib.metadata.version("novetest")` resolves to the `pyproject.toml::version`.

### mypy `--strict`

```
$ uv run mypy --strict src/novetest
Success: no issues found in 93 source files
```
Unchanged baseline (93 files). stdlib `importlib.metadata` is fully typed — zero new
typing surface; no `_pkg_version` alias / try-except complaints.

### pytest — apples-to-apples in the SAME main venv

```
BEFORE (pre-edit, main venv):  1 failed, 1229 passed, 23 skipped, 2 snapshots passed
AFTER  (post-merge, main venv): 1 failed, 1229 passed, 23 skipped, 2 snapshots passed
```
**Identical counts** in the same venv → the change is byte-transparent. The 1 failure
is the pre-existing host-equip gap
`tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
(`dotnet` not on PATH) — unrelated to this slice, present in the v0.1.0/v0.1.1 WORKLOG
entries too.

(A fresh-provisioned worktree venv reported `1226 passed / 26 skipped` — the documented
±3 host-equip skip variance; total 1252 and the single `dotnet` failure are invariant.)

### Fallback path — BOTH branches empirically exercised

```
$ uv run python -c "import sys; sys.path.insert(0,'src'); from novetest import __version__; print(__version__)"
0.1.1                # installed → try branch resolves from METADATA

$ PYTHONPATH=src /usr/bin/python3 -c "from novetest import __version__; print(__version__)"
0.0.0+local          # no novetest dist-info → PackageNotFoundError → except branch
```
The `except` branch is genuinely reachable and returns the PEP-440 local-version
identifier exactly as specified (DoD #6 satisfied with a real except-branch hit, not
just the installed happy path).

### Snapshot tests (DoD #5)

`2 snapshots passed` without regeneration. The two `.ambr` files are
`tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr` (help envelope)
and `tests/integration/orchestration/__snapshots__/test_test_workflow.ambr` (test
workflow). **Neither snapshots the resolved `installedVersion` value** — the help
snapshot only lists `'novetest --version'` as a *subcommand name*, and the only version
numbers present are the syrupy serializer version and the envelope `schemaVersion: 1`.
So there is no `--version` envelope-value snapshot to regenerate; DoD #5 is satisfied
(both existing snapshots pass unchanged).

## Scope confirmations (per brief §"Reporting back")

- ✅ **NO `pyproject.toml` change** — `version` stays `"0.1.1"` by design (that is the whole point).
- ✅ **NO other `src/novetest/**` file touched** — only `src/novetest/__init__.py`.
- ✅ **NO snapshot regeneration**, NO `tests/**` modification, NO `.github/workflows/**`, NO `THIRD_PARTY_NOTICES` (stdlib only, no new dependency).
- ✅ Envelope schema unchanged (`schema: novetest/v1`); no envelope-schema implication.

## Surprises

1. **Apples-to-apples needed the main venv.** A first pytest pass inside the freshly
   provisioned worktree venv reported `1226/26/1` while my pre-edit main-venv baseline
   was `1229/23/1`. Both are on this same dev host — it is the documented ±3
   host-equip-dependent *conditional-skip* variance (3 tests flip pass↔skip on whether
   an optional dep is present in the venv), not a regression. Re-running post-merge in
   the SAME main venv reproduced `1229/23/1` exactly, confirming transparency. No action
   needed; pinned in WORKLOG so the next agent doesn't chase it.
2. The fallback `except` branch required a non-venv interpreter to exercise genuinely
   (`/usr/bin/python3` with `PYTHONPATH=src` and no novetest dist-info) — done, returns
   `0.0.0+local`.

## WORKLOG entry

Appended under `## 2026-06-10 — version-source-of-truth / importlib-metadata-migration`
(newest on top), Landed/Verified/Left open/Gotcha/Next format. Committed in `6ff6dde`.

## DoD bullets believed closed — PM to verify and tick

This slice closes (brief's 8-bullet DoD; not ticked here — PM territory):
1. `src/novetest/__init__.py` edited per the canonical try/except + PEP-440 fallback pattern — **believed closed**
2. `uv run mypy --strict src/novetest` clean, 93 source files — **believed closed**
3. pytest baseline maintained (same-venv counts identical: `1229/23/1` before and after) — **believed closed**
4. `uv run novetest --version --output json` returns same `installedVersion` (`0.1.1`) as pre-edit (both envelopes cited above) — **believed closed**
5. Snapshot tests pass without regeneration (no `--version`-value snapshot exists; both `.ambr` pass) — **believed closed**
6. Fallback path empirically reachable (`0.0.0+local` via real except-branch hit) — **believed closed**
7. WORKLOG entry per format — **believed closed**
8. Handoff with DoD-bullets-believed-closed list — **believed closed (this file)**
9. `python3 tools/regen_comms_index.py` — **believed closed** (run as part of this routine)

Architectural close (per decision `2026-06-10-version-source-of-truth-via-importlib-metadata.md`):
- Duality between `pyproject.toml::version` and `src/novetest/__init__.py::__version__` resolved — Path A operationally live.
- Future Release-team version-bump cycles are 1-line `pyproject.toml` edits; Release team never touches `src/` for version.

No Phase 0 DoD tick changes (internal architecture, zero user-observable behavior change).

## Next steps (other teams)

- **Main Branch:** FF-merge already performed (self-merge authorized); only the comms commit carrying this handoff + regenerated INDEX remains. No conflict risk (comms-only).
- **Manual Test:** verify `novetest --version --output json` still reports the correct `installedVersion` from an installed state.
- **PM:** verify + tick DoD; cycle-close noting Path A is operationally live. No follow-up architecture work needed.
