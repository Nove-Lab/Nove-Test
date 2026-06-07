---
from: novetest-coverage-team
to: novetest-main-branch-team
type: handoff
created: 2026-06-07
slug: dotnet-cobertura-derive
status: ready
related:
  - agent-comms/tasks/coverage-team-2026-06-06-dotnet-cobertura-derive.md
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
  - src/novetest/coverage/cobertura_parser.py
  - src/novetest/coverage/derive.py
  - src/novetest/coverage/availability.py
  - tests/fixtures/coverage/cobertura/
  - tests/unit/coverage/test_cobertura_parser.py
  - tests/unit/coverage/test_derive_xunit.py
  - tests/integration/coverage/test_dotnet_cobertura_derive.py
  - WORKLOG.md
---

# Handoff — dotnet Cobertura → CoverageFactSet derive path (closes Phase 2/3 6th-engine Coverage promise)

## TL;DR

Cobertura XML now flows through `derive_coverage_facts` like JaCoCo,
LCOV, and the two JSON paths — the dotnet adapter's already-correct
`coverage.cobertura.xml` artifact (from `6c7bc76`) becomes a real
`CoverageFactSet` on every `novetest run --coverage` invocation, and
`coverage_outcome.kind` flips from `"unavailable"` to `"fact-set"` for
.NET runs. `coverage show` / `coverage diff` / `inspect` Coverage
sections all light up.

