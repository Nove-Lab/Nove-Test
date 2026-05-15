---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-15
slug: coverage-facts-json-layout
related:
  - handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md
---

# Decision: `coverage_facts.json` v1 on-disk layout (frozen contract)

CEO-approved on 2026-05-15. Promotes the layout proposed in
`agent-comms/handoffs/coverage-team-2026-05-14-coverage-fact-set-foundation.md`
to a binding contract so downstream consumers (Regression, Localization,
Orchestration) can rely on field names without re-litigation.

## Decision

The persisted shape of `<store>/coverage/facts/run_<run_id>/coverage_facts.json`
(written by `coverage/derive_coverage_facts`, read by
`coverage/get_coverage_facts` and any cross-engine consumer) is **frozen at
`schema_version: 1`** in the shape implemented by
`src/novetest/models/coverage_fact_set.py` as of commit `dee3252`. The
authoritative shape is:

```jsonc
{
  "schema_version": 1,
  "run_reference": {
    "schema_version": 1,
    "run_id": "<26-char ULID>",
    "created_at": <epoch_ms>
  },
  "engine_name": "pytest",                 // string, native engine identifier
  "ecosystem": "python",                   // string, ecosystem tag (see run/engine_selector)
  "mapping_granularity": "per-test",       // enum, required, validated at construction
  "summary": {
    "num_statements": 100,
    "covered_statements": 80,
    "missing_statements": 20,
    "excluded_statements": 0,
    "num_branches": 30,
    "covered_branches": 25,
    "missing_branches": 5,
    "percent_covered": 80.0
  },
  "files": [
    {
      "file_path": "src/pkg/calc.py",     // string, workspace-relative
      "executed_lines": [1, 2, 3, 5, 6, 8],
      "missing_lines": [10, 11],
      "excluded_lines": [],
      "executed_branches": [[3, 5], [5, 6]],   // [[from_line, to_line], ...]
      "missing_branches": [[3, 10]],
      "summary": { /* same shape as top-level summary */ },
      "line_contexts": {                       // present when granularity == per-test
        "2": ["tests/test_calc.py::test_add"],
        "3": ["tests/test_calc.py::test_add", "tests/test_calc.py::test_sub"]
      }
    }
  ],
  "derived_at": <epoch_ms>,
  "metadata": {
    // open-ended, engine-specific debug info — NOT part of the wire contract
    "coverage_py_version": "7.6.0",
    "show_contexts": true,
    "branch_coverage": true
  }
}
```

### Binding constraints

1. **`mapping_granularity` is mandatory.** Allowed values: `"per-test"`,
   `"per-test-class"`, `"per-test-file"`, `"aggregate"`. Validated at
   `CoverageFactSet` construction; an invalid value is a programmer error.
2. **Summary counters are named `*_statements`, not `*_lines`.** coverage.py
   reuses `missing_lines` to mean both "count" (integer in summary) and "line
   numbers" (list in file entry). Renaming the summary counters removes the
   overload at this layer.
3. **Branches are `[from_line, to_line]` pairs** in `executed_branches` and
   `missing_branches`, matching coverage.py's native shape. Localization
   (Phase 4) consumes these directly as Code Locations.
4. **`line_contexts` keys are stringified line numbers on the wire** (JSON
   object keys must be strings) and become `int` on read. Values are
   **sorted lists of test node IDs** with coverage.py's `|<phase>` suffix
   already stripped at parse time. The empty-string context (module-import
   scope, no attribution) is dropped.
5. **`line_contexts` is empty when `mapping_granularity` is coarser than
   `per-test`.** Consumers MUST NOT rely on it for `per-test-class`,
   `per-test-file`, or `aggregate` granularities.
6. **`file_path` is workspace-relative.** The pytest adapter enforces this via
   `[run] relative_files = True` in its generated `.coveragerc`; other
   engine adapters MUST do the equivalent. Absolute paths are a contract
   violation.
