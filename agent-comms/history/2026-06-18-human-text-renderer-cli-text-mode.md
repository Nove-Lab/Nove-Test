---
from: novetest-pm-team
to: all
type: history
created: 2026-06-18
slug: human-text-renderer-cli-text-mode
cycle_window: 2026-06-18 (single-day, ran parallel with windows-install-ps1-and-binary-pipeline)
related:
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #9 closed
---

# Human-readable TEXT renderer for `novetest` CLI

## TL;DR

`OutputMode.TEXT` is now a true human surface, not pretty JSON. Typing `novetest test` in a terminal gives a scannable summary (`✓ passed · 3/3 · run_id=...`) instead of a 50+-line JSON dump. AI agents that pin `novetest/v1` JSON / NDJSON envelopes are completely unaffected — byte-identity guard verified via zero `.ambr` snapshot drift on pre-existing tests.

**Closes Future-cycle queue item #9.**

Manual Test verdict: **PASSED** — 6 scenarios + 6 edge cases, zero blocking defects. Three minor nits are all documentation/contract clarifications, not product regressions.

## Cycle arc (single day, ran in parallel with #4 Windows pipeline)

| Event | Commit |
|---|---|
| PM dispatch prep — task brief filed | `dbd741b` |
| Orchestration code-slice merged | `397fe00` |
| Comms (handoff + INDEX) | `c76dbbb` |
| Main Branch verification routing | `2556558` |
| Manual Test PASSED findings filed | `<untracked at cycle close>` |
| PM cycle-close (this entry + foundations + dphasing edits + transient cleanup) | `<this commit>` |

## What landed

### Source changes

| File | Change |
|---|---|
| `src/novetest/cli/renderers/` (new package) | 16 files: `__init__.py` (public `render_text` export), `registry.py` (verb→fn dispatch + `render_text`/`render_error`/`render_warnings`/`render_fallback`), `_format.py` (glyph constants + primitives), `_outcomes.py` (kind-discriminated engine-outcome formatters), plus 12 noun-grouped verb renderers (`onboarding`, `init`, `run`, `test`, `status`, `inspect`, `compare`, `replay`, `memory`, `coverage`, `regression`, `localization`). |
| `src/novetest/cli/output.py::emit_envelope` | One `if mode == OutputMode.TEXT:` branch added; deferred import of `render_text` (keeps dependency direction `renderers → output`). JSON / NDJSON branches **byte-identical** to pre-slice. |
| `tests/unit/cli/renderers/` (new) | 14 test modules + 13 `.ambr` snapshot files → 35 syrupy snapshots → 46 unit tests. |
| `tests/integration/cli/test_text_mode_end_to_end.py` (new) | 6 subprocess e2e tests covering `test`/`run`/`localization`/`help` in TEXT mode + JSON/NDJSON contrast + env override. |

Total touch: ~3-4k LOC including 13 .ambr snapshot files. Zero changes to `cli/app.py`, `cli/handlers/`, `orchestration/`, any engine layer, any decision file, `foundations.md`, or `pyproject.toml::dependencies`.

### Test count delta

- Pre-slice baseline: 1226 passed / 26 skipped / 1 failed
- Post-slice on Manual Test's host: 1281 passed / 23 skipped / 1 failed
- Net: +52 new passes (46 unit renderer + 6 integration e2e) — exact match to handoff DoD #4 claim
- The 1 failure is the pre-existing chronic `dotnet` host-equip gap (unchanged)

## Load-bearing learnings (4)

### 1. Noun-grouped renderer layout > 1-file-per-token

**Surface**: The PM brief's DoD #1 literally read "one renderer module per verb token in `_RENDERERS`" (18 tokens). The Orchestration team implemented **12 noun-grouped modules** instead, co-locating per-noun helpers (e.g., `memory.py` houses `render_memory_list/show/delete`; `coverage.py` houses `render_coverage_show/diff`). The Note A in the handoff surfaced this as a PM judgment call.

**Why noun-grouped wins**: The kind-discriminated outcome blocks (CoverageFactSet vs CoverageUnavailable; RegressionFactSet vs RegressionUnavailable; LocalizationFinding vs LocalizationUnavailable; ReplayResult vs ReplayUnavailable) recur across 3+ verbs each. A 1-file-per-token layout would force the shared formatter into a helper module while each per-verb file becomes a 5-line stub calling the helper — pure ceremony with no architectural benefit. The noun-grouped layout keeps the helper next to the verbs that use it.

**Manual Test recommendation**: accept noun-grouped as canonical (Karpathy "Simplicity First" — every verb is still independently snapshot-tested via `_RENDERERS` map). PM concurs.

**Future PM briefs**: when prescribing module granularity, prefer the looser shape "every verb token in `_RENDERERS` maps to a callable" over the rigid shape "one module per token." Lets the team find the natural co-location boundary.

### 2. JSON / NDJSON byte-identity discipline via `.ambr` snapshot pinning

**Surface**: DoD #7 required "JSON / NDJSON snapshots unchanged (zero syrupy updates)." The Orchestration team verified empirically via `git diff` on `tests/**/__snapshots__/*.ambr` post-slice — only NEW `.ambr` files under `tests/unit/cli/renderers/__snapshots__/` (13 new files); zero modifications to pre-existing snapshot files anywhere in the tree.

**Why this matters**: The AI-agent contract is the JSON envelope shape — Cursor, Claude Code, Cline, and future MCP-via-`novetest-mcp` consumers parse against `schema: novetest/v1`. A single byte drift in JSON / NDJSON output breaks the contract silently. Snapshot pinning is the load-bearing verification surface for "additive UX change, frozen wire shape."

