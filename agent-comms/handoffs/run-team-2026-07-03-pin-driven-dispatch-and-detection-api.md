---
from: novetest-run-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-03
slug: pin-driven-dispatch-and-detection-api
related:
  - agent-comms/tasks/run-team-2026-07-03-pin-driven-dispatch-and-detection-api.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
---

# Handoff: Run — pin-driven dispatch + single-source detection API

## Worktree

- **Path**: `/home/yjshin/dev/aispace/novetest-pin-driven-dispatch`
- **Branch**: `run-team/pin-driven-dispatch-and-detection-api`
- **Base**: main @ `5e7d5b5`
- **Status**: ready — NOT self-merged, NOT pushed.

## Files written / modified

| File | Change |
|---|---|
| `src/novetest/run/engine_selector.py` | REWRITTEN — `_ENGINE_MARKER_TABLE` single source of truth (canonical REQ-RUN-006 order; dotnet row = glob markers); `detect_engine_candidates` moved in from readiness; `_marker_evidence` unifies literal + glob matching; `select_native_engine` = first candidate; `list_supported_engine_pairs` derived from table |
| `src/novetest/run/readiness.py` | Detection + marker constants + `_existing_markers`/`_glob_markers` (pre-existing dead code)/`_glob_dotnet_markers` REMOVED; `assess_engine_readiness` probes `candidates[0]` via NEW `_probe_candidate` + UNORDERED `_READINESS_PROBES` registry (the 6-branch hand-ordered if-chain — the §4.1 bug — is deleted); NEW `probe_engine` |
| `src/novetest/run/engine.py` | `execute` gains `engine: tuple[str, str] | None = None`; pinned path gates via `probe_engine` then dispatches directly; `None` path byte-identical legacy auto-detect with removal TODO |
| `src/novetest/run/__init__.py` | `probe_engine` exported; `detect_engine_candidates` now imported from engine_selector (package-path import for consumers unchanged); stale docstring refreshed |
| `design/interace-contract/run.md` | `execute(test_target, engine?)` row; `detect_engine_candidates` row rewritten (init-facing, canonical order, D1 wiring); NEW `probe_engine` row; detection-order-guarantee note |
| `design/workflows/run.md` | ⚠️ NOT in the brief's pinned file list — see §Deviations. 3 rows realigned (`execute` branch on pin, `select_native_engine` → detect, NEW `probe_engine` row) |
| `tests/unit/run/test_engine_selector.py` | Detection tests moved in from test_readiness 1:1 + NEW: dual-marker canonical order, all-six-markers order == `list_supported_engine_pairs()`, dotnet root-relative evidence, divergence guard, §4.1 selection test |
| `tests/unit/run/test_readiness.py` | Detection tests moved out; NEW: §4.1 assess/select agreement, tooling-only `package.json` candidate-but-not-ready, probe-targets-named-engine, vanished-marker TOCTOU, unsupported-pair raise |
| `tests/unit/run/test_engine.py` | NEW: pinned execute skips detection (bomb-patched detection seams), pinned-not-ready raises pre-subprocess, pinned end-to-end real pytest run, pinned-unsupported raises |
| `WORKLOG.md` | New top entry (pasted below) |

## Detection API for Orchestration (final signatures)

All three surfaces are package-exported: `from novetest.run import ...`.

