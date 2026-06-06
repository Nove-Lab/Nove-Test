---
from: novetest-pm-team
to: novetest-coverage-team
type: task
created: 2026-06-06
slug: dotnet-cobertura-derive
status: pending
related:
  - agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md
  - agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md
  - agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md
  - design/implementation-plan/delivery-phasing.md
  - src/novetest/coverage/derive.py
  - src/novetest/run/adapters/dotnet_adapter.py
  - tests/integration/run/test_dotnet_coverage.py
---

# Coverage engine — Cobertura → CoverageFactSet derive path for the .NET adapter (closes Phase 2/3 promise for the 6th engine)

## TL;DR

The .NET adapter (`6c7bc76`) produces a fully-populated Cobertura XML
at `RunRecord.artifact_paths["coverage_xml"]` on the `--coverage` path,
but the Coverage engine has no Cobertura derive path — only a JaCoCo
derive path. Consequence:
`data.memory_entry.run_record.coverage_outcome.kind` resolves to
`"unavailable"` for the .NET adapter even when Cobertura XML is
present on disk; downstream verbs (`novetest coverage show`,
`novetest coverage diff`, `novetest inspect` Coverage section) are
empty for .NET projects.

Phase 2/3 narrative pinned this as in-scope:
- Phase 2 (delivery-phasing.md): *"JUnit and dotnet land in Phase 2.5 (a same-phase extension)"*
- Phase 3 (delivery-phasing.md): *"all six landed by end of Phase 3"*

This slice closes the 6th-engine promise. Cobertura XML → `CoverageFactSet`
derive path, mirroring the existing JaCoCo pattern.

**Estimated scope**: ~3-6 hours. Single attempt expected.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md`
2. `.claude/agents/novetest-coverage-team.md` (your charter)
3. **`agent-comms/history/2026-06-06-phase2.5-dotnet-adapter-two-cycle-arc.md`** §"Load-bearing lessons" 6 — the gap this slice closes, with concrete evidence
4. `agent-comms/decisions/2026-06-03-coverlet-pertestcoverage-key.md` §3 (amended 2026-06-05) — `mapping_granularity = "aggregate"` is the v1 contract for .NET (per-test deferred); your derive must respect this
5. `agent-comms/decisions/2026-06-04-equip-and-exercise-for-adapter-cycles.md` §1 + §2.5 — this slice touches `tests/integration/run/test_dotnet_coverage.py`, §2.5 binds (see §4 below)
6. `design/implementation-plan/delivery-phasing.md` Phase 2 + Phase 3 sections — the original scope this slice closes
7. `src/novetest/coverage/derive.py` — existing JaCoCo derive path (pattern reference)
8. `src/novetest/run/adapters/dotnet_adapter.py` lines that produce `artifact_paths["coverage_xml"]` (Cobertura location convention)
9. `tests/integration/run/test_dotnet_coverage.py` — current `coverage_outcome.kind = "unavailable"` assertions you'll be updating
10. A sample Cobertura XML at `/tmp/dotnet-repro/...native/TestResults/.../coverage.cobertura.xml` (Manual Test preserved one — see `findings/manual-test-team-2026-06-06-host-equip.md` §"Artifacts on disk" for the path)
11. `src/novetest/models/` for `CoverageFactSet`, `CoverageFact`, `CodeLocation` shapes (your existing data model)

---

## §1. Acceptance criteria (binding)

| # | Criterion | Evidence form |
|---|---|---|
| 1 | `derive_coverage_facts` can ingest Coverlet Cobertura XML and produce a valid `CoverageFactSet` | unit test against fixture XML |
| 2 | `coverage_outcome.kind` resolves to `"fact-set"` (not `"unavailable"`) for .NET runs with `--coverage` when Cobertura XML is present at `artifact_paths["coverage_xml"]` | integration test on dotnet fixture |
| 3 | `mapping_granularity = "aggregate"` for the .NET path (per amended Coverlet decision §3 — XPlat path is aggregate-effective-default) | derive-time pin + test assertion |
| 4 | `novetest coverage show <dotnet_run_id>` returns structured per-file line coverage | CLI smoke + envelope capture |
| 5 | `novetest coverage diff <run1> <run2>` returns structured deltas for two .NET runs | CLI smoke + envelope capture |
| 6 | `novetest inspect <dotnet_run_id>` Coverage section is populated (not the empty/unavailable shape) | CLI smoke + envelope capture |
| 7 | Existing JaCoCo derive path UNCHANGED — no regression for JUnit/Java coverage | full Coverage suite green |
| 8 | Existing pytest/jest/gotest derive paths UNCHANGED — no regression for the other 3 engines that already worked | full Coverage suite green |

---

## §2. Design (Coverage team's call to refine)

PM proposes the following design. Coverage team may refine if a cleaner
shape surfaces during implementation; report deviations in the handoff.

### §2.1 — Detection heuristic

In `derive_coverage_facts`, the existing JaCoCo detector reads a
specific XML shape. Add a sibling detector for Cobertura.

**Cobertura schema (canonical, Coverlet 6.0.x XPlat output)**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1" branch-rate="1" lines-covered="2" lines-valid="2"
          timestamp="..." version="..." complexity="...">
  <sources>
    <source>/abs/path/to/MathLib</source>
  </sources>
  <packages>
    <package name="MathLib" line-rate="1" branch-rate="1" complexity="...">
      <classes>
        <class name="MathLib.MathOps" filename="MathOps.cs"
               line-rate="1" branch-rate="1" complexity="...">
          <methods>
            <method name="Add" signature="..." line-rate="1" ...>
              <lines>
                <line number="5" hits="1" branch="false"/>
              </lines>
            </method>
            ...
          </methods>
          <lines>
            <line number="5" hits="1" branch="false"/>
            <line number="9" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
```

