---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-07-03
slug: engine-selection-policy
related:
  - agent-comms/questions/2026-07-02-engine-selection-policy.md
  - agent-comms/decisions/2026-05-25-supported-engine-matrix.md
  - src/novetest/run/engine_selector.py
  - src/novetest/run/readiness.py
  - src/novetest/regression/compare.py
---

# Decision: engine selection policy — the anchored-pin model

CEO-approved 2026-07-03 after a three-day decision arc (question filed
2026-07-02; user-scenario analysis, six-engine reference study, and two
rejected alternatives documented in §"Rejected alternatives"). Resolves the
open question `2026-07-02-engine-selection-policy` and Open Question #17
in `design/implementation-plan/delivery-phasing.md`.

## Governing principle

**novetest wraps engines; it never replaces or re-scopes them.** Each native
engine defines its own test-execution scope (pytest recurses from cwd, go
test is per-package, cargo/maven/gradle/dotnet run what their manifests
declare). novetest does NOT unify, extend, or re-interpret those scopes.
What novetest adds is an explicit, persisted **anchor**: a `.novetest/`
directory records *which* engine the user consented to at *which* location,
and every verb executes exactly that engine with its native scope. This is
the scope-dimension of the existing brand boundary "we wrap your engine,
never replace it" (`design/website-plan/handoff/site-requirements.md` S10).

## Decision

### D1 — `novetest init` anchors an engine (the pin)

| Situation at the init directory | Behavior |
|---|---|
| Exactly one ecosystem marker | Create `.novetest/`, record the engine **pin** in `store.json`. Unchanged onboarding: zero new flags for the common case. |
| No marker | **Create nothing.** Run a *bounded* downward discovery (see D4) and exit non-zero with error code `no-engine-detected`, listing discovered sub-project candidates (path + inferred engine) in `data`. The agent is instructed to `cd` into each candidate and run `init` there itself. novetest never creates `.novetest/` in a directory the user did not stand in. |
| Two or more markers | **Create nothing.** Exit non-zero with error code `engine-ambiguous` (distinct from `no-engine-detected`), listing the ready candidates and requiring an explicit choice: `novetest init --engine <name>`. |

`--engine <name>` is an **optional** parameter of `init` — required only in
the ambiguous case, accepted in all cases (explicit wins over detection).
Invalid values (outside the six-engine matrix per
`2026-05-25-supported-engine-matrix.md`) fail flag validation
(`invalid-flag`, exit 2).

Re-running `init --engine <other>` at an already-initialized location
**re-pins in place**: same store, pin field updated, run history retained.
A second `.novetest/` is never created for a second engine.

### D2 — every verb requires an anchor; resolution walks up, never down

All verbs resolve their workspace by walking **upward** from cwd to the
nearest `.novetest/` (git-style). Found → that store and its pin govern the
invocation. Not found by filesystem root → error `uninitialized` (existing
code). **No verb ever scans downward. No verb ever guesses an engine.**

Consequences:

- Running a verb from any subdirectory of an initialized workspace works
  (agents routinely invoke from `src/...`); the anchor is deterministic
  (nearest wins).
- Accidentally running `novetest test` at `/`, `$HOME`, or any uninitialized
  directory errors immediately with zero filesystem traversal beyond the
  upward walk (bounded by path depth).
- The runtime engine-ambiguity case is **structurally eliminated**: a store
  implies a pin, so run-time detection no longer exists (see D6 migration).

### D3 — execution: pin by default, explicit transient override allowed

- Default: the pinned engine runs, with its native scope, from the anchor
  directory. `target_expression` for Memory/Regression purposes is
  normalized **relative to the anchor** (the workspace-relpath utility
  promoted 2026-06-19 supplies the mechanics), so runs invoked from
  different subdirectories form distinct, correctly-separated baseline
  series.
- `novetest test --engine <name>` / `novetest run --engine <name>` execute a
  one-off override **without re-pinning**. The run record carries its
  `engine_name` as today; mixed-engine histories in one store are legitimate
  (e.g. Rust + PyO3 roots alternating cargo-test and pytest).

### D4 — discovery scan bounds (the only downward scan that exists)

The `no-engine-detected` candidate report in D1 is the sole downward
traversal in the product, and it is bounded:

1. Depth ≤ 2 below the init directory.
2. If cwd is inside a git repository, never traverse above or outside it.
3. Invoked directly at filesystem root or `$HOME` → refuse the scan
   outright (error without traversal).
4. Skip list: `node_modules/`, `target/`, `.venv/`, `venv/`, `.git/`,
   `dist/`, `build/`, `.novetest/`.
5. Stop descending once a project root is found (a Rust workspace member or
   JS workspace package is not reported as a separate candidate).

The report is a courtesy, not a gate — projects deeper than the bound are
simply not listed and remain fully initializable by running `init` there.

### D5 — cross-run analyses never cross an engine boundary

