---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-07-04
slug: anchored-init-and-verb-resolution
related:
  - agent-comms/tasks/orchestration-team-2026-07-03-anchored-init-and-verb-resolution.md
  - agent-comms/decisions/2026-07-03-engine-selection-policy.md
  - agent-comms/questions/regression-team-2026-07-03-d5-cross-run-audit.md
---

# Handoff: Orchestration — anchored init, verb walk-up resolution, pin dispatch (Wave 2)

## Worktree

- **Path**: `/home/yjshin/dev/novetest-orchestration-anchored-init`
- **Branch**: `orchestration/anchored-init-and-verb-resolution`, commit `c6e51ae`, off main `7c6ece6`
- WORKLOG entry included in the commit (top entry, `2026-07-04 — anchored-pin-cycle / orchestration-team`).

## What landed (task scope §1–§5, all closed)

- **§1 D1+D4+D7 — `workflows/init.py` (rewritten)**: three-way outcome union.
  One viable engine → `create_project_store` + `set_pinned_engine`; envelope
  gains additive `data.pinned_engine`. No marker → NOTHING created, D4
  bounded discovery (`workflows/discovery.py`, NEW — depth ≤2, skip list,
  stop-at-project-root, no symlink descent, refusal at `/`/`$HOME`,
  POSIX-form candidate paths) → `no-engine-detected`. ≥2 READY (or ≥2
  markers with 0 READY) → NOTHING created → `engine-ambiguous`.
  `--engine <name>` on `init` validated against the six pairs
  (`invalid-flag`, exit 2, mirrors `--formula`); re-init `--engine` re-pins
  in place, run history retained (test-pinned).
- **§2 D2 — `orchestration/anchor_resolution.py` (NEW)**: ONE shared
  `resolve_workspace(cwd)` (wraps Memory's walk-up + D6 migration);
  `cli/app.py::_require_store` routes EVERY verb through it. The
  engine-choice rule lives once in `choose_workspace_engine` (shared by
  init, migration, and the workflow-level fallback — cannot diverge).
- **§2b D5 Finding C — `workflows/test.py::build_test_outcome_from_run_id`**:
  engine-blind prior selection replaced with the shared
  `resolve_baseline_for_run` + cache-only `get_regression_facts`; the stale
  "same logic status uses" comment fixed. (No orchestration unit tests
  stubbed `find_runs_for_target` in this module's namespace, so the
  seam-migration kick-back documented by Regression did not bite.)
- **§3 D3 — target semantics**: bare invocation → `target_expression = ""`
  at the anchor regardless of invoking subdir. Explicit targets normalized
  to anchor-relative canonical POSIX form (`normalize_target_expression`,
  built on the promoted workspace-relpath utility); engine-native patterns
  (go `./...`) and nonexistent paths pass through verbatim.
  `--engine` transient override on `test`/`run`: validated, forwarded to
  `execute(engine=...)`, never re-pins (test-pinned on-disk).
- **§4 D6 — migration**: pin-less store on any verb → detection at the
  anchor; one choice → silent backfill (e2e: strip pin from store.json →
  `status` restores it, envelope otherwise unchanged); ambiguous →
  `engine-ambiguous` instructing `init --engine`.
- **§5 — envelopes**: `init` + `status` gain additive `data.pinned_engine`;
  both new error codes carry `data.candidates` as
  `[{path, ecosystem, engine_name}]` (init's no-engine case also carries
  `data.scan_refused: bool`); shapes snapshot-pinned.
- **In-scope extras** (flagged, verify at merge):
  - `reset` re-inits at the wiped store's **anchor** (was: invocation cwd —
    latent store-relocation bug when reset from a subdir) and carries the
    previous pin across the wipe. For **legacy pin-less** stores the D1
    choice happens **BEFORE** the wipe: ambiguous/markerless anchors refuse
    with the store intact ("the store was NOT wiped" guidance). This was
    the code-review should-fix.
  - `design/interace-contract/orchestration.md` +
    `design/workflows/orchestration.md` updated (my owned docs) to match.

## Verification

- `env -u PYTHONPATH uv run mypy` (CI gate, strict) → **Success, 116 source files**
- Full `env -u PYTHONPATH uv run pytest -q tests/unit tests/integration` →
  **1491 passed / 13 skipped / 1 failed / 49 snapshots**. The 1 failure
  (`tests/integration/run/test_dotnet_warnings.py`) reproduces on unmodified
  main — dotnet SDK absent on this host, NOT this slice. 13 skips = known
  jest/Node host issue.