```python
def detect_engine_candidates(project_workspace: Path) -> tuple[EngineCandidate, ...]
```
- Marker scan of ONE directory (plus the dotnet one-level `*/*.csproj` glob). No recursion, no subprocess.
- Returns every matched pair in **canonical priority order** (python, javascript-typescript, java, go, rust, dotnet — the single table's order). Empty tuple when nothing matches.
- `EngineCandidate` fields: `ecosystem: str`, `engine_name: str`, `evidence: tuple[str, ...]` (literal markers in declaration order; glob markers as sorted root-relative paths).
- Note: return type is `tuple[...]`, not the brief's sketched `list[...]` — kept consistent with the codebase's frozen/tuple conventions ("promote/adjust the existing helper"); contents and ordering are exactly as briefed.

```python
async def probe_engine(project_workspace: Path, ecosystem: str, engine_name: str) -> EngineReadinessResult
```
- Readiness of exactly the named engine — no candidate scan, no priority fallback. Same result shape/states as `assess_engine_readiness` (`ready` / `engine-missing` / `engine-misconfigured`).
- Evidence for the pair is re-resolved; may legitimately be `()` (probes carry their own TOCTOU diagnostics — a vanished `go.mod` comes back `engine-misconfigured`, never a crash).
- Pairs outside the six-engine matrix raise `EngineNotSupportedError`. Validate `--engine` at the CLI (D7 `invalid-flag`, exit 2) BEFORE calling; the raise is the programming-error backstop, not a user-input path.
- **D1 ambiguity recipe for init**: `detect_engine_candidates(ws)` → `probe_engine(ws, c.ecosystem, c.engine_name)` per candidate → count `state == "ready"`; ≥2 ready → `engine-ambiguous`; a tooling-only `package.json` with no runnable jest counts as candidate-but-NOT-ready and does not trigger ambiguity (pinned by test `test_probe_engine_tooling_only_package_json_is_candidate_but_not_ready`).

```python
async def execute(test_target, *, artifact_dir, engine: tuple[str, str] | None = None,
                  run_id=None, timeout=600.0, collect_coverage=False)
```
- `engine=(ecosystem, engine_name)` — the store pin or transient `--engine` override (D3). Readiness gates via `probe_engine` (raises `EngineNotReadyError` on non-ready → your existing exit-4 mapping applies unchanged), then dispatches that engine directly. **No marker detection runs.**
- `engine=None` — legacy auto-detect, byte-for-byte. Remove your last `None` caller in the anchored-init slice; the branch then dies in a Run follow-up micro-slice (TODO pinned in `engine.py` referencing your slug).

## Verification

All commands `env -u PYTHONPATH` (host ROS2 PYTHONPATH pollution — pinned host fact):

1. `uv run mypy --strict src/novetest` → **Success: no issues found in 114 source files**.
2. `uv run pytest -q tests/unit tests/integration` → **1361 passed / 3 skipped / 0 failed, 44 snapshots passed** (= 1348 baseline + 13 net-new tests; 3 skips = pre-existing jest/Node host issue, unrelated).
3. `git status --porcelain | grep -i ambr` → empty. **Zero snapshot regen** — the `execute(engine=None)` envelope surface is byte-identical (acceptance criterion "snapshot-pinned" holds via the 44 existing snapshots).
4. Empirical §4.1 proof: `pom.xml`+`go.mod` tmpdir → `detect_engine_candidates` = `[junit, go-test]`; `assess_engine_readiness` context = **junit** (pre-slice: go); `select_native_engine` = junit → readiness and dispatch agree. Pinned by `test_assess_and_select_agree_on_pom_plus_gomod_workspace` + `test_java_outranks_go_in_selection` (deterministic on any host/OS: bare pom.xml lands `engine-misconfigured` with junit context on every path — no JDK, no Maven, no Jupiter, or Windows OS gate).
5. Targeted `tests/unit/run/`: **334 passed**.

## Implementation choices (with rationale)

1. **Detection moved INTO `engine_selector`** (not left in readiness consuming an imported table): `select_native_engine` must consume detection, and readiness already imports engine_selector — the reverse import would be circular. engine_selector is the brief's "natural home"; readiness is now pure probing.
2. **`_READINESS_PROBES` is a dict, deliberately unordered**: order authority lives only in `_ENGINE_MARKER_TABLE`. The registry answers "which probe implements this pair"; `assess_engine_readiness` takes `candidates[0]`. Divergence guard test pins `registry.keys() == list_supported_engine_pairs()`.
3. **Pinned `execute` still gates readiness** (via `probe_engine`, per brief §2 "replacing the scan-until-first-success pattern for pinned flows"): skipping it would regress NFR-RUN-004 — a stale pin would crash inside the native subprocess instead of returning the clean `engine-misconfigured` state / exit-4 envelope. "Do NOT re-detect" is honored: no marker scan decides anything on the pinned path.
4. **Glob-vs-literal markers unified by `"*" in marker`**: dotnet's evidence strings stay byte-compatible with the old `_glob_dotnet_markers` (sorted, root-relative — `root.glob` can't escape root, so the old defensive `ValueError` fallback died with it).

