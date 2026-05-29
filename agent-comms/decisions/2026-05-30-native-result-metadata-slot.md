---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-05-30
slug: native-result-metadata-slot
related:
  - agent-comms/history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md
  - agent-comms/decisions/2026-05-29-cargo-adapter-v1-without-rust-e2e.md
  - agent-comms/tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md
  - src/novetest/run/normalizer.py
  - src/novetest/run/adapters/cargo_adapter.py
---

# Decision: typed `metadata` slot on `NativeResult` — payload-stash convention rejected

CEO-approved 2026-05-30 (evening). Resolves the deferred convention
question from
`decisions/2026-05-29-cargo-adapter-nextest-primary.md` §"What this
does NOT decide" item 5, which the 2026-05-30 cargo sweep findings
sharpened into a binary choice
(`history/2026-05-30-localization-warnings-and-cargo-trigger-b-reopened.md`
§"Issue 2 — `nextest_version` payload-stash lost at normalizer seam").

## Context

The cargo adapter stashes `payload["nextest_version"] = "0.9.137"`
at `cargo_adapter.py:299` per the lazy "payload-stash" convention.
The normalizer at `run/normalizer.py:72` hardcodes
`metadata={"native_exit_code": native_result.returncode}` and drops
every other payload key. Consequence: `nextest_version` (and any
future per-engine metadata stashed this way) is invisible to every
downstream consumer of `record.json` (`inspect`, `regression`,
`replay`, AI agents reading the persisted Run Record).

Two fix paths were on the table:

| | (a) Reserved-key convention | (b) Typed-slot amendment |
|---|---|---|
| Shape | normalizer merges `payload.get("metadata_for_record", {})` into `RunRecord.metadata` | new `NativeResult.metadata: dict[str, str]` field; normalizer copies through |
| Discoverability | implicit (magic key) | explicit (contract layer) |
| Adapter cost | per-adapter awareness of the magic key | per-adapter typed field assignment |
| AI-consumer friendliness | low (soft contract; may-or-may-not contain keys) | high (typed contract; IDE / introspection visible) |
| Future adapter inheritance | drift risk (next author may misremember the key) | inherited via contract — no drift |

## Decision

**Option (b): typed `metadata: dict[str, str]` slot on
`NativeResult`** (or its equivalent contract-layer type — the
implementing team picks the exact placement under the constraints
in §"What this decision does NOT decide").

Specifically the resulting slice MUST:

1. **Add `metadata: dict[str, str] = field(default_factory=dict)`
   to `NativeResult`** (or the equivalent contract-layer type that
   `_build_*_result()` helpers return). Placement constraints (PM):
   type-checked; normalizer-visible; frozen-dataclass-compatible if
   the existing type is frozen.

2. **Update `run/normalizer.py:72`** (or wherever metadata is
   constructed) to overlay adapter metadata onto the existing
   normalizer-controlled keys:

   ```python
   metadata = {"native_exit_code": native_result.returncode}
   metadata.update(native_result.metadata)
   ```

   **Order matters**: `native_exit_code` is the one normalizer-
   controlled key adapters MUST NOT override. The implementing
   slice adds a defensive guard (assert / pop-and-warn) for that
   invariant; future-proofing against adapter-author error.

3. **Migrate the cargo adapter** from payload-stash to typed slot.
   `cargo_adapter.py:299` moves `payload["nextest_version"]` →
   `result.metadata["nextest_version"]` (or equivalent). The
   `payload` dict stays for per-engine transient data that does
   NOT need to surface in `record.json`.

4. **Audit existing adapters (pytest / jest / gotest)** in the same
   slice as the cargo migration. If any of them stash a
   record-bound field in `payload[...]`, migrate to the typed slot.
   The cargo case was only caught because Manual Test grep'd for
   `nextest` while inspecting `record.json`; we do not rely on
   grep'd discovery for the other 3 adapters.

5. **Forbid new `payload[...]` stashes intended for `record.json`
   surface.** This is binding from the effective date below. Future
   adapters (JUnit, dotnet, Rust slow-mode paths) use the typed slot
   directly. Reviewers reject diffs that introduce new
   `payload["<engine>_version"]`-style assignments.

## Rationale

CEO + Manual Test + PM converged on (b) on three grounds:

### 1. Discoverability for AI consumers

A typed `metadata: dict[str, str]` field on the contract layer is
greppable (one symbol, not a magic key), type-checkable (mypy strict
catches misuse), and surfaces in IDE / `inspect`-style introspection.
AI agents reasoning about "what engine version produced this run"
can find the field at the contract layer — no normalizer-source
archaeology required. The reserved-key alternative would have
required AI consumers (and humans onboarding) to learn the magic
key by reading normalizer source or grep'ing for usages.

### 2. No magic-key drift across future adapters