7. **`metadata` is explicitly NOT part of the wire contract.** It carries
   engine-specific debug info (e.g. `coverage_py_version`); consumers MUST
   NOT pattern-match on its keys for behavior. A future contract change to
   `metadata` does not bump `schema_version`.
8. **`percent_covered` is engine-reported, not recomputed.** The native
   engine's rounding is preserved so the value matches what the native CLI
   reports for the same run.

### Read-side tolerance (compatibility seam)

`from_dict` accepts the following deviations to keep Run-adapter integration
loose while the wire format is young — these are NOT relaxations of the
write-side contract:

- `excluded_statements` may be omitted on read (defaults to 0). The pytest
  adapter writes it; other engines that don't track it can omit.
- `metadata` may be omitted on read (defaults to `{}`).
- `line_contexts` may be omitted on read (defaults to `{}`).

Any other omitted required field raises `ValueError` at `from_dict` time.

### Out of scope (intentionally NOT frozen here)

This decision freezes the **persisted on-disk shape only**.

- `CoverageDelta` (return of `compare_coverage_facts`) and
  `FileCoverageDelta` are operation-result types, not persisted; their shape
  is owned by Coverage Team and may evolve without a `schema_version` bump.
- `CoverageAvailability` (return of `check_coverage_availability`) is an
  operation-result type, same treatment.
- The path itself (`<store>/coverage/facts/run_<run_id>/coverage_facts.json`)
  is already load-bearing — Memory's `_availability_flags` probes for this
  exact name to auto-flip `MemoryEntry.has_coverage_facts`. Renaming the file
  requires a coordinated change in Memory + Coverage + a `schema_version`
  bump.

## Rationale

- **Why freeze now?** Three downstream sub-products (Regression Phase 3,
  Localization Phase 4, Orchestration `inspect`/`compare`) will read this
  file by field name. Freezing the contract before any of them ship prevents
  a cross-team rename cascade later.
- **Why `*_statements`?** Eliminates the coverage.py-native ambiguity between
  "count of missing" (summary) and "list of missing line numbers" (file
  entry). Both can appear in the same payload; distinct names make grep,
  jq, and code reviews unambiguous.
- **Why `metadata` is open-ended?** Engine-specific signal that's useful for
  debugging (`coverage_py_version`) but not for cross-engine logic. Locking
  its schema would invite contract churn every time a new adapter ships.
- **Why scope to persisted shape only?** Operation-result types are
  cheaper to evolve in-process; freezing them too early creates friction
  without protecting any cross-process consumer.

## Affected teams / files

- **Coverage Team** — owner of `src/novetest/models/coverage_fact_set.py`,
  `src/novetest/coverage/persistence.py`, `src/novetest/coverage/parser.py`.
  Any change to the persisted shape now requires `schema_version` bump +
  migration plan + this decision's supersession.
- **Memory Team** — `_availability_flags` probe path remains
  `<store>/coverage/facts/run_<run_id>/coverage_facts.json`; the filename
  is part of the contract.
- **Regression Team (Phase 3)** — may read `coverage_facts.json` directly
  via `coverage/get_coverage_facts` to compose Regression + Coverage deltas
  in `novetest compare`. Field names above are binding.
- **Localization Team (Phase 4)** — consumes `line_contexts` for test-to-code
  attribution; `executed_branches` / `missing_branches` pairs serve as Code
  Locations for branch-resolution SBFL.
- **Orchestration Team** — `inspect` and `coverage show/diff` verbs serialize
  this shape (or a subset) to the JSON envelope. The envelope view may
  rename / project fields for the public API, but the on-disk wire is
  frozen.
- **Run Team (and future polyglot adapter teams)** — adapters MUST emit
  workspace-relative `file_path`s (constraint #6). The pytest adapter
  already enforces this; new adapters added by Phase 2.5+ inherit the
  obligation.
- **Design docs** — `design/interace-contract/coverage.md` may add a link to
  this decision when next edited by Coverage Team; not required by this
  decision.

## Effective date

2026-05-15. Already on `main` as of commit `dee3252`.

## Supersedes

None. First binding decision on the Coverage on-disk wire format.