`compare_runs` already hard-refuses cross-engine pairs
(`REASON_ENGINE_MISMATCH`, `src/novetest/regression/compare.py:178`), so
fact corruption is impossible today. The residual defect is noise:
`resolve_latest_baseline` (`compare.py:600`) selects the two newest runs for
a target **without** engine filtering, so a mixed-engine series can yield
"unavailable" when a comparable same-engine baseline exists one step back.

Binding rule: **baseline/candidate selection for any cross-run analysis
(regression, coverage delta, SBFL aggregate/failure-proximity) filters by
the target run's `engine_name`.** `resolve_latest_baseline` gains the
filter; Coverage and Localization cross-run paths are audited against the
same rule during implementation.

### D6 — migration of pre-pin stores

Stores created before this decision have no pin field. On the first verb
against such a store: re-run detection at the anchor directory — one
unambiguous candidate → backfill the pin silently and proceed; ambiguous →
error `engine-ambiguous` instructing `novetest init --engine <name>`
(re-pin in place). One-time cost, no store rebuild.

### D7 — error-code surface (agents pin to these strings)

| Code | Introduced | Meaning |
|---|---|---|
| `no-engine-detected` | NEW | init at a markerless directory; `data` carries discovered sub-candidates |
| `engine-ambiguous` | NEW | ≥2 ready candidates and no explicit `--engine` (init D1, migration D6) |
| `uninitialized` | existing | verb invoked with no `.novetest/` on the upward walk |
| `invalid-flag` | existing | `--engine` value outside the six-engine matrix |

## Rejected alternatives (recorded so they are not re-litigated)

1. **Root fan-out** — plain `novetest test` at an engine-less root
   delegating to initialized sub-workspaces. Rejected by CEO 2026-07-03:
   it re-scopes engine behavior at the novetest layer, contradicting the
   governing principle, and unanchored discovery reintroduces the
   filesystem-scan hazard. A future `workspaces test` verb (backlog #10,
   v0.1.2 release notes) remains *compatible* with this decision as pure
   delegation over explicitly initialized sub-workspaces, but is not
   planned. Agents achieve "run everything" today by iterating `cd` +
   `novetest test` per workspace.
2. **Mandatory `--engine` at every init** — rejected: taxes the ~90%
   single-marker case with a decision that has exactly one answer, breaking
   the one-line `install → init → test` onboarding narrative.
3. **Per-engine `.novetest` directories** — rejected: store identity is
   per-workspace, not per-engine; two stores at one path would fragment run
   history and make verb resolution ambiguous.
4. **Silent priority-win at ambiguous roots (status quo)** — rejected: an
   agent believing "all tests pass" while an entire suite silently never
   ran poisons the agent's world model; the asymmetry (one recoverable
   error turn vs. unbounded silent wrongness) decides it.

Reference study backing D2/D4 (six-engine invocation-scope comparison —
pytest cwd-recursive; jest rootDir-anchored; go per-package with `./...`
bounded by go.mod; cargo manifest walk-up with declared workspace members;
Maven/Gradle declared modules; dotnet sln/csproj-anchored): all six anchor
to a declared manifest and none discover projects by filesystem scanning;
recursion where present is bounded by a declared boundary. The anchored-pin
model transplants exactly that pattern.

## What this decision retires or affects

- **Resolves Open Q #17** (`delivery-phasing.md`): Project Store discovery =
  walk up to nearest `.novetest/`, stop at filesystem root. No nested-store
  semantics beyond nearest-wins.
- **Open Q #18** (readiness probe caching): urgency drops — pins remove
  per-invocation engine *detection*; probe-result caching remains open and
  independent.
- **Kills the two-priority-lists latent bug by design**: detection now
  happens only inside `init` (single site); run-time reads the pin. The
  `engine_selector.py` / `readiness.py` order mismatch (documented in the
  2026-07-02 question §4.1) loses every code path by which it could
  misfire; the lists are consolidated to one source of truth during
  implementation.
- The `foundations.md` decorator-registry stale claim (question §4.2) is
  **out of scope** here — tracked separately.

## Affected teams

- **Orchestration** — `init` workflow (D1, D4), CLI `--engine` flags +
  error codes (D7), verb-level anchor resolution wiring (D2).
- **Memory** — `store.json` pin field (schema), walk-up store discovery
  (D2), migration backfill (D6).
- **Run** — pin-driven engine dispatch replacing run-time detection,
  priority-list consolidation, readiness reporting against the pin.
- **Regression** — engine-scoped `resolve_latest_baseline` (D5).
- **Coverage / Localization** — D5 audit of cross-run paths.

PM will slice and sequence the implementation briefs separately; this
decision fixes the policy, not the delivery plan.

## Effective date

2026-07-03.

## Supersedes

None. Complements `2026-05-25-supported-engine-matrix.md` (the six-pair
matrix is unchanged). First binding decision on engine *selection*.
