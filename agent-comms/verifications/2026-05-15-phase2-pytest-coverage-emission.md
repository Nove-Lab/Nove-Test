---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-05-15
slug: phase2-pytest-coverage-emission
related:
  - handoffs/run-team-2026-05-15-pytest-coverage-emission.md
  - verifications/2026-05-15-phase0-release-and-phase2-coverage-foundation.md
  - questions/main-branch-team-2026-05-15-run-team-pytest-coverage-emission-uncommitted.md
---

# Verification request: pytest adapter — per-test coverage emission (Phase 2 entry)

Third slice of today's Phase 2 entry pass. This was held back from the
first merge pass because the Run Team's worktree had no commits at the
time — see the resolved question file linked above. Run Team committed
as `4d81912` and Main Branch rebased + merged it as `6ff91c5`.

With this slice on `main`, the Phase 2 end-to-end Coverage flow is **now
mechanically exercisable** for the first time (modulo the missing
Orchestration `--coverage` CLI flag, which is a separate downstream
slice).

## Merged commit

- `6ff91c5` — `feat(run): emit per-test coverage from pytest adapter`

Source handoff consumed:
`agent-comms/handoffs/run-team-2026-05-15-pytest-coverage-emission.md`
(handoff front-matter says `status: ready` rather than `done`; the work
is substantively complete and the test gate is green, so Main Branch
treated this as a process-nit and merged anyway — PM may want to remind
teams to flip the status field on next pass).

Fast-forwarded onto `547a9f8` (the post-comms commit from the earlier
pass today). Linear history preserved.

## Test gate (run by Main Branch after merge)

| Step | Command | Result |
| --- | --- | --- |
| Sync new dev deps | `uv sync --dev --frozen` | added `pytest-cov 7.1.0`, `coverage 7.14.0` |
| pytest | `uv run pytest -q tests/unit tests/integration` | **258 passed** (+2 from Run; +1 snapshot) |
| mypy | `uv run mypy` | clean — 49 source files (no source-file count change) |

The +2 deltas are the two new adapter tests:
`test_coverage_emission_produces_contexts_and_missing_branches` and
`test_coverage_missing_plugin_raises_missing_plugin`. The Run Team
also tightened the pre-existing happy-path test to assert
`coverage_json`/`coverage_xml` keys are **absent** when
`collect_coverage=False`.

## Conflict resolution notes

One conflict at rebase, same shape as the Coverage merge: `WORKLOG.md`
top entry. Resolved surgically by stacking the Run entry above the
existing Coverage + Release entries. All entry bodies are byte-identical
to the originals; only position/separators changed. `agent-comms/INDEX.md`
auto-merged. No source-code conflicts.

Note one detail in the merged commit message that wasn't in the
2026-05-15 handoff snapshot: a late finding caught during commit prep —
coverage.py's intermediate SQLite cache (`.coverage`) was landing in the
SuT's cwd, which would pollute a user's repo. Fixed by pinning
`[run] data_file = <artifact_dir>/.coverage` in the generated rc, with a
test assertion that the workspace stays clean. Worth a probe below.

## What to verify

### A. Unit + integration suite stability

```
uv run pytest -q tests/unit tests/integration
```
Expect: **258 passed** (one snapshot).

### B. Adapter contract — coverage default-off, on-by-flag

```
uv run pytest -q tests/unit/run/adapters/test_pytest_adapter.py -v
```
Expect: all pytest_adapter tests green, including:
- `test_coverage_emission_produces_contexts_and_missing_branches`
- `test_coverage_missing_plugin_raises_missing_plugin`
- The default-path test asserting `coverage_json` / `coverage_xml` are
  **absent** from `artifact_paths` when `collect_coverage` is not passed.

### C. End-to-end Python-API smoke (the slice's whole point)

The CLI does not yet expose `--coverage`. Drive the API directly. From
the repo root:

```bash
# Pick a fresh temp workspace
WORKSPACE=$(mktemp -d)
cp -r tests/fixtures/projects/pytest-coverage "$WORKSPACE/sut"
ARTIFACT_DIR=$(mktemp -d)

uv run python - <<'PY'
import asyncio, os, json
from pathlib import Path
from novetest.run.adapters.pytest_adapter import run_pytest

workspace = Path(os.environ["WORKSPACE"]) / "sut"
artifact_dir = Path(os.environ["ARTIFACT_DIR"])

native = asyncio.run(run_pytest(
    workspace=workspace,
    artifact_dir=artifact_dir,
    target=None,
    collect_coverage=True,
))
print("returncode:", native.returncode)
print("artifact_paths keys:", sorted(native.artifact_paths))
cov = json.loads((artifact_dir / "native" / "coverage.json").read_text())
print("files in coverage:", sorted(cov["files"]))
clf = cov["files"]["pytest_coverage/classifier.py"]
print("missing_lines:", clf.get("missing_lines"))
print("missing_branches:", clf.get("missing_branches"))
print("summary.percent_covered:", cov["totals"]["percent_covered"])
print("contexts has nodeids:",
      any("|run" in k for ctxs in clf.get("contexts", {}).values() for k in ctxs))
PY
```

Expect:
- `returncode: 0`
- `artifact_paths keys: ['coverage_json', 'coverage_xml', 'pytest_json_report', 'stderr', 'stdout']`
  (the new two keys present alongside the existing three).
