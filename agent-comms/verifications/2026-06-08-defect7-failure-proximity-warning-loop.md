---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: pending
created: 2026-06-08
slug: defect7-failure-proximity-warning-loop
related:
  - agent-comms/tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md
  - agent-comms/handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md
  - agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md
---

# Verification — Defect 7: `failure_proximity` formula-noop warning loop

## Merged commit

- **Tip**: `945f8de comms: handoff for Defect 7 failure_proximity warning-loop fix`
- **Functional commit**: `2fd968d fix(localization): Defect 7 — failure_proximity formula-noop warning, no re-derive loop`
- **Base**: `4184cd1 comms: brief B1 polish parallel pair (defect7 + fixed-tests-spec)` (prior main tip)
- **Merge type**: FF-merge (clean, no conflicts)
- **Files**: 6 changed, +936 / −12

## Source handoff consumed

- `agent-comms/handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`

## What landed

A carve-out in `src/novetest/cli/app.py::_rederive_if_cache_overrode_flags` that
recognizes the `failure_proximity`-mode formula-placeholder no-op case. When the
user passes a non-default `--formula` against a `failure_proximity` finding
(whose engine always returns `formula="ochiai"` as a structural placeholder),
the carve-out:

1. **Suppresses** the re-derive that would otherwise be triggered by the
   formula mismatch.
2. **Emits** a single, distinct envelope warning with `code =
   "localization-formula-noop-in-mode"` carrying `requested_formula`,
   `returned_formula`, and `mode` in `details`.
3. **Preserves** the on-disk cache file (no unlink + rewrite) — the load-bearing
   "no infinite loop" proof.

The carve-out is gated on `mode == "failure_proximity" AND formula_mismatch AND
NOT top_n_mismatch`. The compound case (formula + top_n mismatch together)
falls through to the pre-existing `localization-cache-rederived` warning — see
handoff §"Open items / surprises §1" for PM-ratification request.

## Pre-merge test gate (on merged main = `945f8de`)

| Check | Result |
| --- | --- |
| `uv run mypy --strict src/novetest` | **Success: no issues found in 92 source files** |
| `uv run pytest -q tests/unit tests/integration --deselect tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` | **1186 passed, 23 skipped, 1 deselected in 34.18s** |

§2.5 equip-and-exercise gate does **NOT** fire for this slice (task brief
§"§2.5 equip-and-exercise 게이트": the slice touches neither native adapter
src nor adapter integration tests). The single deselected test
(`test_xunit_v3_deferral_...`) is a `.NET SDK 8.0+`-bound test that fails
identically on the unmodified base `4184cd1` — environmental, not a regression
(verified in handoff §"Open items / surprises §5").

## Wire-level envelope shape (verbatim, pinned from merged source)

The new warning lives in `src/novetest/cli/app.py:1097-1141`
(`_build_localization_formula_noop_warning`). Source-grep confirms the structure:

```python
EnvelopeWarning(
    code="localization-formula-noop-in-mode",
    message=(
        f"requested --formula='{requested_formula}' is a no-op in "
        f"'{mode}' mode; engine pins formula='{returned_formula}' as a "
        "placeholder for this mode (no SBFL formula is computed). "
        "Re-running with a different --formula value will not change "
        "the result."
    ),
    details={
        "requested_formula": requested_formula,
        "returned_formula": returned_formula,
        "mode": mode,
    },
)
```

Resulting envelope (sample from the team's integration test capture, paths
match merged source exactly):

```json
{
  "command": "localization",
  "ok": true,
  "data": {
    "localization_outcome": {
      "kind": "fact-set",
      "mode": "failure_proximity",
      "formula": "ochiai",
      "...": "..."
    }
  },
  "warnings": [{
    "code": "localization-formula-noop-in-mode",
    "message": "requested --formula='op2' is a no-op in 'failure_proximity' mode; engine pins formula='ochiai' as a placeholder for this mode (no SBFL formula is computed). Re-running with a different --formula value will not change the result.",
    "details": {
      "requested_formula": "op2",
      "returned_formula": "ochiai",
      "mode": "failure_proximity"
    }
  }]
}
```

## Verification steps — for Manual Test

Use the existing `tests/fixtures/projects/localization-no-coverage` fixture (no
new fixture was added). Setup mirrors the integration test
`tests/integration/cli/test_localization_e2e.py::test_localization_failure_proximity_non_default_formula_emits_noop_warning`.

### Scenario A — the noop carve-out fires (load-bearing)

```bash
# In a tmp workspace, materialize the no-coverage fixture and seed a run
cd $(mktemp -d)
cp -r /path/to/Nove-Test/tests/fixtures/projects/localization-no-coverage/. .
novetest init
novetest run tests/ --no-coverage   # forces failure_proximity mode
# Capture run_id from envelope or .novetest/runs/

RUN_ID="<captured>"
CACHE=".novetest/localization/findings/run_${RUN_ID}/localization_findings.json"
PRE_MTIME=$(stat -c %Y "$CACHE")

novetest localization "$RUN_ID" --formula op2 -o json > /tmp/loc-noop.json
POST_MTIME=$(stat -c %Y "$CACHE")
```

**Expected envelope shape** (`jq` selectors against `/tmp/loc-noop.json`):

