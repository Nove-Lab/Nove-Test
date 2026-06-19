---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-19
slug: v1-metadata-channel-sunset
related:
  - agent-comms/tasks/run-team-2026-06-19-v1-metadata-channel-sunset.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
  - src/novetest/run/adapters/dotnet_adapter.py
  - tests/unit/run/adapters/test_dotnet_adapter.py
  - tests/integration/run/test_dotnet_coverage.py
  - tests/integration/run/test_dotnet_warnings.py
---

# Handoff: v1 `coverage_unavailable_kind/_message` metadata channel sunset

The Option C envelope-warnings-projection (shipped 2026-06-07) has been
the operational user-visible surface for adapter warnings for 12 days.
The one-release-cycle backward-compat window declared by 2026-06-06
decision §"Acceptance criteria for Option C slice" criterion #2 closed
cleanly. This slice removes the v1 metadata-bridge keys from the dotnet
adapter, making `envelope.warnings[]` the **single canonical** surface
for adapter-emitted warnings.

Scope: bookkeeping cleanup, not a feature change. The `AdapterWarning`
emit onto `NativeResult.warnings` (the canonical surface) was retained
byte-identically; only the v1 bridge writes were removed.

## Worktree

| Field | Value |
|---|---|
| Path | `/home/yjshin/dev/aispace/novetest-v1-metadata-channel-sunset` |
| Branch | `run/v1-metadata-channel-sunset` |
| Base | `42f6a32` (current `main` HEAD as of cycle dispatch — supersedes brief's `a2679a0` by 1 comms commit `comms: Wave 1 parallel dispatch …`) |
| Tip | (filed under WORKLOG + handoff + INDEX commit; check `git log` post-commit) |

## Files written / modified

| File | LOC delta | Change |
|---|---|---|
| `src/novetest/run/adapters/dotnet_adapter.py` | ~-30 / ~+5 | Removed 2 local-var declarations + 2 string-literal assignments (~24 lines) + 4-line metadata write block. Rewrote 4 docstrings/comments to drop literal references to removed key names. `AdapterWarning` emit on `NativeResult.warnings` untouched. |
| `tests/unit/run/adapters/test_dotnet_adapter.py` | ~+45 / ~-30 | Migrated 5 assertion sites: `test_restore_failure_tolerated_proceeds_to_probe` (1 assertion) + `TestEnvelopeSafetyNet` class docstring + 4 tests (renamed and re-pinned against `result.warnings`). New positive assertion pins `AdapterWarning.details.csproj` + `.coverlet_floor` per decision §1.1 structured-detail shape. |
| `tests/integration/run/test_dotnet_coverage.py` | ~+7 / ~-7 | Migrated 1 happy-path negative assertion block (lines 259-266) from metadata→`result.warnings` filter check. |
| `tests/integration/run/test_dotnet_warnings.py` | ~+10 / ~-13 | Migrated 1 CLI-smoke positive assertion block (lines 142-148) from metadata-bridge "must populate" to negative-proof "MUST be absent" — binds the sunset. Rewrote test docstring + 1 in-test comment. |
| `agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` | ~+80 | Appended "Amendment 2026-06-19" section: pre/post surface table, scope, backward-compat posture, empirical sunset evidence. §"Reserved metadata keys for v1" historical table annotated historical-only (NOT deleted — audit trail preserved). |
| `WORKLOG.md` | ~+12 | New top entry (one-paragraph Landed; full §2.5 + DoD #4 Verified; Left open + 2 Gotchas + Next). |
| `agent-comms/handoffs/run-team-2026-06-19-v1-metadata-channel-sunset.md` | NEW | This file. |
| `agent-comms/INDEX.md` | regenerated | `tools/regen_comms_index.py`. |

Net src LOC: ~−25 (deletions dominate per "bookkeeping cleanup" framing).
Net test LOC: ~+15 (positive shape assertions slightly more verbose than the original 1-line metadata `.get(...)` pins).

## Verification

### §2.5 binding equipped-host gate (per `decisions/2026-06-08-equip-and-exercise-default-verification-posture.md` §1 SHOULD tier + §2.5 mandate)

The slice touches `src/novetest/run/adapters/dotnet_adapter.py` +
`tests/unit/run/adapters/test_dotnet_adapter.py`, so §2.5 fires.
Equipped host: `~/.local/share/novetest-toolchains.sh` provisioned
**dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5**.

| Command | Result |
|---|---|
| `uv run pytest tests/unit/run/adapters/test_dotnet_adapter.py` | **93 passed in 0.27s** — equipped-host adapter logic fully green |
| `uv run mypy --strict src/novetest` | **Success: no issues found in 109 source files** (baseline unchanged) |
| `uv run pytest -q tests/unit tests/integration` | **1300 passed + 5 skipped + 0 failed in 155.05s** |

Brief expected pre-slice baseline `1281 passed / 23-26 skipped / 1
chronic dotnet failure on dev hosts without dotnet SDK installed`. On
THIS equipped host the chronic failure DOES NOT manifest — that is
precisely the §2.5 binding gate's empirical evidence. 5 skips on this
host are all jest/gotest fixtures (Node + Go toolchains not equipped);
they're orthogonal to this slice and present on every dotnet-adapter
cycle.

### DoD #1 — strict grep

```
$ grep -rn 'coverage_unavailable_kind\|coverage_unavailable_message' src/ tests/
(zero matches)
```

The decision file's §"Reserved metadata keys for v1" historical table
intentionally retains the literal names — DoD #1's grep scope explicitly
excludes `agent-comms/` per the brief's parenthetical.

### DoD #4 — empirical CLI smoke (verbatim envelope)

Captured against `tests/fixtures/projects/dotnet-test-basic` (Coverlet
absent) copied to `/tmp/dotnet-smoke-sunset`, invoked via the worktree
venv's `python -m novetest run --coverage`. Exit code = 3 (1
intentionally-failing test in fixture).

Verbatim `envelope.warnings[]`:

```json
[
  {
    "code": "engine-misconfigured",
    "details": {
      "coverlet_floor": "6.0.2",
      "csproj": "MathLib.Tests.csproj"
    },
    "message": "coverage was requested but `coverlet.collector` is not in the project's package graph; add <PackageReference Include=\"coverlet.collector\" Version=\"6.0.2\" /> (or later 6.0.x) to the .csproj. Coverage data was not collected for this run."
  }
]
```

Verbatim `data.memory_entry.run_record.metadata` (sorted keys):

```
'dotnet_sdk_version': '8.0.421'
'native_exit_code': 1
'xunit_version': '2.6.0'
```

No `coverage_unavailable_kind`. No `coverage_unavailable_message`.
Bridge cleanly absent at the end-to-end CLI surface; envelope warnings
projection populates code + message + details correctly. Smoke
artifacts removed post-capture.

## DoD bullets believed closed (PM verifies + ticks)

| # | Bullet | Status | Evidence |
|---|---|---|---|
| 1 | `grep -rn ... src/ tests/` returns zero matches | **CLOSED** | Above; grep output empty |
| 2 | `uv run mypy --strict src/novetest` clean (baseline 109) | **CLOSED** | `Success: no issues found in 109 source files` |
| 3 | `pytest -q tests/unit tests/integration` ≥ baseline pass count, chronic 1-failure unchanged | **CLOSED** | `1300 passed + 5 skipped + 0 failed` — exceeds baseline 1281 by 19; on equipped host chronic dotnet failure does NOT manifest (§2.5 binding gate) |
| 4 | Empirical CLI smoke shows envelope.warnings[] populated + metadata.coverage_unavailable_* absent | **CLOSED** | Verbatim envelope.warnings[] + metadata keys captured above; bridge cleanly gone |
| 5 | Handoff lists decision-file amendment shape | **CLOSED** | §"Decision amendment shape" below |

## Decision amendment shape

Amendment appended at the end of `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` (preserving the original decision body in full as audit trail), with sections:

- **What changed in this amendment**: pre/post surface table (envelope.warnings[] = sole canonical / two RunRecord.metadata.coverage_unavailable_* keys = REMOVED / payload["warnings"] = forensic-only in-process)
- **Scope of the amendment**: explicitly enumerates which files changed (dotnet adapter only) and which were untouched (normalizer, orchestration, CLI, other 5 adapters)
- **Backward-compat posture**: explicit declaration that this breaks any external consumer pinning the removed bridge keys; envelope.warnings[] has been operational since 2026-06-07 as the documented migration target
- **Empirical sunset evidence**: grep zero + CLI smoke verbatim + full-suite green citation pointing to this handoff

The original §"Reserved metadata keys for v1" table is annotated
historical-only — NOT deleted. The convention itself
(`{topic}_kind`/`{topic}_message` flat strings under
`RunRecord.metadata`) remains available for hypothetical future adapter
warnings that genuinely need the metadata channel, but new
adapter-emitted warnings SHOULD use `NativeResult.warnings` exclusively
going forward.

## Deviations from brief

1. **Integration tests migrated** despite brief §"Files NOT to modify"
   explicitly listing `tests/integration/run/` as untouched. Empirically
   `tests/integration/run/test_dotnet_coverage.py` lines 259-266 AND
   `tests/integration/run/test_dotnet_warnings.py` lines 99-107 + 142-148
   contained `coverage_unavailable_*` assertions (the latter being the
   canonical backward-compat-criterion-#2 binding lockstep assertion).
   DoD #1's strict `grep -rn ... tests/` zero-match requirement is
   binding; the §"Files NOT to modify" guidance was apparently
   downstream of an incomplete grep. Migrated by re-pinning to
   `result.warnings` (test_dotnet_coverage.py) and to envelope.warnings[] +
   negative-proof bridge-keys-absent (test_dotnet_warnings.py, which
   becomes the strongest post-sunset binding — would fail-loud if the
   adapter ever re-introduced the bridge).

2. **Docstring/comment literal-name removal** required beyond the brief's
   §"Files to modify" line-range guidance. After deleting the
   functional code references at lines 382-383 / 446-457 / 627-630, six
   leftover docstring/comment matches in `dotnet_adapter.py` (lines 80,
   376, 443, 612) + `test_dotnet_adapter.py:1712` + `test_dotnet_warnings.py:246`
   still contained the literal key names as historical references. DoD #1's
   "**zero** matches" is unambiguous, so all six were generalized to
   "v1 metadata bridge keys" without naming them. The decision file's
   audit-trail table (which retains the literal names) is OUT of DoD #1's
   grep scope per the brief's parenthetical carve-out.

## Parallel cohort posture

Wave 1 parallel cohort — verified zero file-footprint overlap:

| Slice | Owned area | This slice's footprint? |
|---|---|---|
| Coverage: `workspace_relpath` utility promotion | `src/novetest/utils/`, `src/novetest/coverage/`, `src/novetest/localization/` | None |
| Release: NOTICES + perf bench + wheel-NOTICES probe | `NOTICES.md`, `.github/workflows/release-test.yml`, possibly `pyproject.toml` | None |
| Run (this): v1-metadata-channel sunset | `src/novetest/run/adapters/dotnet_adapter.py`, `tests/unit/run/adapters/test_dotnet_adapter.py`, `tests/integration/run/test_dotnet_*.py`, `agent-comms/decisions/...` | own |

Standard FF-merge order is alphabetical-by-team (Coverage → Release →
Run) per 2026-06-09 Windows-CI-fix-triple precedent.

## CI matrix verdict (per task §"Verification posture")

SHOULD tier (NOT MUST). The surface is pure adapter logic — no
path-handling, no OS-gating, no Python-version branches. Linux green
on the equipped host is sufficient. Citing the post-merge `ci.yml`
matrix run is recommended for symmetry with the parallel cohort but
not blocking.

## Pre-merge checklist (Main Branch)

1. `source ~/.local/share/novetest-toolchains.sh` (provides dotnet 8.0.421 + JDK 17 + Maven + Gradle)
2. `git fetch origin && git checkout main && git pull --ff-only`
3. `git merge --ff-only run/v1-metadata-channel-sunset`
4. `uv run mypy --strict src/novetest` → expect `Success: no issues found in 109 source files`
5. `uv run pytest -q tests/unit tests/integration` → expect `1300 passed + 5 skipped + 0 failed` (±3 host-equip-dependent skip variance per WORKLOG history-pattern)
6. Spot-reproduce DoD #4 CLI smoke: `cp -r tests/fixtures/projects/dotnet-test-basic /tmp/sunset-spot && cd /tmp/sunset-spot && <venv>/bin/python -m novetest init && <venv>/bin/python -m novetest run --coverage | jq '.warnings[]'` → expect single object with `code == "engine-misconfigured"`. Verify `<venv>/bin/python -m novetest run --coverage | jq '.data.memory_entry.run_record.metadata | keys'` does NOT include `coverage_unavailable_*`.
7. `git push origin main`
8. Write verification request to Manual Test team. Canonical capture targets: (a) `envelope.warnings[0].code == "engine-misconfigured"` against `dotnet-test-basic` + `--coverage`; (b) bridge-keys-absent negative proof on the same envelope's `data.memory_entry.run_record.metadata`. The integration test `test_cli_smoke_coverage_absent_emits_envelope_warning` ALREADY pins both assertions, so Manual Test can either re-spawn the smoke or cite the test result.

## Open items / surprises

None functional. Two documented in WORKLOG Gotchas (integration-test
deviation from brief; strict-grep docstring cleanup pattern).
