---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-19
slug: workspace-relpath-utility-promotion
worktree: /home/yjshin/dev/novetest-workspace-relpath
branch: coverage/workspace-relpath-utility-promotion
base_commit: 42f6a32
related:
  - agent-comms/tasks/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md
  - agent-comms/history/2026-06-09-windows-ci-fix-triple-coverage-localization-run.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/decisions/2026-06-08-equip-and-exercise-default-verification-posture.md
parallel_cohort:
  - agent-comms/tasks/run-team-2026-06-19-v1-metadata-channel-sunset.md
  - agent-comms/tasks/release-team-2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
---

# Handoff: workspace-relpath-utility-promotion (Coverage + Localization charter cross-over)

## TL;DR

Lifted `coverage/_paths.py` (Coverage-private workspace-relpath helpers introduced 2026-06-09)
to the project-wide `utils/path_utils.py` surface and migrated the Localization
`failure_proximity._normalize_to_workspace_relative` inside-branch to delegate to
the shared utility. Closes Future-cycle queue item #6. Byte-equivalent refactor;
envelope diff 1406 bytes identical modulo volatile timestamps. Ready for FF-merge.

## Worktree details

- Path: `/home/yjshin/dev/novetest-workspace-relpath`
- Branch: `coverage/workspace-relpath-utility-promotion`
- Base: `42f6a32` (`main` HEAD at cycle dispatch)
- One commit pending (code + WORKLOG bundled per pre-commit hook gate)

## Files changed (9)

| File | Change | LOC |
|---|---|---|
| `src/novetest/utils/path_utils.py` | NEW | +155 |
| `src/novetest/utils/__init__.py` | MODIFIED (was empty; now re-exports 3 names) | +19 |
| `src/novetest/coverage/_paths.py` | **DELETED** | −112 |
| `src/novetest/coverage/lcov_parser.py` | MODIFIED (import line rewrite) | ±0 |
| `src/novetest/coverage/istanbul_parser.py` | MODIFIED (import line rewrite) | ±0 |
| `src/novetest/coverage/cobertura_parser.py` | MODIFIED (import line rewrite) | ±0 |
| `src/novetest/localization/failure_proximity.py` | MODIFIED (delegate inside-branch to utility; drop `import os`; docstring update) | −16 / +6 |
| `tests/unit/coverage/test_paths.py` | **DELETED** (relocated) | −137 |
| `tests/unit/utils/test_path_utils.py` | NEW (7 relocated + 3 new wrapper tests) | +170 |
| `WORKLOG.md` | NEW entry top of file | +14 |
| `agent-comms/handoffs/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md` | NEW (this file) | +200 |

Net production code: **−112 + 155 + 19 − 10 = +52 LOC**.
Net test code: **−137 + 170 = +33 LOC** (the 3 new wrapper tests + slight docstring expansion).

## `coverage/_paths.py` disposition (DoD #7)

**Chose DELETE + rewrite imports**, not re-export shim.

