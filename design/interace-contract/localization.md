# Interface Contract - Localization

**Scope:** Localization sub-product. Selects an analyzable Run Record and ranks suspicious Code Locations using failed Test Result context, available Coverage Facts, and (when available) Regression Facts. Localization produces ranked findings with supporting Evidence Citations; it does not prescribe a fix or assign final root cause.

**Upstream references**
- `design/product-plans/subproducts/nove-test-localization.md`
- `design/requirements-analysis/requirements-specification/groups/localization.md`
- `design/requirements-analysis/system-responsibility-model.md` (SR-015, SR-016, SR-021)
- `design/requirements-analysis/domain-model.md`

---

## Conventions

- **External** - Directly invokable by an actor (AI Agent, Developer) through the `novetest` CLI surface.
- **Internal** - Invokable only by other Nove Test modules (Orchestration) within the tool boundary.
- Inputs and outputs use domain-entity vocabulary from `design/requirements-analysis/domain-model.md`.

---

## Localization Interfaces

| Interface | Type | Input | Output |
| --- | --- | --- | --- |
| `novetest localization <run_id>` | External | Run Reference | Localization Finding set (ranked Code Locations with score or equivalent ranking evidence, related failed Test Result references, supporting Evidence Citations) or explicit unavailable state |
| `novetest localization latest` | External | (none; resolved against current Run History) | Localization Finding set for the most recent stored run that has the evidence required for localization-oriented analysis, or explicit unavailable state |
| `derive_localization_findings(run_reference)` | Internal | Run Reference (resolved through Memory) | Localization Finding set with ranked Code Locations, supporting Evidence Citations referencing Test Results, Coverage Facts, and Regression Facts when available |
| `resolve_latest_analyzable_run()` | Internal | (none; uses current Run History) | Run Reference of the most recent run with sufficient evidence for localization, or unavailable state |
| `derive_latest_localization()` | Internal | (none; uses current Run History) | Localization Finding set for the resolved latest analyzable run (composes `resolve_latest_analyzable_run` then `derive_localization_findings`) |
| `get_localization_findings(run_reference)` | Internal | Run Reference | Previously derived Localization Finding set for the run, or unavailable state if not yet derived |
| `check_localization_availability(run_reference)` | Internal | Run Reference | Availability flag indicating whether failed Test Results plus Coverage Facts (and optionally Regression Facts) exist for derivation (used by Orchestration eligibility evaluation) |

---

## Notes

- Localization depends on Memory (`retrieve_run_evidence`), Coverage (`get_coverage_facts` / `derive_coverage_facts`), and optionally Regression (`get_regression_facts`).
- Every Localization Finding preserves traceability to the run evidence used to rank it (NFR-LOC-001) via Evidence Citations attached during derivation.
- Localization may still produce findings without Regression Facts, provided failed Test Results and Coverage Facts are available (REQ-LOC-003 assumption).

---

## Result shape — mode-invariant

A `LocalizationFinding` carries the following shape guarantees regardless of which of the three modes (`sbfl_per_test`, `sbfl_aggregate`, `failure_proximity`) produced it. AI consumers may rely on a single mental model when reading the envelope without branching on `finding.mode`.

### `metadata` key set

The `metadata` dict has the same two **base keys** across all three modes:

| Key | Type | `sbfl_per_test` | `sbfl_aggregate` | `failure_proximity` |
|---|---|---|---|---|
| `changed_files_count` | `int \| None` | `None` (mode does not consult RegressionFactSet) | `int` (≥ 0; count of files in the FLUCCS-style change set) | `int` (≥ 0; same definition as aggregate) |
| `regression_reweighted` | `bool \| None` | `None` (no FLUCCS reweighting in this mode) | `bool` (`True` when ≥ 1 covered file appears in the change set) | `bool` (`True` when ≥ 1 ranked file appears in the change set) |

`None` (vs `0` / `False`) is the principled discriminator: it surfaces "this mode does **not** consult Regression Facts at all" (per-test) as distinct from "consulted, no boost fired" (aggregate / failure_proximity when Regression Facts are absent or the change set is empty).

Mode-specific **optional** keys MAY be present in addition to the two base keys:

- `parse_warnings: list[str]` — one entry per failing test whose failure log could not be parsed (`sbfl_aggregate` and `failure_proximity` only; absent when every failure log parsed cleanly). Each entry has the form `"<node_id>: <reason>"`.

Consumers MUST handle key absence for the optional keys; the base-key set is the stable contract.

### `code_location.file` representation

All three modes emit `code_location.file` in **workspace-relative form** — relative to the workspace root, i.e. one level up from `<workspace>/.novetest/`.

Workspace-relative is the consistent shape across the envelope (matches Coverage `CoverageFactSet.files[*].file_path`, Regression `coverage_change.files_added/removed`, etc.) so AI consumers can join paths from different envelopes without absoluteness-mismatch handling.

**Edge case** — paths outside the workspace (e.g. `/usr/lib/python/.../stdlib.py` in a pytest traceback, or `/rustc/<hash>/.../panicking.rs` in a cargo nextest panic frame) are emitted **absolute** verbatim. Such paths cannot be made workspace-relative meaningfully; the absolute form surfaces as an obvious "not your code" cue. The `failure_proximity` mode is the practical surface for this edge — `sbfl_per_test` and `sbfl_aggregate` source paths from `CoverageFactSet` whose adapter contract already produces workspace-relative paths, so an out-of-workspace path cannot arise there.
