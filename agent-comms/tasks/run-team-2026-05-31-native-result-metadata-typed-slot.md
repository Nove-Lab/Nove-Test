---
from: novetest-pm-team
to: novetest-run-team
type: task
status: pending
created: 2026-05-31
slug: native-result-metadata-typed-slot
related:
  - agent-comms/decisions/2026-05-30-native-result-metadata-slot.md
  - agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - src/novetest/models/native_result.py
  - src/novetest/run/normalizer.py
  - src/novetest/run/adapters/cargo_adapter.py
---

# Task: typed `metadata` slot on `NativeResult` — Issue 2 follow-up

## TL;DR

Per `decisions/2026-05-30-native-result-metadata-slot.md` (Option (b)
chosen 2026-05-30 evening), add a typed `metadata: dict[str, str]`
field to `NativeResult`, have the normalizer copy it through (with
a defensive guard on the `native_exit_code` reserved key), migrate
cargo adapter from `payload["nextest_version"]` to the typed slot,
and audit pytest / jest / gotest adapters for analogous fields in
the same slice.

Closes Issue 2 from the 2026-05-30 cargo E2E sweep
(`nextest_version` silently dropped at the normalizer seam — see
`history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
§"Issue 2"). Replaces the lazy "payload-stash" convention with a
typed contract-layer slot.

**Dispatch ordering**: this slice was binding-gated on the cargo
nextest env-var hotfix
(`tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`,
deleted at the 2026-05-31 cycle close). Hotfix merged at `1e736cc`
and trigger-(b) closed at this cycle. **The slice is now
dispatchable.**

## Cross-territory authorization (READ FIRST)

This slice touches `src/novetest/models/native_result.py`, which is
**Memory team territory** per their charter ("Owns the shared
domain entity models in src/novetest/models/"). PM hereby authorizes
the Run team to make the 1-line typed-field addition to that file
as part of THIS slice, because:

- The diff is dominated by Run-territory changes (normalizer +
  cargo adapter + pytest/jest/gotest adapter audit).
- Run team has fresh hotfix context on cargo adapter internals.
- A single-team slice avoids cross-team coordination overhead for
  a small structural change.
- Splitting into a Memory-only "add field" slice + a Run-only "use
  field" slice would force Run to wait on Memory and create a
  needless 2-cycle latency.

Run team coordinates with Memory team by:
- Cross-referencing this brief's PM authorization in the handoff
  doc
- Including Memory team in any design questions the field
  placement raises (e.g., if `NativeResult` turns out to need a
  bigger refactor than 1 line)

If the slice's actual diff to `models/native_result.py` exceeds
~10 lines or touches related model files (e.g.,
`run_record.py`), STOP and escalate to PM — that would be a
genuine Memory-territory slice that needs a separate task brief.

## Scope (what this slice DOES)

### 1. Add typed metadata field to `NativeResult`

**File**: `src/novetest/models/native_result.py`

Add:
```python
metadata: dict[str, str] = field(default_factory=dict)
```

Placement: follows the existing fields' style (frozen dataclass
conventions; `field(default_factory=dict)` if frozen; plain dict
default if not). Type strictly `dict[str, str]` — NOT
`dict[str, Any]`. Adapter authors stash typed strings (versions,
flags, etc.); non-string metadata uses `payload[...]` (which stays
the per-engine catch-all for transient data).

### 2. Update normalizer overlay with `native_exit_code` guard

**File**: `src/novetest/run/normalizer.py:72` (or wherever
`metadata={"native_exit_code": ...}` is currently constructed)

Change from:
```python
metadata = {"native_exit_code": native_result.returncode}
```

To:
```python
metadata = {"native_exit_code": native_result.returncode}
# Merge adapter-provided metadata, but the native_exit_code reserved
# key is normalizer-controlled — adapters MUST NOT override it.
adapter_metadata = dict(native_result.metadata)
if "native_exit_code" in adapter_metadata:
    raise ValueError(
        f"NativeResult.metadata['native_exit_code'] is reserved for "
        f"the normalizer. Adapter passed: "
        f"{adapter_metadata['native_exit_code']!r}"
    )
metadata.update(adapter_metadata)
```

OR (equivalent, more lenient): pop-and-log warning instead of
raise. PM defers between strict-raise vs pop-and-warn to the
implementing team — strict-raise catches bugs at write time and is
PM's slight preference; pop-and-warn is more forgiving. Either is
acceptable; pin the choice in the docstring.

### 3. Migrate cargo adapter

**File**: `src/novetest/run/adapters/cargo_adapter.py`

Current code at line 299:
```python
payload["nextest_version"] = nextest_version
```

Migrate to:
```python
metadata["nextest_version"] = nextest_version  # was payload[...]
```

Where `metadata` is constructed inside the `NativeResult`
instantiation. Exact mechanical form depends on whether
`_build_*_result()` helpers exist (use them) or whether
`NativeResult(...)` is constructed inline (add a `metadata={...}`
kwarg).

DELETE the old `payload["nextest_version"]` line. The `payload`
dict stays for any per-engine transient data that doesn't need to
surface in `record.json`. If `nextest_version` is the only key
`cargo_adapter.py` stashes in `payload`, the dict may now be
empty for most paths — that's fine.

### 4. Audit pytest / jest / gotest adapters

**Files**:
- `src/novetest/run/adapters/pytest_adapter.py`
- `src/novetest/run/adapters/jest_adapter.py`
- `src/novetest/run/adapters/gotest_adapter.py`

For each adapter, `grep -n "payload\[" <adapter>` and review every
hit. If any adapter stashes a field intended for `record.json`
surface (engine versions, configuration flags, anything an AI
consumer might want to read from a persisted run), migrate it to
`metadata[...]` in the SAME slice. Transient per-engine data
(parser state, intermediate buffers) stays in `payload`.

Report the audit results in the handoff doc:
- Which adapters had record-bound fields in `payload` (likely
  zero — the cargo case was unique because Run team explicitly
  applied the deferred convention)
- Which fields were migrated
- Which fields explicitly stayed in `payload` (with rationale)

### 5. Tests

- **Unit**: in `tests/unit/run/test_normalizer.py` (or equivalent),
  add tests pinning:
  - Adapter metadata overlays correctly onto normalizer metadata
    (positive case)
  - `native_exit_code` reserved-key guard fires when adapter tries
    to override (negative case — either `raises ValueError` or
    `warns + drops`, matching the chosen guard form)
  - Default empty `metadata` dict serializes correctly
    (`record.json` `metadata` field is `{"native_exit_code": <int>}`
    for adapters that don't stash anything, unchanged from current
    behavior)

- **Cargo adapter test update**: in
  `tests/unit/run/adapters/test_cargo_adapter.py`, the existing
  tests that assert on `payload["nextest_version"]` (if any —
  grep the file) must move to asserting on
  `metadata["nextest_version"]`. If there are no such existing
  tests, add ONE pinning the migration target.

- **Full suite**: `uv run pytest -q tests/unit tests/integration`
  must stay green. Baseline at this cycle's tip is **676 passed +
  7 skipped** on Rust-less hosts, **678 passed + 5 skipped** on
  the equipped dev host. Your tip should be **baseline + your new
  tests, no regressions**.

## Out of scope (do NOT touch)

- **Schema versioning bump** for `record.json`. Per the metadata-slot
  decision §"What this decision does NOT decide": "Likely no
  schema bump — the slot is additive; existing `record.json` files
  stay valid; `metadata` field is already present in `record.json`,
  we just add more keys to it." Confirm this is true via grep of
  `tests/fixtures/projects/*/.novetest/memory/runs/**/record.json`
  (if any fixtures pin a frozen `metadata` shape) and a clean
  full-suite run. If the audit reveals the schema must bump,
  STOP and escalate.
- **Build-failure heuristic at `cargo_adapter.py:263`** — Manual
  Test's low-priority polish carry-forward; separate slice.
- **Coverage LCOV dispatch on `engine_name == "cargo-test"`** —
  Coverage team carry-forward; independent slice (no file
  conflict with this slice).
- **MCP transport surface** — typed slot will naturally surface
  via the same serialization path the MCP transport uses; no
  separate MCP code change needed in this slice.
- **Edge 6 Cyclopts help UX** — still deferred-not-queued per CEO
  2026-05-30 decision.

## Pre-flight checks (before opening handoff)

1. **Full gate green**: `uv run pytest -q tests/unit tests/integration`
   → baseline-plus-new-tests, no regressions.
2. **mypy strict clean**: `uv run mypy` → `Success` on N source
   files (N = 70 from this cycle's baseline; +0 expected unless
   you split into a sub-module).
3. **Persisted record.json sanity check**: run a real `novetest
   run` against a fresh `tests/fixtures/projects/cargo-test-basic`
   workspace, grep the persisted `record.json` for the migrated
   `nextest_version` field. Should appear under
   `metadata.nextest_version`. This is the smoking-gun proof the
   migration works end-to-end.
   - Pre-migration grep: `grep -i nextest .../record.json` returns
     nothing (Issue 2 symptom from 2026-05-30 sweep).
   - Post-migration grep: returns the version string under
     `metadata`.
4. **Cargo integration tests**: on the equipped host,
   `uv run pytest -q tests/integration/run/test_cargo_*.py -v`
   → **2 passed**, no skips, no fails. (Same probe as the hotfix
   slice — this confirms you haven't accidentally broken the
   adapter's runtime contract while moving the metadata around.)

## DoD

- [ ] `NativeResult.metadata: dict[str, str]` field added.
- [ ] Normalizer overlay merges adapter metadata correctly.
- [ ] `native_exit_code` reserved-key guard implemented + tested.
- [ ] Cargo adapter migrated (`payload["nextest_version"]` →
      `metadata["nextest_version"]`).
- [ ] pytest / jest / gotest adapters audited; migrations done
      where needed; audit results in handoff.
- [ ] Unit tests for normalizer overlay + reserved-key guard.
- [ ] Cargo adapter test asserts on `metadata["nextest_version"]`.
- [ ] Pre-flight checks above all green.
- [ ] `record.json` schema NOT bumped (or escalation if audit
      forces a bump).
- [ ] `mypy --strict` clean.
- [ ] Full pytest suite green (676+7 / 678+5 baseline + new
      tests, no regressions).

## Handoff format

Standard handoff per team charter at
`agent-comms/handoffs/run-team-2026-05-31-native-result-metadata-typed-slot.md`.
MUST include:

1. **DoD bullets believed closed** (PM verifies + ticks).
2. **Audit results table** — adapters audited; record-bound fields
   migrated; fields explicitly retained in `payload[...]` with
   rationale.
3. **Pre-flight check evidence** — exact gate output + grep proof
   of cargo `record.json` migration.
4. **No `delivery-phasing.md` checkbox implications** (per
   metadata-slot decision §"What this decision does NOT decide" —
   structural refactor of contract layer).
5. **Open questions for PM** — anything you encountered that the
   decision did not anticipate (especially: guard form chosen
   between strict-raise vs pop-and-warn; any unexpected
   model-file touches; any pytest/jest/gotest field that PM should
   know about).

## End-of-work checklist

Per `CLAUDE.md` §Multi-Agent Coordination Harness and your team
charter:

1. Append `WORKLOG.md` entry per format.
2. Write the handoff (above).
3. Run `python3 tools/regen_comms_index.py`.
4. Stage `WORKLOG.md`, the new `agent-comms/` files, and `INDEX.md`
   alongside source. PreToolUse hook blocks the commit if `src/`
   or `tests/` are staged but `WORKLOG.md` is not.

## Cross-references

- **Authoritative decision (read first)**:
  `agent-comms/decisions/2026-05-30-native-result-metadata-slot.md`
  — full rationale + dispatch ordering + (b) chosen + cross-team
  team assignments.
- **Origin of Issue 2**:
  `agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
  §"Issue 2 — `nextest_version` payload-stash lost at normalizer
  seam".
- **Trigger-(b) closure** (proves the typed-slot's downstream
  consumer is ready):
  `agent-comms/history/2026-05-31-cargo-env-var-hotfix-and-trigger-b-closure.md`
  §"Cargo trigger-(b) — CLOSED".
- **Cargo adapter execution-path constraints** (still in force —
  do not violate during migration):
  `agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`.