| `jq` selector | Expected value |
| --- | --- |
| `.command` | `"localization"` |
| `.ok` | `true` |
| `.data.localization_outcome.kind` | `"fact-set"` |
| `.data.localization_outcome.mode` | `"failure_proximity"` |
| `.data.localization_outcome.formula` | `"ochiai"` (placeholder — NOT `"op2"`) |
| `.warnings \| length` | `1` (exactly one warning) |
| `.warnings[0].code` | `"localization-formula-noop-in-mode"` |
| `.warnings[0].details.requested_formula` | `"op2"` |
| `.warnings[0].details.returned_formula` | `"ochiai"` |
| `.warnings[0].details.mode` | `"failure_proximity"` |

**Cache invariant**: `$PRE_MTIME == $POST_MTIME`. This is the wire-level "no
re-derive loop" proof. Pre-Defect-7, the same invocation would have unlinked +
rewritten this file, bumping the mtime.

### Scenario B — default formula path is unchanged (negative control)

```bash
# Same workspace + run_id, no --formula
novetest localization "$RUN_ID" -o json > /tmp/loc-default.json
```

**Expected**:
- `.ok == true`, exit code `0`
- `.warnings == []` (or omitted) — NO `localization-formula-noop-in-mode` warning
- `.data.localization_outcome.formula == "ochiai"` (same as Scenario A; the
  placeholder is mode-defined, not flag-driven)

### Scenario C — SBFL mode still re-derives on formula mismatch (regression-guard)

The carve-out is mode-scoped. Run against a fixture that DOES produce coverage
(forces `sbfl_per_test` or `sbfl_aggregate`) and pass `--formula op2`:

```bash
# Use any fixture with coverage; e.g. localization-sbfl-* fixtures
cd $(mktemp -d)
cp -r /path/to/Nove-Test/tests/fixtures/projects/localization-sbfl-toy/. .  # or equivalent
novetest init
novetest run tests/   # default WITH coverage
RUN_ID="<captured>"

# First call seeds cache with default formula (ochiai)
novetest localization "$RUN_ID" -o json > /tmp/loc-sbfl-1.json
# Second call with --formula op2 should re-derive
novetest localization "$RUN_ID" --formula op2 -o json > /tmp/loc-sbfl-2.json
```

**Expected on `/tmp/loc-sbfl-2.json`**:
- `.data.localization_outcome.formula == "op2"` (engine actually computed op2)
- `.warnings[0].code == "localization-cache-rederived"` (NOT the new noop code)
- Cache file mtime CHANGED between the two calls (re-derive happened)

This proves the carve-out is properly mode-gated; the SBFL paths are
unchanged.

### Scenario D — second invocation with the same args is idempotent (no loop)

After Scenario A:

```bash
novetest localization "$RUN_ID" --formula op2 -o json > /tmp/loc-noop-2.json
diff /tmp/loc-noop.json /tmp/loc-noop-2.json
```

**Expected**: identical envelopes (modulo any nondeterministic timestamps).
`.warnings[0].code` still `"localization-formula-noop-in-mode"`. Same cache
mtime as Scenario A's `$POST_MTIME`. Proves the loop is broken.

## Critical edge cases worth probing

1. **Compound mismatch — flagged in handoff as PM-ratification point**: A user
   who passes BOTH `--formula op2` AND `--top-n 5` against a
   `failure_proximity` cache (whose current top_n differs) should see
   `localization-cache-rederived` (NOT `localization-formula-noop-in-mode`),
   because the `top_n` mismatch is meaningful in `failure_proximity` mode. The
   formula transition is still observable via the rederived warning's
   `details.previous.formula="ochiai"` field. If Manual Test feels this
   compound path is surprising or hard to discover from the envelope, escalate
   to PM via `agent-comms/findings/` for ratification of alternative shape
   (A: emit both warnings; B: noop dominates; C: current — see handoff §"Open
   items / surprises §1").

2. **`latest` verb mirror**: The `latest` verb path (`novetest localization
   latest`) was extended with the same carve-out (see unit test
   `test_localization_latest.py::...`). Manual Test should exercise it once:
   ```bash
   novetest localization latest --formula op2 -o json
   ```
   on the same workspace. Expected: same noop warning, exit 0.

3. **`details.message` readability**: The warning message is intentionally
   verbose (3 sentences). Read it from the perspective of an AI agent
   consuming the envelope — does it convey "structural noop; retry won't help"
   without ambiguity? If Manual Test thinks the wording could be tighter,
   surface as a low-priority polish observation.

## Anything not obvious during merge

- **Clean FF-merge** — no conflicts. Base `4184cd1` matched main tip exactly.
- **Warning emit location**: kept in `cli/app.py` (NOT engine, NOT
  orchestration/workflows), per the handoff §"Open items / surprises §3"
  rationale: mismatch detection is a CLI-flag-explicitness concern. The
  carve-out lives next to the pre-existing `localization-cache-rederived`
  emit, minimizing code-distance for future readers tracing the warning
  surface.
- **`_make_finding` test helper duplication**: handoff §"Open items §4" flags
  parallel copies in `test_localization.py` and `test_localization_latest.py`.
  Not a regression; both helpers gained the same `mode=...` extension.
  Visibility flag only — Manual Test does not need to act on this.

## Reference

- Task: `agent-comms/tasks/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
- Handoff: `agent-comms/handoffs/localization-team-2026-06-08-defect7-failure-proximity-warning-loop.md`
- Original Defect 7 discovery: `agent-comms/history/2026-06-01-defects-5-6-closed-phase4-modes-narrative-lands.md` §"Defect 7"
- Warning surface contract: `agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md`