**Detection signal**: root element is `<coverage>` (vs. JaCoCo's
`<report>`). PM suggests:

```python
def _is_cobertura(root: ElementTree.Element) -> bool:
    return root.tag == "coverage" and root.find("packages") is not None
```

### §2.2 — Per-file derivation

Each `<class>` element has:
- `filename` attribute — RELATIVE to the `<source>` path under `<sources>`
- `<lines>` child with `<line number=N hits=H branch=...>` children

The derivation walks `<packages>/<package>/<classes>/<class>` and for
each class:
1. Resolves the absolute file path: `<source-dir>/<class.filename>`
   (each Cobertura file lists exactly one `<source>` per Coverlet's
   convention; if multiple, prefer the first)
2. For each `<line>`: builds a `CoverageFact` keyed by
   `CodeLocation(file=<resolved_path>, line=<line.number>, symbol=None)`
   with `hits = int(line.hits)`, `kind = "line"`
3. Collects per-file facts into a `CoverageFactSet`

### §2.3 — Branch coverage

Cobertura supports branch coverage via `branch="true"` + `condition-coverage`
attribute. **PM defers branch derivation to a future slice** —
v1 derives lines only, matching the JaCoCo path's current scope. The
derive function MAY read the `branch-rate` attribute as a top-level
fact-set property but does not produce per-location branch facts.

### §2.4 — Path resolution edge cases

Coverlet's `<source>` is usually the *test project's directory* (e.g.
`/abs/path/to/MathLib.Tests/`), but `class.filename` resolves against
the *source under test* (e.g. `MathLib/MathOps.cs` — a sibling
directory). Concretely: Coverlet emits `<source>` with the common
ancestor of all compiled sources, and `filename` relative to that.

**Edge case handling**: if the resolved path doesn't exist on disk
(possible if user ran `novetest run` and then moved files), the
derive MUST emit a `CoverageFactSet` with `mapping_granularity =
"aggregate"` + `kind = "fact-set"` for facts whose paths DID resolve,
and silently drop unresolvable facts. Do NOT fail the derive on
unresolvable paths (the Cobertura XML is still valuable evidence).

If ZERO facts resolve (entire source tree missing), the derive returns
`coverage_outcome.kind = "unavailable"` with a metadata key
`coverage_unavailable_kind = "cobertura-sources-not-found"` per the
v1 metadata-channel convention (`decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`).

### §2.5 — `mapping_granularity`

Per amended `decisions/2026-06-03-coverlet-pertestcoverage-key.md §3`:
the .NET XPlat path is aggregate-effective-default. Coverage engine
hard-codes `mapping_granularity = "aggregate"` for the .NET derive
path. This is correct per v1 contract and matches Manual Test's
empirical evidence (zero per-test files in Cobertura output across
two independent host reproductions).

A future slice (post-MVP) may revisit if Coverlet adds per-test XPlat
output. Not in scope here.

### §2.6 — Wiring up `coverage_outcome.kind`

The orchestration layer's `coverage_outcome` computation already
distinguishes `"fact-set"` vs `"unavailable"` based on whether
`derive_coverage_facts` returned a non-empty `CoverageFactSet`. This
slice's derive returning a populated `CoverageFactSet` should
automatically flip `coverage_outcome.kind` to `"fact-set"` without
orchestration changes.

**Coverage team verifies**: if orchestration changes ARE needed (e.g.
the dispatch logic for which adapter format to derive currently
hard-codes "if JaCoCo only"), STOP and file a `questions/` entry to
PM. Do not silently expand scope into orchestration territory.

### §2.7 — Test placement

- Unit tests: `tests/unit/coverage/test_derive.py` extension for Cobertura cases (Coverage team territory)
- Fixture XML: `tests/fixtures/coverage/cobertura/` (NEW; small canonical Cobertura XML samples)
- Integration test on dotnet path: `tests/integration/coverage/test_dotnet_cobertura_derive.py` (NEW; touches dotnet adapter via integration)
- Update existing `tests/integration/run/test_dotnet_coverage.py` assertions: `coverage_outcome.kind` expectation flips from `"unavailable"` to `"fact-set"` (Coverage team is authorized to update this assertion AS-IS; do not change the dotnet adapter source)

---

## §3. §2.5 binding (equip-and-exercise pre-handoff gate)

This slice touches `tests/integration/run/test_dotnet_coverage.py`
(updating `coverage_outcome.kind` assertions). §2.5 IS BINDING.

