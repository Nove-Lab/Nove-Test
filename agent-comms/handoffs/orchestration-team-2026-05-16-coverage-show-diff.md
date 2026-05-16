---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: done
created: 2026-05-16
slug: coverage-show-diff
related:
  - tasks/orchestration-team-2026-05-16-coverage-show-diff.md
  - decisions/2026-05-15-coverage-facts-json-layout.md
  - decisions/2026-05-16-coverage-outcome-envelope-shape.md
  - history/2026-05-16-coverage-cli-wiring.md
---

# Handoff: `novetest coverage show` + `coverage diff` CLI verbs

## Worktree

- Path: `/home/yjshin/dev/novetest-coverage-show-diff`
- Branch: `worktree-coverage-show-diff`
- Base commit: `3df9ec2` (main)

## Files written / modified

Modified:
- `src/novetest/cli/app.py` — new `coverage_app` Cyclopts sub-App with two real handlers (`coverage_show`, `coverage_diff`); shared `_resolve_run_reference` helper; new `_coverage_delta_payload` helper. Imports now pull `compare_coverage_facts`, `get_coverage_facts` from `novetest.coverage` and `CoverageDelta` from `novetest.coverage.compare`. Removed the `_register_group_stub("coverage", ("show", "diff"))` line.
- `tests/integration/cli/test_subcommand_stubs.py` — parametrize list drops `["coverage", "show"]` and `["coverage", "diff"]` (now implemented, covered by `tests/integration/orchestration/test_coverage_cli.py`).

Created:
- `tests/unit/cli/test_coverage_cmd.py` — 6 unit cases (show fact-set / show unavailable / show not-found, diff delta / diff unavailable / diff not-found). Uses capsys + force-JSON-mode + monkeypatched engine seams.
- `tests/integration/orchestration/test_coverage_cli.py` — 6 subprocess E2E cases against the `pytest-coverage` fixture.

NOT created (per task spec — inline kept handler logic under the ~20-line threshold):
- `src/novetest/orchestration/workflows/coverage.py` — handler logic is ~15 lines per verb (store lookup + engine call + envelope projection); inlining keeps `cli/app.py` thin without an extra indirection layer.

## Verification result

- `uv run pytest -q tests/unit tests/integration` → **277 passed** (265 post-stub-drop baseline + 12 new), 1 syrupy snapshot.
- `uv run mypy` → **clean** (49 source files, `--strict`).
- Manual smoke (tmp copy of `tests/fixtures/projects/pytest-coverage/`):
  - `init` → ready.
  - Two `run --coverage tests/` → two persisted runs with `coverage_facts.json` on disk.
  - `coverage show <id1>` → `kind: "fact-set"`, `mapping_granularity: "per-test"`, `percent_covered: 86.67`.
  - `coverage diff <id1> <id2>` → `kind: "delta"`, both summaries equal (same fixture twice), `files_added: []`, `files_removed: []`, `file_deltas: []`.
  - `coverage show fake-id` → `errors[0].code == "not-found"`, exit 2.

## Worklog entry text