## Deviations from the brief (flagged for PM)

- **`design/workflows/run.md` edited though not in the pinned file list.** The slice made its `execute` / `select_native_engine` workflow rows factually wrong; the file is Run-charter-owned, the fix is 3 table rows. Judged surgical truth-restoration over leaving owned design docs stale. Revert is trivial if PM disagrees.
- **`detect_engine_candidates` returns `tuple`, not `list`** (see API section above).
- **CLAUDE.md's karpathy-guidelines Skill invocation**: this session's toolset carries no Skill tool (harness constraint, same class as GOTCHAS.md's EnterWorktree entry). The four guidelines were applied manually (pre-flight design before code; no new abstractions beyond the two briefed APIs; zero footprint outside charter; every acceptance criterion mapped to a test). No deliverable impact.

## Behavior changes (intentional, decision-mandated)

- Polyglot `java`+`go` (and any workspace where the old readiness chain ranked differently than the selector): readiness now probes what dispatch runs. This is the §4.1 fix, not a regression — pre-slice, such a workspace could be Go-readiness-verified while JUnit was dispatched.
- No other observable change: single-ecosystem workspaces, all envelopes, and all snapshots are byte-identical.

## DoD bullets believed closed (PM verifies and ticks)

Task acceptance criteria — all four closed locally:
1. Full unit + integration green + mypy clean → verification #1/#2 (CI matrix run post-merge is Main Branch/PM's cite).
2. `execute(engine=None)` byte-identical, snapshot-pinned → verification #3.
3. §4.1 demonstrably dead on the pom+go.mod fixture → verification #4.
4. WORKLOG entry + this handoff with final API signatures → done.

No unchecked `delivery-phasing.md` bullets are claimed by this slice (the anchored-pin wave's DoD bookkeeping is PM's cycle-close).

## Open items / surprises

- `execute(engine=None)` compat branch survives until Orchestration's anchored-init slice removes the last caller; then a Run micro-slice drops the branch (TODO pinned in `engine.py`).
- `_invoke_adapter` if-elif ladder untouched per brief §Out of scope (decorator-registry question tracked separately).
- Gotcha for future Run work: `RunRecord.engine_version` is **adapter-observed only** (`normalize_native_result` ignores the context's version). A pinned run whose probe captured a version but whose adapter reported none lands `engine_version=None` on the record. Pre-existing contract; documented because the first draft of a pinned-dispatch test wrongly assumed otherwise.

## Merge notes for Main Branch

- Parallel wave (per PM's 2026-07-03 briefs): Memory `engine-pin-store-primitives`, Regression `engine-scoped-baseline`, Orchestration `anchored-init-and-verb-resolution`. This slice has **zero file overlap** with Memory/Regression. Orchestration's slice CONSUMES this API — **merge this slice before Orchestration's**. No other ordering constraint.
- Pre-merge gate: `env -u PYTHONPATH uv run mypy --strict src/novetest` (Success, 114) + `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` (1361/3/0, 44 snapshots).

## WORKLOG entry (pasted)

See `WORKLOG.md` top entry `## 2026-07-03 — anchored-pin-cycle / run-team pin-driven dispatch + single-source detection API (1/4 of anchored-pin wave)` in this worktree — staged in the same commit per the pre-commit hook.