Coverage team's pre-handoff gate:
1. **Equipped host** — `dotnet --version >= 8.0` resolvable; `coverlet.collector >= 6.0.2` cached or resolvable. The toolchain shim at `~/.local/share/novetest-toolchains.sh` (if present per host-equip findings) provides this when sourced.
2. **Dotnet-focused integration tests pass** — `uv run pytest -v tests/integration/run/test_dotnet_coverage.py tests/integration/coverage/test_dotnet_cobertura_derive.py` produces **0 skips, 0 fails**.
3. **Full suite pass** — `uv run pytest -q tests/unit tests/integration` produces 0 fails. Skip count documented.
4. **CLI smokes** — at minimum:
   - `novetest run --coverage` on `tests/fixtures/projects/dotnet-test-basic-coverage` → envelope `coverage_outcome.kind = "fact-set"`
   - `novetest coverage show <run_id>` → structured per-file coverage
   - `novetest inspect <run_id>` → Coverage section non-empty

Capture each smoke's envelope shape in the handoff.

---

## §4. DoD bullets (PM ticks at cycle close)

| # | Bullet | Evidence form expected |
|---|---|---|
| 1 | Cobertura detection added to `derive_coverage_facts`; `root.tag == "coverage"` heuristic | grep on `coverage/derive.py` |
| 2 | Per-file line-coverage derivation lands per §2.2 design (or refined equivalent) | unit test against fixture XML |
| 3 | `mapping_granularity = "aggregate"` hard-coded for .NET path per amended Coverlet decision §3 | unit test + grep |
| 4 | Source path resolution handles missing-files gracefully (drop unresolvable; do not fail) per §2.4 | unit test against fixture with intentionally-missing source path |
| 5 | `coverage_outcome.kind = "fact-set"` for .NET runs with Cobertura present (vs. `"unavailable"` pre-slice) | integration test on dotnet fixture; CLI smoke envelope capture |
| 6 | `novetest coverage show <dotnet_run_id>` returns structured per-file coverage | CLI smoke envelope capture |
| 7 | `novetest coverage diff <run1> <run2>` returns structured deltas for .NET runs | CLI smoke envelope capture |
| 8 | `novetest inspect <dotnet_run_id>` Coverage section populated | CLI smoke envelope capture |
| 9 | JaCoCo / pytest / jest / gotest derive paths UNCHANGED; full Coverage suite green for all 4 prior engines | `pytest -q tests/unit/coverage tests/integration/coverage` |
| 10 | `mypy --strict` clean | mypy output |
| 11 | §2.5 pre-handoff gate per §3 above; 0 skips / 0 fails on equipped host; smoke envelopes captured | handoff §"Pre-handoff gate environment" |
| 12 | Cobertura fixture XML(s) land under `tests/fixtures/coverage/cobertura/` | git diff |

---

## §5. Out of scope (NOT in this slice)

- Per-test (per-test-method) attribution on .NET — deferred per amended Coverlet decision §3; would need Coverlet `coverlet.msbuild` opt-in or future xUnit v3 MTP
- Branch coverage per-location facts (line coverage only in v1 per §2.3)
- Cobertura derive for non-.NET adapters (Cobertura is theoretically multi-language but only .NET uses it in our matrix today)
- Orchestration-layer changes (`workflows/run.py`, `cli/app.py` etc.) — if needed, file questions/ entry per §2.6
- Memory engine RunRecord schema additions (Memory team territory; NOT authorized)
- The dotnet adapter source changes (Run team territory; NOT authorized — adapter already produces correct Cobertura XML per `6c7bc76`)
- Phase 4 Localization SBFL on .NET — already lands as `failure_proximity` per amended Coverlet decision R4; no SBFL change needed here

---

## §6. Decisions referenced

| Decision | Honored as |
|---|---|
| `2026-06-03-coverlet-pertestcoverage-key.md` §3 (amended 2026-06-05) | `mapping_granularity = "aggregate"` for .NET path; per-test deferred |
| `2026-06-03-coverlet-pertestcoverage-key.md` R4 | Phase 4 SBFL on .NET = `failure_proximity` mode (already wired; no change needed here) |
| `2026-06-04-equip-and-exercise-for-adapter-cycles.md` §2.5 | Binding pre-handoff gate per §3 |
| `2026-06-06-adapter-warning-surface-v1-metadata-channel.md` | If source paths unresolvable, emit `coverage_unavailable_kind` per v1 metadata-channel convention per §2.4 |
| `2026-05-25-supported-engine-matrix.md` | Coverlet floor 6.0.2 holds; no matrix change |

---

## §7. Effective date

Brief queued 2026-06-06 PM. CEO will dispatch Coverage team when ready.
Expected single-attempt close (no hotfixes); §2.5 equip-and-exercise
gate catches structural defects before handoff.

**On clean Manual Test pass**: the 6th-engine coverage promise from
Phase 2/3 closes; B track of the post-Phase-2.5 backlog clears;
`novetest coverage show/diff/inspect` parity across all 6 engines
achieved.
