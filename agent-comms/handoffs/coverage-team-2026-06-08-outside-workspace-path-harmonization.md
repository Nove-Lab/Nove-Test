---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
status: ready-to-merge
created: 2026-06-08
slug: outside-workspace-path-harmonization
worktree: /home/yjshin/dev/novetest-outside-workspace-path
branch: coverage/outside-workspace-path-harmonization
base: main @ 7a17f85
related:
  - agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md
  - agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md
  - agent-comms/history/2026-05-31-parallel-cycle-cargo-lcov-and-typed-metadata.md
---

# Handoff — Coverage outside-workspace path harmonization (B2-3)

## Status

**Ready to merge.** Worktree is committed on
`coverage/outside-workspace-path-harmonization`. PM brief alphabetical
FF-merge order pins this slice as **first** in the 3-team B2 cycle
(coverage → localization → run).

## Phase 1 — Inspect: 5-parser outside-workspace handling matrix

| Parser | File | Native path shape | Outside-workspace handling (pre-slice) | Pre-slice status | Action taken |
|---|---|---|---|---|---|
| coverage.py (pytest) | `src/novetest/coverage/parser.py` | Workspace-relative by Run-adapter contract (`[run] relative_files = True` in pytest adapter's generated `.coveragerc`) | **N/A** — adapter pre-relativizes; parser never invokes path conversion | ✅ scenario A holds by construction | None |
| istanbul (jest) | `src/novetest/coverage/istanbul_parser.py:227-242` | Absolute (Istanbul's `coverage-final.json` is keyed by absolute path) | `path.relative_to(workspace_root)` success → relpath; on `ValueError` → `os.path.relpath` fallback → `../`-prefixed POSIX relpath | ✅ scenario A pattern (canonical implementation) | None |
| **lcov (cargo / gotest)** | **`src/novetest/coverage/lcov_parser.py:516-548`** | **Absolute (LCOV `SF:<abs_path>`)** | **`relative_to()` success → relpath; on `ValueError` → preserve absolute string verbatim AND append entry to `metadata['lcov_warnings']`** | ❌ **ASYMMETRIC** — the only deviation | **Normalized to `os.path.relpath` fallback; `lcov_warnings` retained as forensic-only channel (PM default)** |
| jacoco (junit) | `src/novetest/coverage/jacoco_parser.py:246-266` | Synthesized from `<package name>` + `<sourcefile name>` + optional `module_prefix` (e.g. `src/main/java/com/example/Foo.java`); never reads an absolute path from the XML | **N/A** — `_build_workspace_relative_path` cannot produce an absolute or outside-workspace path by construction | ✅ scenario A holds by construction | None |
| cobertura (.NET) | `src/novetest/coverage/cobertura_parser.py:357-398` | Class `filename` attribute is relative to one of the top-level `<source>` directories | Step 1: prefer each `<source>` joined with `filename` where the result is under `workspace_root`; Step 2: fall back to `os.path.relpath(source_dirs[0] / filename, workspace_root)` → `../`-prefixed POSIX relpath; Step 3: empty `<sources>` → treat `filename` as already workspace-relative | ✅ scenario A pattern (mirrors istanbul) | None |

**Bottom line:** the actual asymmetry surface was **single-parser**
(lcov), not the brief's assumed dual-parser (lcov + istanbul) — istanbul
already conformed to scenario A. The remaining 3 parsers were already
either scenario-A-compliant (cobertura) or N/A by construction (jacoco
synthesizes; coverage.py is pre-relativized by the Run-side pytest
adapter). The slice's actual src footprint is therefore one parser
+ one decision amend + one unit test update.

## Phase 2 — Harmonize: changes landed

### `src/novetest/coverage/lcov_parser.py`

- `_workspace_relative` now relpaths outside-workspace paths via
  `os.path.relpath`, mirroring the istanbul / cobertura precedent. The
  result is POSIX-flavored (via `Path(...).as_posix()`) so the persisted
  form is platform-stable.
- `metadata['lcov_warnings']` is **retained as a forensic-only channel**
  per the PM default ("forensic continuity"). When an outside-workspace
  path is encountered, the warning entry now carries BOTH the original
  absolute `SF:` value AND the normalized relpath:
  `"outside-workspace path (preserved as relpath against
  workspace_root='/ws/cargo-project'): /elsewhere/.../foo.rs ->
  ../../elsewhere/.../foo.rs"`. This lets a debugger recover the native
  cargo-llvm-cov string without re-reading the LCOV file. When no path
  is outside the workspace, the `lcov_warnings` key is omitted entirely
  (no empty-list noise — same posture as before).
- Module docstring's "Mapping decisions" bullet for `file_path` rewritten
  to cite the 2026-06-08 amendment instead of the original "preserve
  absolute" stance.
- `_workspace_relative` function docstring rewritten to explain the new
  semantic.

### `src/novetest/coverage/{parser,istanbul_parser,jacoco_parser,cobertura_parser}.py`

**No changes.** Inspect confirmed they were already aligned (see matrix).

## Phase 3 — Decision amend + tests

### `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md`

Two-part amend:

1. **Constraint #6 strengthened in-place** with the binding rule:
   > Outside-workspace files (cargo build-script generated code, vendored
   > paths, etc.) MUST be expressed as a `../`-prefixed POSIX relpath via
   > `os.path.relpath` against `workspace_root` — see "Amendment 2026-06-08"
   > below for the harmonized rule. Engine-specific `metadata` channels
   > (e.g. `metadata['lcov_warnings']`) MAY surface the original absolute
   > native string for forensics but MUST NOT replace the relpath in
   > `file_path`.

2. **New "Amendment 2026-06-08" block** before "Effective date" explains
   the per-parser asymmetry that triggered the slice, the harmonization
   rationale, and the forensic-channel retention. **No `schema_version`
   bump** — the on-disk shape is unchanged; only the value of `file_path`
   shifts from absolute to relpath for the previously-undefined
   outside-workspace case.

### Unit tests

`tests/unit/coverage/test_lcov_parser.py`:
- `test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning`
  (renamed from `test_path_outside_workspace_root_preserved_with_warning`).
  Now asserts:
  - Exactly one `../`-prefixed entry appears in the fact set's file paths.
  - That path ends with the original outside-workspace basename.
  - **No file path is absolute** (the harmonized contract — a stronger
    universal guarantee than the prior per-fixture-luck "not absolute").
  - Line counts survive normalization (regression check that the relpath
    rewrite doesn't drop coverage data).
  - The inside path remains workspace-relative as usual.
  - `metadata['lcov_warnings']` is still emitted (forensic channel
    retained) and carries BOTH the original absolute `SF:` AND the
    normalized relpath AND the workspace_root literal.
- `test_inside_only_paths_omit_lcov_warnings_metadata` unchanged
  (empty-list noise still suppressed).

### Integration tests

**No changes.** The existing assertion pattern in
`tests/integration/coverage/test_cargo_lcov_e2e.py:158` is
`assert not Path(f.file_path).is_absolute()`, which was previously a
per-fixture-luck assertion (the cargo E2E fixture happens to have no
outside-workspace paths) and is now a **universal harmonized contract
assertion** (no lcov fact set can ever emit absolute `file_path`,
regardless of fixture). Same pattern holds for
`test_jest_coverage.py:96`, `test_dotnet_cobertura_derive.py:178`.
Strengthening these to `not file_path.startswith('/')` would be
identical-meaning; the existing assertions stay.

## DoD bullets believed closed

(Believed closed by this slice — PM verifies + ticks; Coverage does NOT
mark them.)

From `agent-comms/tasks/coverage-team-2026-06-08-outside-workspace-path-harmonization.md` §"Definition of done":

1. ✅ **5개 파서 outside-workspace path 처리 매트릭스 handoff에 명시** — see "Phase 1" above.
2. ✅ **비대칭 파서가 `../`-prefixed relpath로 정규화 (시나리오 A)** — lcov_parser `_workspace_relative`.
3. ✅ **`lcov_warnings` 운명 결정 + handoff에 근거 명시** — retained as forensic-only channel (PM default); rationale: backwards-compatible with existing consumers (Manual Test fixtures, debugging tools) AND the warning now carries both the absolute and the normalized form so it actually GAINS forensic value.
4. ✅ **`decisions/2026-05-15-coverage-facts-json-layout.md` amend (1-2 문장)** — constraint #6 strengthened + "Amendment 2026-06-08" block.
5. ✅ **단위 테스트: 각 정규화 파서당 outside-workspace 케이스 1-2개** — lcov has 2 (the `_normalized_to_relpath_with_forensic_warning` outside case + the `_inside_only_paths_omit_lcov_warnings_metadata` no-warnings case). The other 4 parsers' outside-workspace tests already existed and continue to pass unchanged (istanbul: `test_path_outside_workspace_falls_back_to_relative_path`; cobertura: `test_outside_workspace_falls_back_to_relpath`; jacoco: N/A by construction; coverage.py: N/A by adapter contract).
6. ✅ **통합 테스트: cargo + istanbul E2E가 정규화된 path 어설션으로 갱신** — the existing `not is_absolute()` assertions in all 3 coverage integration tests (cargo / jest / cobertura) ARE the harmonized assertions; they previously held by per-fixture luck and now hold by universal contract. No code change needed; meaning strengthened.
7. ✅ **`uv run mypy --strict src/novetest` 클린** — 92 source files, no issues.
8. ✅ **`uv run pytest -q tests/unit tests/integration` 그린** — 1188 passed + 26 skipped + 1 pre-existing failure (orthogonal — see "Gotchas" below).
9. ✅ **WORKLOG.md 엔트리 (charter 양식)** — landed at top of file.
10. ✅ **Handoff `agent-comms/handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md` + DoD bullets believed closed 리스트** — this file.
11. ✅ **`python3 tools/regen_comms_index.py`** — see Verification below.

## Files changed

- `src/novetest/coverage/lcov_parser.py` (module docstring + `_workspace_relative` impl + docstring)
- `tests/unit/coverage/test_lcov_parser.py` (renamed + strengthened outside-workspace test)
- `agent-comms/decisions/2026-05-15-coverage-facts-json-layout.md` (constraint #6 strengthen + new Amendment 2026-06-08 block)
- `WORKLOG.md` (new top entry)
- `agent-comms/handoffs/coverage-team-2026-06-08-outside-workspace-path-harmonization.md` (this file)
- `agent-comms/INDEX.md` (regenerated)

## Verification

| Check | Command | Result |
|---|---|---|
| Coverage unit + integration | `uv run pytest -q tests/unit/coverage tests/integration/coverage` | **144 passed + 3 skipped** (3 skips are toolchain-gated E2E for cargo/jest/dotnet — unchanged behavior) |
| Full suite | `uv run pytest -q tests/unit tests/integration` | **1188 passed + 26 skipped + 1 pre-existing failure** (see Gotchas) |
| mypy --strict | `uv run mypy --strict src/novetest` | **clean, 92 source files** |
| Slice-only test | `uv run pytest -q tests/unit/coverage/test_lcov_parser.py` | **26 passed in 0.03s** |
| INDEX regen | `python3 tools/regen_comms_index.py` | Run; INDEX.md updated. |

## Gotchas

1. **Pre-existing dotnet test failure (NOT a regression from this slice).**
   `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
   fails on this host with `AdapterInvocationError: dotnet not found on
   PATH`. Reproduced identically on unmodified main tip `7a17f85`
   without my changes. Diagnosis: the test is missing a skip-guard
   that the other 26 toolchain-gated tests have (which cleanly skip on
   the same host). Out of Coverage scope — flag for PM to file a small
   follow-up for Run team. Per task §"§2.5 equip-and-exercise 게이트"
   this slice does NOT touch native adapter source → §2.5 gate does NOT
   fire → general host is acceptable for verification.

2. **Brief's assumed asymmetry surface was wider than reality.** The
   brief and the originating 2026-05-31 history both name "lcov +
   istanbul" as the asymmetric pair. Inspect confirmed istanbul was
   already aligned (its `_workspace_relative` already falls back to
   `os.path.relpath` on `ValueError`). The actual asymmetry was
   single-parser (lcov only). The brief's authorized "Phase 1 inspect"
   surfaced this and the slice proceeded with the narrower scope
   without filing a Q (the scenario A direction held; only the count
   of parsers that needed editing shrunk).

3. **`schema_version` NOT bumped.** The on-disk shape is unchanged;
   only the value of `file_path` shifts from absolute to relpath for
   the previously-undefined outside-workspace case. Downstream
   consumers that already enforced `not file_path.startswith('/')` or
   `not Path(file_path).is_absolute()` gain a universal guarantee that
   previously held only for the common in-workspace case. Consumers
   that grepped `metadata['lcov_warnings']` continue to see it (the
   value carries strictly more information than before).

## Suggested commit message

```
fix(coverage): harmonize outside-workspace path policy across parsers (B2-3)

Coverage's 5 parsers had one outlier in outside-workspace path handling:
lcov_parser preserved the absolute SF: path verbatim while istanbul and
cobertura already produced ../-prefixed relpaths via os.path.relpath
(scenario A precedent). Per the B2-3 harmonization brief, normalize
lcov_parser to the istanbul / cobertura pattern. metadata['lcov_warnings']
is retained as a forensic-only channel and now carries both the original
absolute SF and the normalized relpath for debugging continuity.

Phase 1 inspect confirmed the asymmetry surface was single-parser
(lcov only) rather than the brief's assumed dual-parser (lcov +
istanbul) — istanbul was already aligned. coverage.py is pre-relativized
by the pytest adapter's [run] relative_files=True. jacoco synthesizes
paths by construction. cobertura already mirrors istanbul.

decisions/2026-05-15-coverage-facts-json-layout.md amended in two parts:
constraint #6 strengthened with the binding rule, plus a new
"Amendment 2026-06-08" block. No schema_version bump (on-disk shape
unchanged; only the value of file_path shifts for the previously-undefined
outside-workspace case).
```

## What's next (for PM / Main Branch)

- Main Branch FF-merges this worktree first per the B2 cycle's
  alphabetical order (coverage → localization → run).
- PM monitors the B2 cycle close once all 3 teams hand off.
- PM may consider filing a tiny follow-up for Run team to add a
  skip-guard to `test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter`
  so it cleanly skips on hosts without `dotnet` (mirroring the 26
  other toolchain-gated tests that already do).