A reserved key like `"metadata_for_record"` is a convention that
lives in adapter author memory. The next adapter author may
misremember the exact spelling (`"metadata"`? `"record_metadata"`?
`"_metadata"`?), notice no test failures (the normalizer silently
ignores unknown keys), and ship a silent data-drop bug analogous
to the one this decision is closing. Typed slots cannot drift.

### 3. The 2026-05-30 history file's load-bearing learning #2 names
the payload-stash pattern as anti-pattern

> "Convention by payload-stash is a soft contract that silently
> drops data. When a contract layer's 'rest of the dict gets
> silently dropped' surfaces, that is the contract layer asking to
> be strengthened. Resist the 'just add another conventional key'
> fix path."

Picking (a) would have perpetuated the exact pattern that learning
is asking us to retire. (b) is the structural fix the learning
points to.

### 4. Cost is small and one-time

Net source budget for the whole project:
- contract-layer field: ~1 line
- normalizer overlay + native_exit_code guard: ~3-5 lines
- cargo migration: ~1 line moved + payload key delete
- audit + migration for pytest / jest / gotest: ~5 lines total if
  needed (those adapters' current `payload` usage is small; audit
  may find nothing record-bound)
- tests for the new normalizer overlay: ~10 lines

Total ~25 lines net for the entire project. Future adapters (JUnit,
dotnet) inherit the channel for ~free.

## What this decision does NOT decide

- **Exact field placement**: `NativeResult.metadata` vs
  `NativeEngineContext.metadata` vs a new dedicated wrapper. PM
  defers to the implementing Memory/Run team. Constraints above
  (type-checked, normalizer-visible, frozen-compatible) bind the
  choice but multiple shapes satisfy them. The team picks whichever
  minimizes churn.
- **Schema versioning**: whether the typed slot bumps
  `record_schema_version`. Likely no — the slot is additive
  (existing `record.json` files stay valid; `metadata` field is
  already present in `record.json`, we just add more keys to it).
  Implementing team confirms.
- **Audit timing for existing adapters**: pytest / jest / gotest
  audit happens in the same slice as the cargo migration (the brief
  will direct this), OR — at the implementing team's request — a
  separate small follow-up slice. PM defers.
- **What happens to the `payload[...]` dict in general**: it stays
  as the per-engine catch-all for data that does NOT need to
  surface in `record.json`. Adapters can keep stashing transient
  internal state there.
- **MCP transport implications**: the typed slot will surface in
  the future MCP transport's tool responses identically to the
  CLI's `record.json` projection. No separate MCP decision needed.

## Affected files / teams

- **PM** — queues the follow-up typed-slot task brief AFTER the
  cargo nextest env-var hotfix
  (`tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`)
  merges. See §"Dispatch ordering" below.
- **Memory team** (likely owner — they own `src/novetest/models/`
  per their charter) — adds the typed field to whichever model is
  appropriate; ensures `record.json` serialization survives the
  schema-version question above.
- **Run team** — updates `run/normalizer.py` overlay + the
  `native_exit_code` reserved-key guard; migrates cargo adapter
  from `payload` to `metadata`; audits pytest / jest / gotest
  adapters in the same slice.
- **`agent-comms/decisions/2026-05-29-cargo-adapter-nextest-primary.md`**
  §"What this does NOT decide" item 5 is now **RESOLVED** by this
  decision. No edit to that file needed — the cross-reference here
  + the related: backref in this decision's frontmatter is enough
  for future PMs.

## Dispatch ordering (binding)

This decision creates a follow-up slice that **MUST land after**
the cargo nextest env-var hotfix
(`tasks/run-team-2026-05-30-cargo-nextest-env-var-hotfix.md`).

Reason: both slices touch `cargo_adapter.py`. The hotfix is
surgical (env-var addition only); the typed-slot slice migrates the
existing payload assignment at `:299`. Running parallel risks merge
conflicts in the same adapter file.

Concretely:
1. CEO dispatches Run hotfix (tomorrow).
2. Hotfix worktree → Main Branch merge → Manual Test sweep →
   findings → cycle close.
3. PM queues the typed-slot task brief at THAT cycle's close
   commit. The brief will inherit this decision verbatim and pick
   up the implementation work.
4. CEO dispatches typed-slot slice in the cycle that follows.

## Effective date

2026-05-30.

## Supersedes

No prior decision fully. Replaces:
- The implicit "payload-stash" convention used in the cargo adapter
  at commit `6d9f463` (which itself was implementing the deferred
  lazy-extension framing from the 2026-05-29 cargo-adapter-nextest-primary
  decision §"What this does NOT decide" item 5).
- The framing of "payload-stash vs amend `NativeEngineContext`" as
  an open question in that earlier decision.

The 2026-05-29 cargo-adapter-nextest-primary decision stays in force
for everything else it pinned (nextest-primary execution, no
nightly path, no plain-text fallback, libtest-json graduation watch);
only the deferred item 5 is now resolved.
