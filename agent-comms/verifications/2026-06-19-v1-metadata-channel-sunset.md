---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready-for-verification
created: 2026-06-19
slug: v1-metadata-channel-sunset
merged_commit: d5b4242
merged_tip: d5b4242
source_handoffs:
  - agent-comms/handoffs/run-team-2026-06-19-v1-metadata-channel-sunset.md
related:
  - agent-comms/tasks/run-team-2026-06-19-v1-metadata-channel-sunset.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
  - agent-comms/history/2026-06-07-parallel-pair-envelope-warnings-and-dotnet-cobertura-derive.md
host: equipped (per `decisions/2026-06-08-equip-and-exercise §1` MUST tier — §2.5 file-glob fires for `dotnet_adapter.py` + `test_dotnet_adapter.py`; equipped Linux host with dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5)
---

# Verification — v1 `coverage_unavailable_kind/_message` metadata channel sunset (dotnet adapter)

## TL;DR

**Merged commit**: `d5b4242` (single bundled commit — adapter sunset + 5 test-site migration + decision-file amendment + WORKLOG + handoff). **Merged tip**: `d5b4242` (Wave 1 cohort tip — Coverage `9c5abbf` + Release `f4523da` + this slice on top after WORKLOG conflict resolution).

Removes the v1 metadata-bridge keys (`coverage_unavailable_kind` + `coverage_unavailable_message`) from `dotnet_adapter.py`'s `RunRecord.metadata` write site. The Option C envelope-warnings-projection (shipped 2026-06-07) has been the operational user-visible surface for 12 days; the one-release-cycle backward-compat window declared by `decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md` §"Acceptance criteria for Option C slice" #2 expired cleanly. **`envelope.warnings[]` is now the single canonical surface** for adapter-emitted warnings.

7 files changed: 1 src (`dotnet_adapter.py` -98/+5), 3 tests (1 unit + 2 integration migrated), 1 decision-file amendment, WORKLOG, handoff. Net src LOC: ~−25 (bookkeeping cleanup). Net test LOC: ~+15 (positive shape assertions verbose).

Your job (Manual Test): verify the **bridge keys are verifiably ABSENT** at the merged tip's CLI envelope + **`envelope.warnings[]` populates correctly** for the canonical engine-misconfigured path + (lower priority) the decision-file audit trail is preserved.

## Source handoff consumed

- `agent-comms/handoffs/run-team-2026-06-19-v1-metadata-channel-sunset.md` (committed in `d5b4242` alongside the code sunset + decision amendment)

## Pre-merge empirical anchors (re-verified at merged tip `d5b4242`)

### Anchor A — DoD #1 strict grep (zero literals in src/ + tests/)

```bash
$ grep -rn "coverage_unavailable_kind\|coverage_unavailable_message" src/ tests/
(exit=1, no matches)
```

Zero hits. Six historical-reference matches (4 in `dotnet_adapter.py` docstrings + 2 in test docstrings) were generalized to "v1 metadata bridge keys" per Run handoff §"Deviations from brief" Gotcha #2.

### Anchor B — Decision-file audit trail preserved

```bash
$ grep -c "coverage_unavailable_kind\|coverage_unavailable_message" agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
11
```

11 literal references retained in the decision file's audit-trail (§"Reserved metadata keys for v1" historical table + Amendment 2026-06-19 pre/post surface table). DoD #1's grep scope explicitly excludes `agent-comms/` per the brief's parenthetical carve-out.

### Anchor C — CLI smoke envelope (verbatim at merged tip)

Source: `tests/fixtures/projects/dotnet-test-basic` (Coverlet absent) copied to `/tmp/nv-cap-run-dotnet`. Invoked via `/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage` on equipped host.

Exit code: **3** (1 intentionally-failing test in fixture).

`envelope.warnings[]` (verbatim from `/tmp/nv-envelope.json`):

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

`data.memory_entry.run_record.metadata` keys (sorted):
```python
['dotnet_sdk_version', 'native_exit_code', 'xunit_version']
```