**Worktree**: `coverage-dotnet-cobertura-derive` at
`/home/yjshin/dev/novetest-dotnet-cobertura-derive` (NOT committed yet —
CEO hasn't authorized the commit).

**Status**: code written + tested + smoked, ready for Main Branch merge
after user-explicit commit authorization.

## Files

### New (4)

| File | Purpose |
|---|---|
| `src/novetest/coverage/cobertura_parser.py` (~310 LOC) | XML→`CoverageFactSet`; mirrors `jacoco_parser.py` shape |
| `tests/fixtures/coverage/cobertura/coverlet_basic.xml` | Canonical Coverlet 1-class 100%-covered fixture |
| `tests/fixtures/coverage/cobertura/coverlet_partial_coverage.xml` | 2-class multi-package fixture with `branch="true"` lines (parser must ignore for v1) |
| `tests/unit/coverage/test_cobertura_parser.py` (19 cases) | Parser unit tests — happy paths, multi-source resolution, edge cases, structural errors, multi-file inputs |
| `tests/unit/coverage/test_derive_xunit.py` (11 cases) | Derive xunit branch — happy dispatch, missing artifact key, missing file, malformed XML, wrong root tag, §2.4 sources-not-found, partial survival, directory-shape artifact (forward-compat), empty directory |
| `tests/integration/coverage/test_dotnet_cobertura_derive.py` (1 case) | E2E: real `dotnet test --coverage` → `coverage_outcome.kind=fact-set`; subprocess-invoked `inspect` + `coverage show` envelope assertions |

### Modified (3)

| File | Change |
|---|---|
| `src/novetest/coverage/derive.py` | + `_XUNIT_ENGINE_NAME = "xunit"` constant, + early-branch dispatch right after the junit one, + `_derive_xunit_cobertura` helper (handles both file and directory `coverage_xml` artifact shapes, implements §2.4 silent-drop + `cobertura-sources-not-found` discriminator, recomputes summary on partial drop via `dataclasses.replace`), + `_aggregate_file_summary` helper. Imports `parse_cobertura_xml` + `replace` + `CoverageSummary` + `FileCoverage`. |
| `src/novetest/coverage/availability.py` | + `_COVERAGE_XML_ARTIFACT_KEY = "coverage_xml"` to the artifact-key tuple (covers BOTH junit's existing JaCoCo and dotnet's new Cobertura under one key — derive's engine-name dispatch picks the right parser). Native-payload probe switched from `.is_file()` to `.exists()` so the directory-shape per-test-mode forward-compat path counts. |
| `WORKLOG.md` | Top-of-file entry with full verification capture (1176 passed / 5 skipped baseline, mypy 92 src files clean, all 5 CLI smokes captured). |

### NOT modified (charter respect)

- `src/novetest/run/adapters/dotnet_adapter.py` — Run team territory. Adapter already produces correct Cobertura XML on the `coverage_xml` artifact key per `6c7bc76`; no Run-side change required.
- `src/novetest/models/coverage_fact_set.py` — Memory team territory. `CoverageFactSet` shape unchanged; the parser maps into the existing v1 schema.
- `tests/integration/run/test_dotnet_coverage.py` — brief §2.7 said to flip `coverage_outcome.kind` assertions from `"unavailable"` to `"fact-set"` here, but `grep coverage_outcome` returned zero hits (only `coverage_unavailable_*` metadata-key checks from F1b hotfix). No edits applied; gap was preemptive in the brief.
- `src/novetest/orchestration/**` — brief §2.6 said to file a `questions/` entry if orchestration changes were needed. Verified existing `cli/app.py::_coverage_outcome_payload` automatically projects `kind=fact-set` when derive returns a `CoverageFactSet`; no orchestration change needed.

## Pre-handoff gate environment (§2.5 binding per `decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md`)

- Host: WSL2 Ubuntu (yongjun9461's CEO machine; the same equipped host that landed dotnet adapter hotfix #1 and the Coverlet PerTestCoverage host-equip findings)
- Toolchain shim: `~/.local/share/novetest-toolchains.sh` sourced — `[novetest-toolchains] equipped: dotnet=8.0.421 java=17.0.19 mvn=3.8.7 gradle=8.5`
- `dotnet --version`: `8.0.421` (matrix floor 8.0 LTS — met)
- `coverlet.collector` resolved: `6.0.2` (matrix floor 6.0.2 — met, NuGet warm cache)
- xunit: `2.6.0` from the fixture (matrix floor 2.6 — met)

### Required §2.5 evidence

| Check | Command | Result |
|---|---|---|
| §2.5.2 dotnet-focused tests execute (no skips) | `uv run pytest -v tests/integration/run/test_dotnet_coverage.py tests/integration/coverage/test_dotnet_cobertura_derive.py` | **4 passed + 0 skipped + 0 failed in 34.56s** |
| §2.5.3 full suite | `uv run pytest -q tests/unit tests/integration` | **1176 passed + 5 skipped + 0 failed in 173.54s** (5 skips: cargo / jest toolchain gaps — unrelated to this slice) |
| mypy --strict | `uv run mypy` | **clean, 92 source files** (baseline 91 + 1 new `cobertura_parser.py`) |
| §2.5.4 CLI smoke #1 — init | `novetest init` | `ok=true`, `command=init` |
| §2.5.4 CLI smoke #2 — run --coverage | `novetest run --coverage` | `coverage_outcome.kind=fact-set`, `mapping_granularity=aggregate`, `summary.num_statements=2 covered=2 percent=100.0`, `engine_name=xunit`, `has_coverage_facts=True`, `artifact_paths.coverage_xml` registered. **HEADLINE: this is the pre→post-slice flip from `unavailable` to `fact-set`.** |
| §2.5.4 CLI smoke #3 — inspect | `novetest inspect <run_id>` | `sub_reports.coverage=available`, `coverage_outcome.kind=fact-set`, `mapping_granularity=aggregate` |
| §2.5.4 CLI smoke #4 — coverage show | `novetest coverage show <run_id>` | `coverage_outcome.kind=fact-set`, `mapping_granularity=aggregate`, `summary.percent_covered=100.0` |
| Extra CLI smoke #5 — coverage diff | `novetest coverage diff <run1> <run2>` | `coverage_delta.kind=delta`, 0 file_deltas (identical re-runs) |

Smoke workspace preserved at `/tmp/novetest-dotnet-cob-smoke/ws/` for postmortem inspection if Main Branch wants to replay.

## DoD bullets believed closed (12/12)

PM verifies and ticks; Coverage Team claims based on §3 evidence above.

| # | Bullet | How closed |
|---|---|---|
| 1 | Cobertura detection added to `derive_coverage_facts`; root.tag heuristic | `derive.py` `_XUNIT_ENGINE_NAME` branch (engine-name driven, not root-tag — see §"Design deviations" below); `cobertura_parser.py` raises on root.tag != "coverage" |
| 2 | Per-file line-coverage derivation per §2.2 | `cobertura_parser.py::_build_class_file_coverage`; unit test `test_fixture_partial_coverage_yields_two_files` |
| 3 | `mapping_granularity = "aggregate"` hard-coded for .NET path | `cobertura_parser.py::_COBERTURA_MAPPING_GRANULARITY = "aggregate"` constant; pinned in every test assertion |
| 4 | Source path resolution drops missing files gracefully per §2.4 | `derive.py::_derive_xunit_cobertura` post-parser filter; unit test `test_derive_xunit_all_sources_unresolvable_returns_sources_not_found` + `test_derive_xunit_partial_survival_drops_only_missing_files` |
| 5 | `coverage_outcome.kind = "fact-set"` for .NET runs | Integration test asserts `outcome.coverage_outcome` is `CoverageFactSet` AND subprocess `inspect` envelope `coverage_outcome.kind == "fact-set"`; CLI smoke #2 + #3 above |
| 6 | `coverage show <dotnet_run_id>` returns structured per-file coverage | Integration test asserts `coverage show` envelope; CLI smoke #4 above |
| 7 | `coverage diff <run1> <run2>` returns structured deltas | CLI smoke #5 above (envelope `coverage_delta.kind="delta"`) |
| 8 | `inspect <dotnet_run_id>` Coverage section populated | Integration test + CLI smoke #3 (`sub_reports.coverage=available`) |
| 9 | JaCoCo / pytest / jest / gotest derive paths UNCHANGED | Full suite 1176 passed; pre-existing derive tests untouched. Junit derive tests still green: `tests/unit/coverage/test_derive_junit.py` runs alongside; LCOV cargo dispatch test still green. |
| 10 | mypy --strict clean | 92 source files clean |
| 11 | §2.5 pre-handoff gate executed | §"Pre-handoff gate environment" above (5 CLI smokes captured byte-equivalently) |
| 12 | Cobertura fixture XML(s) under `tests/fixtures/coverage/cobertura/` | `coverlet_basic.xml` + `coverlet_partial_coverage.xml` |

## Design deviations from brief §2 (refined during implementation)

### D1 — Dispatch via engine_name, NOT root.tag heuristic (§2.1)

Brief §2.1 suggested `_is_cobertura(root)` helper that detects via
`root.tag == "coverage" and root.find("packages") is not None`. This
would have collided with the existing `_JUNIT_ENGINE_NAME` dispatch
shape — both junit and xunit use the `coverage_xml` artifact key, and
the engine_name is what discriminates them at the dispatch layer. The
root-tag check still lives, but in the **parser** (`cobertura_parser.py`
raises if root.tag != "coverage"), not the dispatcher. The dispatcher
follows the existing pattern: `_CARGO_ENGINE_NAME` / `_JUNIT_ENGINE_NAME`
/ now `_XUNIT_ENGINE_NAME` engine-name branches.

This is a strict improvement: dispatching by engine_name catches
misconfigurations (e.g. someone wires JaCoCo XML into a xunit-engine
RunRecord) as `native-payload-corrupt` rather than mis-routing the
parse. Unit test `test_derive_xunit_wrong_root_tag_returns_corrupt`
pins this guard.

### D2 — Path resolution + §2.4 split between parser and derive (§2.4)

Brief §2.4 specified the source-path resolution behavior as derive
responsibility. To keep the parser pure (XML→model, no filesystem
touch — matches `jacoco_parser.py` / `istanbul_parser.py` / `parser.py`
/ `lcov_parser.py`), the parser does **best-effort workspace-relative
resolution** (first `<source>` joined under `workspace_root`; relpath
fallback for outside-workspace) but does NOT existence-check. The
derive helper `_derive_xunit_cobertura` post-filters by
`.is_file()` against `workspace_root / fc.file_path`. When ALL files
filter out (but the XML had classes), the helper returns
`CoverageUnavailable(missing-native-payload)` with the literal string
`cobertura-sources-not-found` in the detail per §2.4. When SOME filter
out, `dataclasses.replace` rebuilds the fact set with filtered files +
recomputed summary.

This split is empirically cleaner: 5 parser unit tests can use
`tmp_path`-based source dirs without writing source files; the derive
tests use `workspace_files` parameter to materialize them. Mirrors the
JSON parser's posture (validation in parser; environmental concerns in
derive).

### D3 — `availability.py` artifact-key probe switched to `.exists()`

The previous `.is_file()` probe would have silently missed the dotnet
adapter's forward-compat per-test directory-shape `coverage_xml` (which
registers the parent of multiple `coverage.<slug>.cobertura.xml`
files). Switched to `.exists()` so both file and directory shapes
count. This also forward-protects a hypothetical future multi-module
Maven case where junit might register a dir instead of a file.

### D4 — `branch_arc_semantics = "branches-omitted"` metadata pin (§2.3)

The Cobertura XML carries `branch="true"` + `condition-coverage`
attributes on per-line entries. Per §2.3 the v1 parser drops these to
match the JaCoCo path's lines-only v1 scope (which has been the
shipping contract since 2026-05-31). The semantic absence is pinned in
`metadata["branch_arc_semantics"] = "branches-omitted"` so downstream
debuggers can distinguish "branches absent because coverage tool
reported zero" from "branches absent because v1 dropped them" without
re-reading the original XML.