- New tests: 26 `tests/unit/orchestration/test_anchor_resolution.py`,
  11 `tests/unit/orchestration/workflows/test_init_anchoring.py`,
  16 `tests/unit/orchestration/workflows/test_discovery.py`,
  17 `tests/unit/cli/test_engine_flags.py`,
  6 `tests/integration/test_anchored_pin_e2e.py` (real subprocesses;
  dual-marker init → engine-ambiguous → `init --engine` → test from nested
  subdir via walk-up → bare vs explicit-target series separation, proven
  end-to-end via `inspect`'s regression baseline). All four D7 codes are
  observable in integration; `data.candidates` shapes are syrupy-pinned.
- Determinism note: the `engine-ambiguous` e2e leg fabricates `node`/`npx`
  PATH shims + `node_modules/.bin/jest` — jest readiness is
  PATH+filesystem-only (never executes node), so the dual-READY workspace is
  host-independent (works on hosts and CI runners with or without Node).
- code-reviewer subagent: **no blockers**; should-fix + 3 nits applied
  (reset pre-wipe choice; TOCTOU `EngineAmbiguousError` mapping in
  `run_cmd`/`test_cmd`; `::test_a` normalization guard; import order).
- Harness note: the karpathy-guidelines Skill could not be invoked (no
  Skill tool in this session's toolset — same as 2026-06-08/wave-1
  sessions); principles applied manually. This handoff file itself was
  written via the GOTCHAS.md-sanctioned Bash-heredoc fallback (Write
  blocked by the worktree-isolation handshake on the shared checkout) —
  no deliverable impact.

## Envelope-schema implications (for PM's Wave-3 doc pass)

Schema stays `novetest/v1` — all changes additive or new-error-code:

1. `init` success `data` += `pinned_engine: {ecosystem, engine_name}`
   (single-marker envelope otherwise byte-identical; keyset test pins it).
2. `status` `data` += `pinned_engine: {…} | null` (null only for a legacy
   pin-less store on a markerless anchor).
3. NEW error code `no-engine-detected` (init/reset; **exit 4**): `data` =
   `{candidates: [{path, ecosystem, engine_name}], scan_refused: bool}`;
   message instructs the agent to `cd` into a candidate and `init` there.
4. NEW error code `engine-ambiguous` (init/reset/any-verb-migration;
   **exit 2**): `data.candidates` same shape with `path: "."`.
5. `--engine` invalid values → existing `invalid-flag`, exit 2.
6. `reset` success envelope deliberately unchanged (no `pinned_engine`
   surfaced — kept byte-stable with its snapshot; follow-up candidate if PM
   wants parity with init/status).
7. Exit-code mapping is my read of the brief's "exit non-zero":
   `no-engine-detected` → 4 (engine-missing class), `engine-ambiguous` → 2
   (user action required). Flag for ratification before the doc pass.

## Notifications / follow-ups to route

- **Run team**: no `execute(engine=None)` caller remains in orchestration —
  their TODO (`run/engine.py` execute docstring) to drop the legacy
  auto-detect branch is now unblocked. Suggest folding into their next slice.
- **PM**: user-doc pass (task §Out of scope) — `design/user-doc/**` "You do
  not pass an `--engine` flag" claims are now false; behavioral change:
  `init` on a markerless directory now FAILS (used to create a store with
  engine-missing readiness) — one existing lifecycle test was updated
  accordingly and the change is decision-mandated (D1).
- **PM**: item 6/7 above (reset pin parity; exit-code ratification).

## DoD bullets believed closed (do NOT tick — PM territory)

- init pins with bounded discovery (D1+D4): no-marker and ambiguous paths
  create nothing; candidates reported; `--engine` accepted/validated;
  re-pin in place.
- Every verb resolves via ONE shared upward-walk helper (D2); no per-verb
  cwd assumptions remain (reset's cwd assumption removed).
- Bare/explicit target semantics with anchor-relative normalization (D3);
  transient `--engine` override without re-pin.
- Lazy migration (D6) incl. silent-backfill acceptance pin.
- All four D7 codes observable in integration with snapshot-pinned
  `data.candidates` shapes.
- `build_test_outcome_from_run_id` D5 swap (§2b).
- Full suite green (modulo the pre-existing dotnet host failure), mypy
  strict clean, single-marker init→test envelopes unchanged except the
  additive `data.pinned_engine`.
