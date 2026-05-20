---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification-request
status: pending
created: 2026-05-20
slug: inspect-aggregated-view
related:
  - handoffs/orchestration-team-2026-05-20-inspect-aggregated-view.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
---

# Verification: `novetest inspect <run_id>` — aggregated single-run view

## Merged commit

- `8d1db6f` — `feat(orchestration): build novetest inspect aggregated single-run view`
- `88da33a` — `comms: handoff for inspect-aggregated-view slice`
- main HEAD after this cycle's full merge: `88da33a`.

## Source handoff consumed

- `handoffs/orchestration-team-2026-05-20-inspect-aggregated-view.md`

## Merge notes

- Rebased onto main; one WORKLOG.md conflict resolved surgically
  (newest-on-top ordering only — no code touched). Branch landed
  fast-forward.
- Post-merge full gate on the combined tree (all 5 slices this cycle):
  `uv run pytest -q tests/unit tests/integration` -> **334 passed,
  3 skipped**; `uv run mypy` -> **clean, 52 source files**. The 3 skips
  are Node-dependent jest integration tests (no Node.js on this box).

## What changed

`novetest inspect <run_id>` was a flat `not-implemented` stub; it is now a
real command that produces an aggregated read-only view of ONE already
stored run. It executes nothing -- it reads the Run Record + cached
coverage facts.

## Verification steps for Manual Test

All paths below were pinned by running the actual merged CLI -- copy-paste
verbatim.

### 1. Coverage-run inspect (happy path)

```sh
# fresh copy of the pytest-coverage fixture into a scratch dir
cp -r tests/fixtures/projects/pytest-coverage/. /tmp/nv-inspect-smoke/
cd /tmp/nv-inspect-smoke
novetest init
novetest run --coverage tests/        # grab run_id from: data.memory_entry.entry_id
novetest inspect <run_id>
```

`novetest inspect <run_id>` returns exit 0 and this envelope shape
(values vary; **structure** is what to confirm):

```json
{
  "command": "inspect",
  "data": {
    "coverage_outcome": {
      "kind": "fact-set",
      "mapping_granularity": "per-test",
      "run_reference": { "created_at": <int>, "run_id": "<ULID>", "schema_version": 1 },
      "summary": {
        "covered_branches": <int>, "covered_statements": <int>,
        "excluded_statements": <int>, "missing_branches": <int>,
        "missing_statements": <int>, "num_branches": <int>,
        "num_statements": <int>, "percent_covered": <float>
      }
    },
    "run_reference": { "created_at": <int>, "run_id": "<ULID>", "schema_version": 1 },
    "run_summary": {
      "ecosystem": "python",
      "engine_name": "pytest",
      "status": "passed",
      "summary_counts": { "collected": <int>, "passed": <int>, "total": <int> },
      "target_expression": "tests/",
      "target_type": "directory",
      "tombstoned": false
    },
    "sub_reports": {
      "coverage": "available",
      "localization": "unavailable",
      "regression": "unavailable",
      "replay": "unavailable"
    }
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

Confirm: `data.coverage_outcome.kind == "fact-set"`,
`data.sub_reports.coverage == "available"`, and
`data.coverage_outcome.run_reference.run_id == data.run_reference.run_id`.

### 2. Plain-run inspect (coverage unavailable)

```sh
cd /tmp/nv-inspect-smoke
novetest run tests/                   # NO --coverage; grab run_id again
novetest inspect <run_id>
```

`data.coverage_outcome` and `data.sub_reports` then read (verbatim from
the merged CLI):

```json
"coverage_outcome": {
  "detail": "No coverage_facts.json found for this run; call derive_coverage_facts first",
  "kind": "unavailable",
  "reason": "missing-derived-facts",
  "run_reference": { "created_at": <int>, "run_id": "<ULID>", "schema_version": 1 }
},
"sub_reports": {
  "coverage": "unavailable", "localization": "unavailable",
  "regression": "unavailable", "replay": "unavailable"
}
```

### 3. Unknown run_id -> `not-found`, exit 2

```sh
cd /tmp/nv-inspect-smoke
novetest inspect 01AAAAAAAAAAAAAAAAAAAAAAAA ; echo "exit=$?"
```

Returns exit **2** and:

```json
{
  "command": "inspect",
  "data": {},
  "errors": [
    { "code": "not-found", "details": {},
      "message": "No Memory Entry for run_id='01AAAAAAAAAAAAAAAAAAAAAAAA'" }
  ],
  "ok": false,
  "schema": "novetest/v1",
  "warnings": []
}
```

## Critical edge cases worth probing

- **Uninitialized tree** -- run `novetest inspect <anything>` in a dir with
  no `.novetest/` store. Expect a structured `uninitialized` envelope,
  exit 2, **no Python traceback** leaking to stderr.
- **Tombstoned run** -- a run that was tombstoned should still be
  inspectable: `data.run_summary.tombstoned` flips to `true` but the call
  still returns exit 0 with the view populated (not `not-found`).
- **`run_reference` carries three keys** -- `run_id`, `created_at`, AND
  `schema_version: 1`. The frozen `coverage_outcome` decision doc
  illustrates only the first two; the real projection passes the full
  `RunReference.to_dict()`. This is consistent across `coverage show`
  too -- not a drift.
- **`sub_reports` always has exactly four keys** -- `coverage`,
  `regression`, `localization`, `replay`. Only `coverage` is dynamic this
  phase; the other three are hard `"unavailable"` until their engines
  land. Confirm no key is ever missing.

## Reporting

Write findings to `agent-comms/findings/manual-test-team-2026-05-20-inspect-aggregated-view.md`.