### D5 — Multi-file input uses "last-write-wins" not "first-wins"

Brief §2 didn't pin behavior for multi-XML input (forward-compat path
where the dotnet adapter registers a directory of per-test XMLs).
JaCoCo's parser uses "first-wins" (skips duplicate file paths); the
Cobertura parser uses "last-write-wins" (later XMLs overwrite earlier
entries). Either is defensible; "last-write-wins" was chosen because
the practical multi-file scenario is "per-test mode emits one XML per
test method, possibly multiple writes to the same file across tests"
where the LATER write would typically reflect the cumulative aggregate
state. The unit test `test_multi_file_input_overwrites_same_file_path_last_wins`
pins it explicitly.

(Practically moot for v1 — Coverlet XPlat aggregate is empirically
single-file.)

## Open questions for PM (NOT blocking; informational)

### Q1 — `coverage_xml` artifact-key collision between junit + xunit

Junit and xunit both register under `coverage_xml`. The
engine-name-driven dispatch handles it cleanly. PM may want to
formalize this in a follow-up decision: "single artifact key per
output format, engine-name discriminator routes" vs "one key per
engine." The current pattern matches the dotnet adapter's own pattern
precedent (`src/novetest/run/adapters/dotnet_adapter.py:34-38` —
"reuse the `coverage_xml` key matches the JUnit slice's pattern
precedent for XML-based coverage formats"). No action needed unless
the convention changes downstream.

### Q2 — Branch coverage derive — when does the deferral close?

§2.3 defers Cobertura branch derivation. The JaCoCo path also defers
branches today (looking at `jacoco_parser.py` — it DOES emit
synthesized branch indices). So there's a partial drift: JaCoCo emits
synthesized branch indices via `cb`/`mb` counters; Cobertura v1 emits
zero. PM may want to schedule a follow-up to align the two — either
JaCoCo drops to zero (simpler) or Cobertura learns `<conditions>`
parsing (richer). Suggested timing: post-MVP polish or a Q2
specialist-driven cycle.

### Q3 — Sources-not-found discriminator vs adapter-warning-surface v1

The `cobertura-sources-not-found` discriminator I added to the
`CoverageUnavailable.detail` field is currently free-form text (matches
the existing JaCoCo / LCOV "missing-native-payload" detail strings).
Decision `2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
established `{topic}_kind` / `{topic}_message` metadata pairs as the
v1 surface for adapter warnings. The Coverage engine's
`CoverageUnavailable` is a different shape (`reason` + `detail`
already exists) and not adapter-generated, so the v1 metadata-channel
convention doesn't directly apply. PM may want to add a
`reason_kind` / `reason_detail` split to `CoverageUnavailable` in a
follow-up if AI consumers need machine-readable discriminators on
this path; not blocking today (the literal string is grep-able).

### Q4 — Cobertura derive path for Python coverage.py `--cov-report=xml`

The pytest adapter writes BOTH `coverage_json` AND `coverage_xml`
(Cobertura). Coverage engine prefers the JSON path. If a future
slice ever drops the JSON path (unlikely — coverage.py JSON is
richer), the existing Cobertura parser could be repointed at pytest's
XML. No action today; preserve as an architectural note.

### Q5 — CI matrix .NET cell still absent

The new integration test `test_dotnet_cobertura_derive.py` skips
without `dotnet` on PATH. Current CI lanes don't include .NET, so the
test skips in CI today (per the same pattern as cargo). When Release
team adds a .NET cell to the matrix, this test becomes a real gate.
Out of scope for this slice; flagged for Release backlog.

## Risks / what could break

- **Cobertura schema drift in future Coverlet releases** — the parser
  pins to today's Coverlet 6.0.x XPlat output shape (`<coverage>` →
  `<sources>` → `<packages>/<package>/<classes>/<class>` →
  `<lines>/<line number=N hits=H>`). A future Coverlet release that
  bumps to a different XML schema would surface as `native-payload-corrupt`
  at the parser level. Unit test `test_wrong_root_tag_raises` provides
  the structural regression guard.
- **Per-test mode flip-on** — if a future Coverlet release fixes the
  XPlat data collector pipe and starts emitting per-test XMLs, the
  dotnet adapter's `_glob_coverage_xml` will register the parent
  directory under `coverage_xml`; the derive helper handles this
  shape (unit test `test_derive_xunit_directory_artifact_globs_xml_children`)
  but the `mapping_granularity` is hard-coded `aggregate` in the
  parser today per amended decision §3. A follow-up slice would need
  to either lift the granularity decision into the dispatch layer or
  change the parser to read it from the adapter's metadata. Not
  needed until Coverlet ships the fix.
- **Workspace-relative path semantics for outside-workspace sources** —
  the parser falls back to `os.path.relpath` (Istanbul precedent),
  which can produce `../../tmp/foo/Calc.cs`-shaped strings. Practical
  impact is minimal for `dotnet test` runs (the workspace is always
  the csproj's parent), but if a user pipes Coverlet output from a
  different directory the relpath form would surface; consumers
  expecting clean POSIX-relative-without-double-dot would need to
  handle it. Same posture as the Istanbul parser; no new surprise.

## What Main Branch needs to do

1. Pull worktree branch `coverage-dotnet-cobertura-derive`
2. Verify §2.5 gate replicates on Main Branch's host (the equipped
   host per `decisions/2026-06-04 §2.5`):
   - `uv run pytest -v tests/integration/run/test_dotnet_coverage.py tests/integration/coverage/test_dotnet_cobertura_derive.py` → expect 4 passed + 0 skipped + 0 failed
   - `uv run pytest -q tests/unit tests/integration` → expect 1176+ passed + 0 failed
   - `uv run mypy` → expect clean
3. Re-run the 5 CLI smokes from §"Pre-handoff gate environment" against
   the merged binary to confirm byte-equivalent envelope shape
4. Merge to main, write verification doc using the Cap-N format
   established by the dotnet hotfix cycle (Manual Test reproduces
   each Cap-N byte-equivalently modulo per-run ULIDs)
5. Hand off to Manual Test for the equip-and-exercise verdict pass

## Cycle-close commit message (suggested, for when CEO authorizes)

```
feat(coverage): Cobertura XML → CoverageFactSet derive path for .NET

Closes the 6th-engine Coverage promise from Phase 2/3. The dotnet
adapter's already-correct coverage.cobertura.xml artifact (from
6c7bc76) now produces a real CoverageFactSet instead of
CoverageUnavailable. coverage_outcome.kind flips from "unavailable"
to "fact-set" for every novetest run --coverage on .NET projects;
coverage show / coverage diff / inspect Coverage sections all light up.

New cobertura_parser.py mirrors jacoco_parser.py's shape. derive.py
dispatches engine_name == "xunit" through the new helper; same
coverage_xml artifact key as junit (engine_name discriminates the
right parser). availability.py adds coverage_xml + switches probe to
.exists() for forward-compat with directory-shape per-test mode.
§2.4 sources-not-found path returns CoverageUnavailable with
cobertura-sources-not-found discriminator; partial drop recomputes
summary via dataclasses.replace. Branch facts deferred per §2.3 +
marked branches-omitted in metadata.

Tests +31 (1176 passed + 5 skipped on equipped host vs. 1145 baseline),
mypy --strict clean (92 source files). All 5 CLI smokes green on
equipped host; coverage_outcome.kind == "fact-set" confirmed.

Closes Phase 2/3 backlog Track D.
```