```
## 2026-05-16 — phase2 / coverage-show-diff

- Landed: `novetest coverage show <run_id>` and `novetest coverage diff <baseline_run_id> <target_run_id>` promoted from stubs to real handlers in `src/novetest/cli/app.py`. New `coverage_app` Cyclopts sub-App registered the same way `memory_app` is; old `_register_group_stub("coverage", ("show", "diff"))` line removed. `coverage_show` resolves the run_id via `list_run_history` (mirror the `memory_show` pattern → same `not-found` envelope + exit 2 on stale id), calls `coverage.get_coverage_facts`, and projects the result through the existing `_coverage_outcome_payload` helper from the prior slice — REUSE of the frozen v1 shape from `decisions/2026-05-16-coverage-outcome-envelope-shape.md`. `coverage_diff` resolves BOTH run_ids the same way (so either side missing → not-found + exit 2 before any Coverage engine call), then calls `coverage.compare_coverage_facts` and projects through a new `_coverage_delta_payload` helper that discriminates `kind: "delta" | "unavailable"` and emits envelope `data.coverage_delta`. The `delta` body is `CoverageDelta.to_dict()` minus the persisted `schema_version` (envelope-level `schema: novetest/v1` already versions the wire — same convention `coverage_outcome` follows for `fact-set`). The shared `_resolve_run_reference` helper de-duplicates the lookup pattern across both verbs. Tests: new `tests/unit/cli/test_coverage_cmd.py` (6 cases — show fact-set / show unavailable / show not-found, diff delta / diff unavailable / diff not-found; uses capsys + force-JSON-mode + monkeypatched `_require_store`, `list_run_history`, `get_coverage_facts`, `compare_coverage_facts` at the app module seam); new `tests/integration/orchestration/test_coverage_cli.py` (6 subprocess E2E cases — show against `--coverage` run, show against plain run → REQ-COV-004 `kind: "unavailable"` reachable end-to-end for the first time, show against fake id → not-found, diff two coverage runs, diff with one missing-facts side → unavailable, diff with fake target id → not-found). `tests/integration/cli/test_subcommand_stubs.py` parametrize list drops the two now-implemented `coverage` entries.
- Verified: `uv run pytest -q tests/unit tests/integration` → 277 passed (265 prior baseline after stub drop + 12 new); `uv run mypy` → clean (49 source files, `--strict`). Manual smoke against tmp copy of `tests/fixtures/projects/pytest-coverage/` (`uv run --with /home/yjshin/dev/novetest-coverage-show-diff --with pytest-json-report --with pytest-cov --with 'coverage[toml]' novetest …`): `init` → ready; two `run --coverage tests/` → IDs `01KRRDQZ0D94PC1BCBJ96J78ST` / `01KRRDQZY4N7HZRD8CGTYSVGVQ`; `coverage show <id>` → `kind: "fact-set"`, `mapping_granularity: "per-test"`, `percent_covered: 86.67`; `coverage diff <id1> <id2>` → `kind: "delta"`, both summaries equal (same fixture twice), `files_added: []`, `files_removed: []`, `file_deltas: []` (compact-payload optimization in `compare_coverage_facts` omits unchanged-file entries); `coverage show fake-id` → `errors[0].code == "not-found"`, exit 2.
- Left open: Phase 2 DoD #2 closed by this slice (and `kind: "unavailable"` branch is now end-to-end reachable, closing the Manual Test gap from the prior cycle). DoD #3 (`inspect <run_id>` Coverage section) and #4 (NFR-COV-002 50k-location perf) explicitly out of scope. The proposed `data.coverage_delta` envelope shape in the task spec matches what this slice emits VERBATIM (`kind` + 9 body fields for `delta`; `kind` + `run_reference` + `reason` + `detail` for `unavailable`) — PM may freeze it in a follow-up `decisions/2026-05-16-coverage-delta-envelope-shape.md` if any other CLI verb is expected to emit a coverage delta (currently only `coverage diff` and the future `compare` orchestration verb).
- Gotcha: `CoverageDelta.to_dict()` includes `schema_version: 1` from the persistence layer; the envelope projection strips it because envelope versioning lives at the top-level `schema` field. Forgetting the strip would leak two different versioning schemes onto the wire — confusing for AI agents. The two-pass run_id resolution in `coverage_diff` (both lookups happen BEFORE any Coverage engine call) makes the not-found path cheap and deterministic; reversing the order would let `compare_coverage_facts` start work just to surface a `run-not-found` from inside `get_coverage_facts` — same outcome but extra IO. The same `capsys` vs `monkeypatch sys.stdout` gotcha from the prior cycle (history `2026-05-16-coverage-cli-wiring.md` §3) was avoided up front in the new unit test file. The integration test for `kind: "unavailable"` uses a plain `novetest run` (no `--coverage`) to create a memory entry without `coverage_facts.json` — this is the cleanest way to exercise the `missing-derived-facts` branch without manually deleting files on disk.
- Next: Phase 2 DoD #3 — `novetest inspect <run_id>` Coverage section. The handler composes `memory/retrieve_run_evidence` + `coverage/get_coverage_facts` (REUSE of the same `_coverage_outcome_payload` projection introduced here) + (Phase 3+) regression / localization / replay sections inside one aggregate envelope. Sized small if scoped to Memory + Coverage only this cycle. DoD #4 (50k-location perf) needs a perf-fixture proposal first; PM is expected to recruit `performance-engineer` for the scoping.
```

## DoD bullets believed closed

- **Phase 2, bullet #2** — "`novetest coverage diff` returns structured deltas with stable Code Location identity."

  Bonus: the `kind: "unavailable"` envelope branch (frozen in `decisions/2026-05-16-coverage-outcome-envelope-shape.md`) is now reachable end-to-end via `novetest coverage show <run-without-coverage-id>`, closing the test-gap Manual Test flagged in the prior cycle's findings.

NOT claimed: DoD #1 (already closed prior cycle), DoD #3 (`inspect` — separate slice), DoD #4 (50k-location perf — separate slice).

## Proposed `data.coverage_delta` envelope shape (final, as emitted)

