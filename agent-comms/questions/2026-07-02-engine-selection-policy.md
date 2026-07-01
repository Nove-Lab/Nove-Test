---
slug: engine-selection-policy
from: novetest-pm-team
to: CEO
type: question
status: pending
created: 2026-07-02
---

# Question — Engine selection policy (auto-detect at init + explicit user override)

CEO surfaced this as the #1 next product direction on 2026-07-02: the six native engines (pytest, jest, JUnit, go test, cargo, dotnet) today have no user-facing way to be chosen; selection is a fixed-priority auto-detect that fires on every `run` / `test` invocation. CEO wants (A) auto-detection **at init** that persists, and (B) at minimum an explicit user override. Neither exists today. CEO paused before deciding; this file is the resume point.

---

## 1. Current state — facts

| Axis | Today | Location |
|---|---|---|
| Selection algorithm | Marker-file scan → fixed priority, first match wins | `src/novetest/run/engine.py:34-79`, `run/engine_selector.py:74`, `run/readiness.py:164-224` |
| Priority (per user docs) | `pytest > jest > go-test > cargo-test > junit > xunit` | `design/user-doc/human/languages.md:44` |
| User override (CLI flag / env / config) | **None.** User docs verbatim: *"You do not pass an `--engine` flag."* | grep-confirmed 2026-07-02 |
| Does `init` persist a chosen engine? | **No.** `init` probes readiness for reporting only; never written to `.novetest/store.json`. Every `run`/`test` re-probes from scratch. | `orchestration/workflows/init.py:26-31`, `memory/project_store.py:75-81` |
| Polyglot root behavior | Silent priority-win. Workaround: one `.novetest/` per subdir. No warning. | `design/user-doc/human/languages.md:36-51` |
| Binding decision on selection policy | **None** in `agent-comms/decisions/`. `2026-05-25-supported-engine-matrix.md` only fixes the 6-engine matrix. |

## 2. Gap vs CEO's ask

| CEO wants | Gap |
|---|---|
| (A) auto-detect at init | `init` has no persistence slot for engine preference |
| (B) explicit user override | No `--engine` flag, no `NOVETEST_ENGINE`, no config field |

## 3. Decisions CEO owes (6 axes)

### Q1 — Where does the explicit override live?
- (a) CLI flag: `novetest test --engine pytest` (per-invocation)
- (b) Env var: `NOVETEST_ENGINE=pytest` (session-scoped)
- (c) Persisted config in `.novetest/store.json` (new field) (sticky)
- (d) All three, precedence `CLI > env > config > auto-detect`

### Q2 — What does "auto-detect at init" mean concretely?
- (α) `init` pins the detected engine to store; `run`/`test` uses pin, auto-detect is fallback
- (β) `init` recommends only, prompts user for confirmation before pinning
- (γ) `init` auto-pins only when unambiguous (single ecosystem); on multi-ecosystem, requires user to pick

### Q3 — Polyglot root behavior post-change?
- (i) Keep silent first-wins (max backward compat)
- (ii) Silent win + one-line stderr warning (parallels JUnit's `ambiguous-build-tool`)
- (iii) Error out when >1 candidates and no pin/flag → force explicit choice

### Q4 — Fix side finding §5.1 (two mismatched priority lists) in this slice or separately?
- Together: `engine_selector.py` and `readiness.py` both get touched anyway — atomic cleanup
- Separately: land a "single source of truth" priority-list slice first, then layer override on top

### Q5 — Fix side finding §5.2 (`foundations.md` decorator-registry stale claim) in this slice?
- (X) Retract the aspirational text in `foundations.md:318, 475` to reflect the shipped hard-coded ladder (minimal)
- (Y) Actually build the `@register` decorator registry now — makes 7th-engine addition trivial but expands scope significantly
- (Z) Defer to open queue; touch neither

### Q6 — Fold Open Q #18 (`delivery-phasing.md:305` — readiness caching in `.novetest/run/readiness/`) into this?
- The persistence slot for engine pin is a natural home for the cached readiness result too — solving both at once avoids two competing storage schemes.
- Alternative: keep #18 open, engine pin lives only in `store.json`.

## 4. Side findings surfaced during discovery (2026-07-02)

### 4.1 Priority lists disagree between two files (latent bug)
- `engine_selector._ECOSYSTEM_MARKERS` (`run/engine_selector.py:27-33`): python → js/ts → **java (3) → go (4) → rust (5)** → dotnet
- `readiness.assess_engine_readiness` (`run/readiness.py:164-224`): pytest → jest → **gotest (3) → cargo (4) → junit (5)** → xunit
- Failure scenario: workspace has both `pom.xml` and `go.mod`. Readiness probes and reports Go as ready. `execute()` then calls `select_native_engine()` which returns `java/junit` and dispatches `run_junit` — using a readiness verdict that was never taken about JUnit. User docs quote only the readiness ordering as "the" priority. No test, comment, or decision file acknowledges the mismatch.

### 4.2 `foundations.md` describes an unimplemented architecture
- `foundations.md:318, 475`: *"Native engine adapters via decorator-based registry behind a `NativeAdapter` Protocol"* / *"Each engine file decorates its class with `@register`; `run/engine.py` is engine-agnostic. Adding a seventh ecosystem is one PR, one file."*
- Actual: `run/engine.py:137-178` is a hard-coded 6-branch if-elif ladder. `@register` decorator does not exist.

## 5. Self-evident axes (no decision needed)

- Invalid `--engine <name>` value (outside 6-engine matrix) → immediate exit code + envelope error.
- Persistence slot lives in `.novetest/store.json` (new field), not a new file — keeps Memory team as single owner of the store layout. Memory team sign-off required.
- Implementing team composition: **Orchestration + Run + Memory** joint slice. Orchestration owns CLI flag + envelope wiring; Run owns selector logic + priority-list consolidation; Memory owns store schema extension. PM will file the brief once Q1–Q6 are decided.

## 6. Resume point (for next session — 2026-07-03 or later)

CEO paused 2026-07-02 saying "이 결정 과정 자체를 내일 하겠다" (defer the entire decision process to tomorrow). Recommended re-entry order:

1. **Q2 (α/β/γ) and Q3 (i/ii/iii) first** — they define the UX shape; the other 4 axes largely follow mechanically.
2. Q1 (CLI/env/config surface) → Q4 (bug-fix bundling) → Q5 (registry) → Q6 (readiness caching).
3. Once decided: PM drafts `agent-comms/decisions/2026-07-XX-engine-selection-policy.md` (binding), then the tri-team brief.

Code is unchanged. Nothing to unwind if CEO redirects.