- `files in coverage` includes `pytest_coverage/classifier.py`.
- `missing_lines: [16]` (the deliberate `return "negative"`).
- `missing_branches: [[13, 16]]`.
- `summary.percent_covered`: 80.0.
- `contexts has nodeids: True`.

### D. The SuT-workspace-cleanliness gotcha (late finding)

Run Team caught during commit prep that coverage.py's `.coverage` SQLite
cache would otherwise land in cwd. The fix pins it under `artifact_dir`.
Confirm:

```
# After step C above runs:
test ! -e "$WORKSPACE/sut/.coverage" && echo "OK: SuT clean" || echo "FAIL: SuT polluted"
test -e "$ARTIFACT_DIR/.coverage" && echo "OK: cache in artifact dir" || echo "FAIL: cache missing"
```

Expect both `OK` lines.

Also check the per-run `.coveragerc` is in `artifact_dir`, not in the SuT:
```
test ! -e "$WORKSPACE/sut/.coveragerc" && echo "OK"
test -e "$ARTIFACT_DIR/.coveragerc" && echo "OK"
```

### E. Bridge Run → Coverage (the new end-to-end)

With this slice merged, the Coverage engine's `derive_coverage_facts`
can now consume a real native payload (not just the checked-in fixture).
Probe the bridge:

```bash
uv run python - <<'PY'
import asyncio, os, json
from pathlib import Path
from novetest.run.adapters.pytest_adapter import run_pytest
from novetest.coverage.parser import parse_coverage_json

workspace = Path(os.environ["WORKSPACE"]) / "sut"
artifact_dir = Path(os.environ["ARTIFACT_DIR"])

native = asyncio.run(run_pytest(
    workspace=workspace,
    artifact_dir=artifact_dir,
    target=None,
    collect_coverage=True,
))
payload = json.loads((artifact_dir / "native" / "coverage.json").read_text())
facts = parse_coverage_json(
    payload,
    engine_name="pytest",
    ecosystem="python",
    run_reference=None,
)
print("granularity:", facts.mapping_granularity)
print("percent_covered:", facts.summary.percent_covered)
print("file count:", len(facts.files))
clf = next(f for f in facts.files if f.file_path.endswith("classifier.py"))
print("classifier missing_lines:", clf.missing_lines)
print("any context has |suffix:",
      any("|" in n for line_ctxs in clf.line_contexts.values() for n in line_ctxs))
print("empty-string context dropped:",
      "" not in {n for line_ctxs in clf.line_contexts.values() for n in line_ctxs})
PY
```

Expect:
- `granularity: per-test`
- `percent_covered: 80.0`
- `classifier missing_lines: [16]`
- `any context has |suffix: False` (parser strips them)
- `empty-string context dropped: True`

This is the first time the Run + Coverage bridge is exercisable end-to-end.

### F. Missing-plugin error path

The handoff documents that with `collect_coverage=True` and pytest-cov
absent, the adapter should raise
`AdapterInvocationError(kind="missing-plugin")`. The unit test
`test_coverage_missing_plugin_raises_missing_plugin` already verifies
this via a `PYTHONPATH` stub. Eyeball the test code if you want to
confirm the surface; running the unit test (step B) is sufficient.

## Critical edge cases to probe

- **Determinism across reruns.** Run step C twice into the same
  `ARTIFACT_DIR` — the second run must overwrite cleanly (no stale
  `.coverage` SQLite locking issues) and produce identical
  `coverage.json` modulo coverage.py's internal timestamps.
- **Workspace cleanliness with relative test paths.** The handoff says
  `--cov=.` measures cwd-relative everything, including the fixture's
  own `tests/`. Confirm that `cov["files"]` contains BOTH
  `pytest_coverage/classifier.py` AND the fixture's `tests/test_classifier.py`
  (the adapter does not filter; that's Coverage engine's concern).
- **Context phase-suffix variety.** Look at `cov["files"]["pytest_coverage/classifier.py"]["contexts"]`
  and confirm at least one entry uses the `<nodeid>|run` shape. The
  parser handles this; the raw payload must produce it.
- **`coverage[toml]` import resolution.** `pyproject.toml` dev-deps now
  include `coverage[toml]>=7.0`. After `uv sync --dev --frozen`,
  `uv run python -c "from coverage import Coverage; print(Coverage)"`
  must succeed — confirms the right extras are pulled.

## Phase 2 DoD bullets (still NOT closeable by this slice alone)

Per the handoff: **no Phase 2 DoD bullet closes from this slice in
isolation**. DoD 1 (`novetest test --coverage` emits per-test coverage)
needs Orchestration to wire the `--coverage` CLI flag through
`run_target_in_store` to the adapter's `collect_coverage` kwarg. DoD 2
(`novetest coverage diff`) and DoD 3 (`inspect` coverage section) need
Orchestration's `coverage` verbs. The combined effect of today's three
slices is that **everything below the CLI surface** is ready; the next
Orchestration slice should close the user-visible DoD bullets in one
step.

## Reporting back

Manual Test should write findings to
`agent-comms/findings/2026-05-15-phase2-pytest-coverage-emission.md`
covering each lettered probe above, plus any unexpected behavior. If
end-to-end (step C, E) shows surprising output shape, that's worth a
question to PM before downstream slices ship.