- Callsite count: `grep -rn "from novetest.coverage._paths\|from novetest.coverage import _paths" src/ tests/` returned 4 hits (3 src parsers + 1 test).
- Below the brief's `> 5 hits` threshold for retaining the shim.
- Total LOC diff is lower for delete-and-rewrite than shim-plus-original (shim would have meant 112 LOC stays + 3 import lines change; delete means 112 LOC removed + 3 import lines change; the latter is purely additive on the canonical surface).
- Test relocated `tests/unit/coverage/test_paths.py` → `tests/unit/utils/test_path_utils.py` (DoD #1 / brief §3 list).

## Verification matrix

### Mypy
```
uv run mypy
→ Success: no issues found in 109 source files
```
Baseline 109 (+/- 1). Net module count: +1 `path_utils.py` − 1 `_paths.py` = 0. The empty `utils/__init__.py` was already a module (mypy tracks `__init__.py`).

### Pytest
```
uv run pytest -q tests/unit tests/integration
→ 1294 passed, 13 skipped, 1 failed in 103.21s
```
The 1 failure is `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
with `AdapterInvocationError: `dotnet` not found on PATH` — the chronic dotnet host-equip skip the brief explicitly excepts:
> "The 1 chronic dotnet host-equip failure stays unchanged." (DoD #5)

37 snapshots passed. `git status --porcelain tests/ | grep -i snapshot` → empty (DoD #5 second clause: zero snapshot file modifications).

### DoD contract greps
```
# DoD #2 — no internal _paths imports remain
grep -rn "from novetest.coverage._paths import\|from novetest.coverage import _paths" src/ tests/
→ <empty>

# DoD #3 — no inline implementation in Localization
grep -rn "os.path.relpath\|relative_to(workspace_root)" src/novetest/localization/
→ src/novetest/localization/failure_proximity.py:543:        file_path.relative_to(workspace_root)
   src/novetest/localization/failure_proximity.py:579:    encapsulates the three-step ``relative_to → os.path.relpath →
   src/novetest/localization/failure_proximity.py:583:    ``os.path.relpath`` defensively (the ``_is_outside_workspace`` gate
   src/novetest/localization/failure_proximity.py:630:    # ``relative_to → os.path.relpath → drive-stripped POSIX`` resolution
```
Line 543 is inside `_is_outside_workspace` — the Localization policy classifier (`try ... .relative_to(...) ; except ValueError: return True`). NOT a try/except/relpath fallback (returns `bool`, doesn't call relpath). Brief out-of-scope §4 preserves this. Lines 579/583/630 are all docstring/comment text. ZERO function-body try/except/relpath blocks remain.

### DoD #6 — empirical envelope byte-identity

Probe script `/tmp/probe_envelope.py` mirrors `tests/integration/localization/test_failure_proximity_e2e.py::test_failure_proximity_ranks_buggy_file_top` and writes the persisted `localization_findings.json` to `/tmp`.

Pre-slice run (against `main` HEAD `42f6a32`):
```
raw bytes: 1406 -> /tmp/envelope_pre.json
```

Post-slice run (against this worktree HEAD):
```
raw bytes: 1406 -> /tmp/envelope_post.json
```

Diff:
```
$ diff /tmp/envelope_pre.json /tmp/envelope_post.json
5,6c5,6
<     "run_id": "01KVG2GGVFCW2HEARH2VBHJE03",
<     "created_at": 1781877195631
---
>     "run_id": "01KVG2GNJ97R2WB9CHVF4PJN7W",
>     "created_at": 1781877200457
41,42c41,42
<             "run_id": "01KVG2GGVFCW2HEARH2VBHJE03",
<             "created_at": 1781877195631
---
>             "run_id": "01KVG2GNJ97R2WB9CHVF4PJN7W",
>             "created_at": 1781877200457
52c52
<   "derived_at": 1781877195933,
---
>   "derived_at": 1781877200764,
```
Both runs: **1406 bytes identical**. All 3 diff hunks are volatile-field expected differences:
- `run_id` (ULID, per-run identity, varies)
- `created_at` (RunReference creation timestamp, varies)
- `derived_at` (LocalizationFinding derivation timestamp, varies — the "verifiedAt analogue" the brief calls out)

Crucially: the `entries[*].code_location.file` field — the load-bearing envelope shape this refactor's policy preservation guarantees — is byte-identical pre and post.

## DoD bullets believed closed

1. ✓ `src/novetest/utils/path_utils.py` exists; exports 3 public names. `utils/__init__.py` re-exports the same 3.
2. ✓ `grep -rn "from novetest.coverage._paths"` returns zero results (delete path chosen).
3. ✓ Localization grep returns only docstring/comment hits + the policy classifier (NOT a try/except/relpath block).
4. ✓ Mypy clean at 109 source files.
5. ✓ Pytest 1294 passed + 13 skipped + 1 chronic-dotnet-skip; zero snapshot file modifications.
6. ✓ Envelope byte-identity proven empirically: 1406 bytes identical; diff shows only `run_id` + `created_at` + `derived_at` volatile differences.
7. ✓ Disposition documented (DELETE path chosen on 4-callsite count).

**CI-pending (handed off to Main Branch)**: verification posture §"CI matrix verdict criterion" — 9/9 ci.yml matrix SUCCESS on merged HEAD. See "Main Branch action items" below.

## Main Branch action items

1. **FF-merge** `coverage/workspace-relpath-utility-promotion` to `main` (alphabetical-by-team Wave 1 cohort → Coverage merges FIRST among the 3 cycle slices: coverage / release / run).
2. **CI matrix verdict citation (binding per §4 amendment 2026-06-19)**: This slice qualifies under §4.1 #1 (touches `pathlib.Path` ops + `os.path` calls + workspace-relative path conversion). After merge, run `gh workflow run ci.yml --ref main` and capture the resulting workflow run number; cite it in the Manual Test verification request as the cross-OS empirical assurance for the new `path_utils.py` surface.
3. **Verification request** to Manual Test with the ci.yml URL + a request for Linux + macOS smoke on the merged HEAD. Windows cross-drive re-validation is provided by the existing fixture-driven CI tests (no new manual probe needed — the cross-drive case is fixture-mocked via `monkeypatch.setattr(os.path, "relpath", _raising_relpath)`, fully repeatable on every OS).

## Design deviations (informational; no PM intervention needed unless flagged)

| # | Brief expected | We did | Why |
|---|---|---|---|
| D1 | Coverage chooses delete vs shim | Chose DELETE | 4 callsites < 5 threshold; lower LOC diff |
| D2 | `workspace_relpath` semantics | `Path(to_workspace_relative_posix(...))` one-liner | Exactly matches brief's directive |
| D3 | Move tests from `tests/unit/coverage/test_paths.py` | DELETED old, NEW at `tests/unit/utils/test_path_utils.py` | Per brief §3 instruction |
| D4 | Localization mock target if any test mocked `_normalize_to_workspace_relative` | NO test mocks `_normalize_to_workspace_relative` directly (only `_is_outside_workspace`, which stays); no mock updates needed | Verified via `grep monkeypatch tests/unit/localization/` — only `_is_outside_workspace` is mocked |
| D5 | `import os` posture in failure_proximity | REMOVED entirely (was only used by the inline `os.path.relpath` fallback; now delegated to utility) | Surgical — no other `os.*` use in the module |

## Informational questions to PM (no blockers)

- **Q1**: Should we add `path_utils.py` to a future "shared utility surface" decision doc, or is the implementation-by-WORKLOG record sufficient? (No action needed unless PM wants a formal decision pin.)
- **Q2**: The `_is_outside_workspace` helper remains a Localization-specific policy. If Run/Memory teams later need an "outside-workspace" classifier with the SAME semantics, should we promote it as a 4th `path_utils.py` export, or keep it Localization-internal? (Defer to first actual cross-engine need.)
- **Q3**: `os.path.relpath` literal in DoD #3 grep matches docstring text in 3 lines. Should the grep pattern be tightened (e.g. exclude comment/docstring lines) for future DoD verifications, or is the human-eye exemption acceptable? (Current handoff documents the exemption per-hit.)

## Risks

- **Low risk**: byte-equivalent refactor; envelope diff confirmed. No envelope-shape changes; no policy changes; no engine adapter touch.
- **CI matrix gate is the load-bearing assurance** (per verification posture §"CI matrix verdict criterion"); Linux dev-host cannot exercise the cross-drive Windows fallback. Main Branch must capture the ci.yml run number on merged HEAD.

## Suggested commit message

```
refactor(utils): promote coverage/_paths.py to utils/path_utils.py + migrate Localization

Lift `to_workspace_relative_posix` + `relpath_or_drive_stripped` (and
the `_WINDOWS_DRIVE_PREFIX_RE` constant) from the Coverage-private
namespace at `src/novetest/coverage/_paths.py` to the project-wide
`src/novetest/utils/path_utils.py` surface, and add a third public
function `workspace_relpath(path, workspace_root) -> Path` as a
Path-typed convenience wrapper.

Migrate `src/novetest/localization/failure_proximity.py`'s
`_normalize_to_workspace_relative` inside-workspace branch to delegate
to the shared `to_workspace_relative_posix` utility. The B2-2
outside-workspace policy (failure_proximity stdlib frames remain
absolute) is preserved unchanged — the `_is_outside_workspace`
classifier is a Localization-specific POLICY on TOP of the path
utility, not a path-utility behavior.

Coverage `_paths.py` callsite count was 4 (3 src parsers + 1 test);
below the brief's >5 threshold for retaining a re-export shim, so the
disposition is delete + rewrite imports. Tests relocated to
`tests/unit/utils/test_path_utils.py` with 3 new tests covering the
`workspace_relpath` Path-typed wrapper.

CEO-approved charter cross-over (third application of the in-cycle
Option-A exception pattern) per task brief
`agent-comms/tasks/coverage-team-2026-06-19-workspace-relpath-utility-promotion.md`.
Closes Future-cycle queue item #6 from the 2026-06-09 MVP
release-ready sign-off backlog.

Verification:
- `uv run mypy` → 109 files clean
- `uv run pytest -q tests/unit tests/integration` → 1294 passed +
  13 skipped + 1 chronic-dotnet-skip; zero snapshot file modifications
- Empirical envelope byte-identity (`failure_proximity` E2E
  `localization_findings.json`): 1406 bytes identical pre + post,
  diff shows only volatile `run_id` + `created_at` + `derived_at`
  differences

CI matrix verdict citation (§4 amendment 2026-06-19) deferred to
Main Branch post-merge ci.yml run on merged HEAD.
```