**Pattern for future cycles**: any slice that adds a new output mode, a new rendering layer, or anything that changes how the envelope reaches stdout MUST include the byte-identity guard:

```sh
git diff <base-sha>..<head> --name-only -- 'tests/**/__snapshots__/*.ambr' | grep -v '<new-subdir>/'
# should output nothing
```

The slice that adds NDJSON streaming (per `foundations.md §"NDJSON stream"`) will face the same discipline. Pinned.

### 3. The 7-glyph palette for future renderer extensions

**Surface**: Manual Test enumerated 7 glyphs in the active renderer output (the PM brief expected 5):

| Glyph | Semantic |
|---|---|
| `✓` | passed / clean / reproducible / availability OK |
| `✗` | failed / regressed / error envelope header |
| `—` (em-dash) | unavailable (generic) |
| `⚠` | warning (per `render_warnings`) |
| `·` (middle-dot) | inline separator (`passed · 3/3 · run_id=...`) |
| `↳` | sub-reference arrow (e.g., recommendation citation) |
| `?` | replay-specific unavailable variant (distinguishes replay gating from generic `—`) |

**Why pinned**: future renderer extensions (NDJSON pretty-stream, color polish, additional verbs) should reuse this palette rather than introduce new symbols. The 7 glyphs render cleanly in UTF-8 on Linux/macOS terminals and Windows Terminal; cmd.exe legacy renders `?` boxes (acceptable — modern Windows users get correct rendering).

**Canonical surface**: `src/novetest/cli/renderers/_format.py` constants. Future renderers add to that file; the PM brief / verification doc enumerates from there.

### 4. `resolve_output_mode` precedence is `explicit > env > TTY-auto` (canonical Unix) — PM verification template correction

**Surface**: The verification doc for this cycle asserted (Scenario C #3 + Edge case #1) that `NOVETEST_OUTPUT=json` overrides `--output text`. Empirically wrong: `src/novetest/cli/output.py::resolve_output_mode` lines 66-79 check `explicit is not None` FIRST and return immediately on hit. The existing test `test_env_var_json_override_wins_over_text_default` only pins env beats TTY *default*, not env beats explicit.

**Why the actual precedence is correct**: explicit flag > env > TTY-auto is the canonical Unix tool convention. AI agents that want deterministic JSON should pass `--output json` (overrides anything) or rely on the non-TTY pipe default (overrides nothing). Env override is the shell-config fallback. The implementation IS the better contract.

**PM action**: future `agent-comms/verifications/` templates for this CLI surface MUST scope env-override claims to "wins over TTY default" — not "wins over explicit flag." Pinned for the next verification routing.

## Manual Test nits (all doc-side, no product action)

1. **Verification doc env-override claim** — covered by learning #4 above.
2. **Glyph enumeration gap** — verification doc listed 5 glyphs; reality is 7 (covered by learning #3).
3. **Unavailable-reason token style inconsistency** — `(no_failed_tests)` (underscore) vs `(missing-derived-facts)` (hyphen) for what are conceptually same-class "unavailable" markers. The hyphen convention matches the wider envelope `code` field style (`"not-found"`, `"engine-missing"`). The renderer faithfully reproduces what the engines emit — the inconsistency is upstream in the engine outcome data, not the renderer.

**Disposition of nit #3**: low-priority engine hygiene cycle for future. Localization engine emits underscore separator (`no_failed_tests`); other engines emit hyphen. Normalize to hyphen in a future Coverage/Localization/Replay-team cleanup. NOT auto-queued — surface only if a user complains about envelope inconsistency.

## Phase 0 DoD bullets re-validated (no new ticks)

This cycle adds zero new Phase 0 DoD ticks (all already `[x]` from prior cycles). The renderer slice is a Future-cycle queue item, not a Phase 0 binding. Empirically re-validated:
- `ci.yml` GREEN on every commit (`397fe00`, `c76dbbb`, `2556558`, `9b365ff`)
- mypy `--strict` GREEN (109 source files; baseline 93 + 16 new renderer modules)
- pytest 1278+ passed / 23-26 skipped / 1 failed (chronic dotnet host-equip — unchanged)

## Cycle transcript (commits)

- `dbd741b` — PM: prepare parallel cycles (this cycle + #4 Windows)
- `397fe00` — Orchestration: human-readable TEXT renderer for the novetest CLI
- `c76dbbb` — Orchestration: handoff + INDEX
- `2556558` — Main Branch: verification routing to Manual Test
- `<this commit>` — PM: cycle-close (this entry + foundations.md + delivery-phasing.md edits + transient cleanup + INDEX regen)

## Closure

The human-readable TEXT mode is shippable as-is. The CLI's design intent (`foundations.md §6.2`: "humans get pretty output by default") is now operationally true — typing `novetest test` in a terminal gives a scannable summary, and AI agents continue receiving structured JSON envelopes verbatim via `--output json`, `NOVETEST_OUTPUT=json`, or the non-TTY pipe auto-detection.

**Future-cycle queue #9 is operationally closed.**

The next cycle's `2026-06-18-windows-install-ps1-and-binary-pipeline.md` history closes #4 + Open Q #16 at the same time. After both, the Future-cycle queue inherits 7 items: #2 (`novetest --licenses` CLI surface) + #3 (v1 metadata-channel sunset) + #5 (first-run latency bench) + #6 (`workspace_relpath` utility) + #7 (CI matrix verdict meta-decision) + #8 (Wheel-NOTICES probe codification, optional) + #10 (`novetest workspaces test` polyglot orchestrator, optional). Sequenced per CEO direction.