**Zero `coverage_unavailable_*` keys.** Bridge cleanly absent at end-to-end CLI surface. Envelope-warnings projection populates code + message + details correctly.

`data.coverage_outcome.kind` = `"unavailable"` (consistent with coverage-not-collected per Coverlet-absent path; the coverage outcome surface is sibling to memory_entry, not under run_record).

### Anchor D — Pre-merge gate (combined Wave 1 cohort on equipped host)

```bash
$ source ~/.local/share/novetest-toolchains.sh
[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5

$ uv run mypy
Success: no issues found in 109 source files

$ uv run pytest -q tests/unit tests/integration
1303 passed, 5 skipped in 147.60s (0:02:27)
37 snapshots passed.
```

§2.5 binding gate satisfied: equipped host, full dotnet adapter exercised, zero failures. The chronic-dotnet failure that manifests on non-equipped hosts (`AdapterInvocationError: dotnet not found on PATH`) is SUPPRESSED here — that is the §2.5 evidence.

## Verification scenarios (4 surface + 2 decision-trail + 2 negative-proof)

### Scenario A — DoD #1 grep zero re-confirmation

```bash
cd /home/yjshin/dev/Nove-Test
grep -rn "coverage_unavailable_kind\|coverage_unavailable_message" src/ tests/
echo "exit=$?"
```

Expected: zero output, exit 1.

**PASS** if zero matches; **FAIL** if any hit (would signal the sunset is incomplete or a regression re-introduced the bridge).

### Scenario B — CLI smoke envelope.warnings[] populated + bridge absent (the critical negative proof)

```bash
source ~/.local/share/novetest-toolchains.sh
rm -rf /tmp/nv-verify-run && cp -r tests/fixtures/projects/dotnet-test-basic /tmp/nv-verify-run
cd /tmp/nv-verify-run
/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest init >/dev/null
/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest run --coverage > /tmp/nv-verify-envelope.json
echo "exit=$?"
/home/yjshin/dev/Nove-Test/.venv/bin/python -c "
import json
e = json.load(open('/tmp/nv-verify-envelope.json'))
print('exit code (re-print):', 'see prior echo')
print()
print('envelope.warnings[0].code:', e['warnings'][0]['code'])
print('envelope.warnings[0].details:', e['warnings'][0]['details'])
print()
md = e['data']['memory_entry']['run_record']['metadata']
print('metadata keys:', sorted(md.keys()))
print('bridge keys present?', 'coverage_unavailable_kind' in md or 'coverage_unavailable_message' in md)
"
rm -rf /tmp/nv-verify-run
```

Expected:
- exit code: 3
- `envelope.warnings[0].code` == `"engine-misconfigured"`
- `envelope.warnings[0].details` == `{"coverlet_floor": "6.0.2", "csproj": "MathLib.Tests.csproj"}`
- metadata keys == `['dotnet_sdk_version', 'native_exit_code', 'xunit_version']` (3 keys, NO `coverage_unavailable_*`)
- bridge keys present? `False`

**PASS** if all 4 conditions hold; **FAIL** if any (especially bridge-present-True) — would invalidate the sunset.

### Scenario C — Integration test binding survives merge

```bash
.venv/bin/python -m pytest -q tests/integration/run/test_dotnet_warnings.py::test_cli_smoke_coverage_absent_emits_envelope_warning tests/integration/run/test_dotnet_coverage.py 2>&1 | tail -5
```