The shape matches the task spec's proposal verbatim. No deviation.

### `kind: "delta"` — successful diff

```json
{
  "kind": "delta",
  "baseline_run_reference": { "schema_version": 1, "run_id": "<ULID>", "created_at": <epoch_ms> },
  "target_run_reference":   { "schema_version": 1, "run_id": "<ULID>", "created_at": <epoch_ms> },
  "baseline_granularity": "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "target_granularity":   "per-test" | "per-test-class" | "per-test-file" | "aggregate",
  "summary_before": { ... CoverageSummary.to_dict() ... },
  "summary_after":  { ... CoverageSummary.to_dict() ... },
  "files_added":   ["new_file.py", ...],
  "files_removed": ["removed_file.py", ...],
  "file_deltas": [
    {
      "file_path": "changed.py",
      "newly_covered_lines":   [5, 7, ...],
      "newly_uncovered_lines": [],
      "newly_covered_branches":   [[3, 5], ...],
      "newly_uncovered_branches": [],
      "summary_before": { ... },
      "summary_after":  { ... }
    }
  ]
}
```

### `kind: "unavailable"` — either side lacks derived facts

```json
{
  "kind": "unavailable",
  "run_reference": { "schema_version": 1, "run_id": "<ULID>", "created_at": <epoch_ms> },
  "reason": "missing-derived-facts" | "run-not-found" | "missing-native-payload" | "native-payload-corrupt" | "incomparable-granularity",
  "detail": "human-readable explanation"
}
```

### Binding constraints (mirror the `coverage_outcome` decision)

1. `kind` is the discriminator.
2. Per-kind required fields are mandatory.
3. Persisted `CoverageDelta.schema_version` is intentionally stripped on the wire (envelope-level `schema: novetest/v1` already versions everything in `data`).
4. `file_deltas` is compact: files with no actual line/branch transition are omitted (consumer rule: absence ≡ "no change"). This is a `compare_coverage_facts` engine-side optimization; the envelope is just passing it through.
5. `run_reference` in `unavailable` identifies which side was unavailable — could be baseline or target depending on which side's `get_coverage_facts` returned first.

PM call on whether to promote to a `decisions/` entry: only needed if another CLI verb will emit a coverage delta. Currently only `coverage diff` here and the future `compare` orchestration verb (Phase 3) would; if Phase 3's `compare` reuses this verbatim, freezing makes sense.

## Envelope-schema implications

- `novetest coverage show` envelope: `data.coverage_outcome` reusing the frozen v1 shape from `decisions/2026-05-16-coverage-outcome-envelope-shape.md`. No new shape introduced.
- `novetest coverage diff` envelope: NEW `data.coverage_delta` block (see "Proposed shape" above). Mirrors the `coverage_outcome` discrimination pattern but with `kind: "delta" | "unavailable"`.
- The envelope-level `schema: novetest/v1` is **unchanged** — both blocks are additive extensions to `data` on commands that opt into coverage. No `decisions/` entry strictly required for the slice to ship; recommended for `coverage_delta` once a second consumer appears.
- Both verbs always emit a meaningful outcome (no omission case for either `coverage_outcome` on `show` or `coverage_delta` on `diff` — they're the verb's reason for existing).

## Open items / surprises

- **`kind: "unavailable"` branch is now end-to-end reachable.** Manual Test flagged this as a coverage gap in the prior cycle (the projection was unit-locked but couldn't be exercised by any user-typed command). `coverage show <run-id-without-coverage>` is the natural cure and is exercised in the new integration suite.
- **Two-pass run_id resolution in `coverage_diff`.** Both lookups happen before any Coverage engine call so the not-found path stays deterministic and cheap. Reverse ordering would surface the same outcome via `compare_coverage_facts → get_coverage_facts → CoverageUnavailable(reason="run-not-found")`, but at the cost of one extra IO trip and an inconsistent error path between `show` and `diff`.
- **Compact `file_deltas` payload.** `compare_coverage_facts` omits per-file entries with no actual transition (this is by Coverage team's design — the envelope just passes it through). Consumers should treat the absence of a file in `file_deltas` as "no change", not "unknown". This is documented in `coverage/compare.py` but worth surfacing in any future AI-agent-facing doc.
- **No `pyproject.toml` touch.** As task spec said, no new deps needed.
- **No charter-cross touches this slice.** Pure Orchestration territory — `cli/app.py`, `tests/unit/cli/`, `tests/integration/orchestration/`, `tests/integration/cli/test_subcommand_stubs.py`.
- **One commit on the worktree branch.** Will be reported below in the "Reporting" section per the standard pattern.