Expected: tests pass. These two integration tests are the post-sunset binding (Run handoff §"Deviations from brief" Gotcha #1 — `test_dotnet_warnings.py::test_cli_smoke_coverage_absent_emits_envelope_warning` is now the negative-proof "bridge MUST be absent" assertion; `test_dotnet_coverage.py` happy-path uses `not any(w.code == "coverlet-absent-or-stale" for w in result.warnings)`).

**PASS** if both green; **FAIL** if either red — would signal the migration is broken.

### Scenario D — Unit test class migration

```bash
.venv/bin/python -m pytest -q tests/unit/run/adapters/test_dotnet_adapter.py::TestEnvelopeSafetyNet 2>&1 | tail -10
```

Expected: 5 tests passed in the `TestEnvelopeSafetyNet` class (`test_warnings_carry_*`, `test_warnings_empty_when_probe_succeeds`, `test_warnings_empty_on_non_coverage_path`, `test_xunit_v3_path_emits_deferred_warning_not_coverlet_absent`, plus the legacy `test_restore_failure_tolerated_proceeds_to_probe` outside the class). Per Run handoff §"Files written / modified" table for `test_dotnet_adapter.py`.

**PASS** if all 5 green; **FAIL** if any red (would signal class rename + assertion migration drifted).

### Scenario E — Decision file Amendment 2026-06-19 present

```bash
grep -n "Amendment 2026-06-19\|## Amendment" agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
wc -l agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
```

Expected:
- At least one line matches `Amendment 2026-06-19`.
- File length increased by ~80 lines vs pre-slice (the amendment appended section).

Run handoff §"Decision amendment shape" lists 4 amendment subsections: pre/post surface table, scope, backward-compat posture, empirical sunset evidence. PM may eyeball that the 4 subsections are present.

**PASS** if amendment block present; **FAIL** if amendment missing (would signal the decision-file audit trail isn't pinned).

### Scenario F — Decision file historical literals preserved (audit trail intact)

```bash
grep -c "coverage_unavailable_kind\|coverage_unavailable_message" agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
```

Expected: 11 hits (per Anchor B above) — the §"Reserved metadata keys for v1" historical table + amendment pre/post surface table together retain the literal references for audit.

**PASS** if ≥ 5 hits (rough lower bound; the exact 11 may shift slightly if amendment wording changes); **FAIL** if 0 (would signal the audit trail was erroneously purged).

### Scenario G — Wave 1 cohort merge diff scope

```bash
git log --oneline 42f6a32..d5b4242
git diff --stat 42f6a32..d5b4242
```

Expected: 5 commits forming the Wave 1 cohort:
- `9c5abbf` Coverage refactor
- `24477ee` Release work
- `f4523da` Release handoff
- `d5b4242` Run sunset (this slice)
- (plus any verification commits Main Branch added on top before push)

Run's footprint (4th commit): 7 files (1 src, 3 tests, 1 decision, WORKLOG, handoff).

**PASS** if cohort shape matches; **FAIL** if any unexpected commit interleaved.

### Scenario H — CI matrix verdict (POST-PUSH)

§4 amendment 2026-06-19 SHOULD tier (not MUST — pure adapter logic, no path-handling or OS-gating). The post-merge `ci.yml` matrix run is recommended for symmetry with the parallel cohort but not blocking for this slice's sign-off.

```bash
# After push lands:
gh run list --workflow ci.yml --branch main --limit 5
# Find the run for SHA d5b4242 (or the verification commit on top, which is the actual push tip)
gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'
```

Expected: 9/9 matrix cells SUCCESS (3 OSes × 3 Pythons) + non-blocking perf lane.

**PASS** if 9/9 green; **FAIL** if any cell RED — would suggest a cross-OS regression slipped past the equipped-Linux gate (low expected given pure adapter logic touched).

## Critical edge probes

1. **`engine_version` is the dotnet SDK version, NOT xUnit version**: `metadata.dotnet_sdk_version == "8.0.421"` and `metadata.xunit_version == "2.6.0"`; `run_record.engine_version` (top-level) == `"8.0.421"` (dotnet SDK). This is the established convention from the 2026-06-06 .NET adapter cycle; Flag if the assignment flips.

2. **`coverage_outcome.kind` lives at `data.coverage_outcome.kind`, NOT under `run_record`**: empirically observed at merged tip; sibling to `data.memory_entry`, not nested. If a future cycle moves it, this verification's Anchor C wording needs amendment. Currently the contract holds.

3. **Verbatim CLI capture used `/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest`, not `uv run novetest`**: per GOTCHAS.md #4 (`uv run --with /local-path` may serve a stale wheel against a fixture project's own pyproject.toml). The venv invocation is the GOTCHAS-sanctioned way to ensure the merged-tip code is exercised; Manual Test should use the same pattern.

4. **`engine-misconfigured` is the warning code, NOT `coverlet-absent-or-stale`**: the latter is the internal `AdapterWarning.code` constant in the dotnet adapter; the former is the public envelope-facing code projected by `_adapter_to_envelope_warnings` in `cli/app.py`. Both names appear in Run handoff text; only `engine-misconfigured` should appear in the envelope's `warnings[].code` field. Flag if the envelope surfaces the internal name (would signal projection broke).

5. **The 2 docstring/comment generalizations (Run Gotcha #2) preserve historical intent**: 4 site comments in `dotnet_adapter.py` + 2 in tests now read "v1 metadata bridge keys" instead of naming the literal keys. This is per DoD #1 strict zero-match. Future audits looking for the literal key names should grep `agent-comms/decisions/2026-06-06-...` (audit trail), NOT src/tests (intentionally sanitized).

6. **AdapterWarning ↔ envelope projection is unchanged**: the Option C projection helper `_adapter_to_envelope_warnings` (in `cli/app.py` per 2026-06-07 history) was not touched by this slice. The sunset only removed the v1 bridge write site in `dotnet_adapter.py`; the projection that turns `NativeResult.warnings` (canonical) into `envelope.warnings[]` (user-facing) is the same surface that has been operational for 12 days.

7. **Wave 1 cohort parallel-merge soundness**: zero file-overlap across the 3 slices (Coverage `utils/coverage/localization`, Release `NOTICES.md` + workflow + foundations.md, Run `dotnet_adapter.py` + dotnet tests + decision amendment). Only WORKLOG overlapped; resolved with incoming-on-top at Run's rebase (Run entry above Coverage entry, separated by `---`). Both entries dated 2026-06-19.

8. **Backward-compat break is documented + intended**: the v1 bridge keys had a one-release-cycle window per 2026-06-06 decision; window expired 2026-06-07 + 12 days = 2026-06-19 (today). Any external consumer pinning `metadata.coverage_unavailable_*` MUST migrate to `envelope.warnings[].{code,message,details}`. This is the canonical Option C migration target documented since 2026-06-07.

## Anything that wasn't obvious during merge

1. **Run worktree rebase produced a WORKLOG conflict** at the top-of-file new-entry region (both Coverage and Run added entries dated 2026-06-19; Coverage merged first, so its entry was already at top when Run rebased). Resolved via Python regex helper with `incoming-on-top` convention: Run's entry on top, `---` separator, Coverage's entry below. Run commit re-applied cleanly as `d5b4242`.

2. **Pre-merge gate on equipped host** (per §2.5 binding for adapter cycles): 1303 passed + 5 skipped + 0 failed in 147.60s; mypy 109 files clean. The 5 skips are jest/Node + Go SDK fixture skips (orthogonal). Zero dotnet failures — that's the §2.5 evidence.

3. **CLI smoke envelope re-captured at merged tip**, not just trusted from Run's pre-merge probe. The byte-equivalent capture confirms the merge did not perturb the envelope structure. The capture matches Run handoff's pre-merge sample verbatim.

4. **GOTCHAS.md #4 invoked**: the CLI smoke used `/home/yjshin/dev/Nove-Test/.venv/bin/python -m novetest` (not `uv run novetest`), with `cd /tmp/nv-verify-run` to the SuT directory + `source ~/.local/share/novetest-toolchains.sh` first. Manual Test should mirror this incantation.

5. **No worktree cleanup before push**: 3 worktrees (`/home/yjshin/dev/novetest-workspace-relpath`, `/home/yjshin/dev/novetest-notices-pip-deps-and-perf-bench-bundle`, `/home/yjshin/dev/aispace/novetest-v1-metadata-channel-sunset`) + 3 branches remain at moment Manual Test reads this. Cleanup happens AFTER successful push per charter; the worktrees are read-only for Manual Test's purpose (verification targets the merged tip on `main`).
