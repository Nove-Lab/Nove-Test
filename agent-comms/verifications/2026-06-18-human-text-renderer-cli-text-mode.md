---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-18
slug: human-text-renderer-cli-text-mode
related:
  - agent-comms/handoffs/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md
  - agent-comms/tasks/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md
---

# Verification — human-readable TEXT renderer for novetest CLI (Future-cycle queue #9)

## Merge summary

Orchestration slice FF-merged into `main` as the **first** of two parallel
cycles (alphabetic merge order per Main Branch charter; zero file-footprint
overlap with the parallel Release / Windows slice).

| Slice | Original SHA | Post-merge SHA | Subject |
|---|---|---|---|
| Code  | `397fe00` | `397fe00` (FF, unchanged) | `cli: human-readable TEXT renderer for the novetest CLI` |
| Comms | `c76dbbb` | `c76dbbb` (FF, unchanged) | `comms: orchestration handoff + INDEX for human-text-renderer cli-text-mode` |

- **Source handoff**: [orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md](../handoffs/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md)
- **Merge mode**: FF-only against `dbd741b` (no conflicts; base was current `main` HEAD)
- **Local main HEAD after this slice**: `c76dbbb`
- **⚠ Push status (CEO action required)**: `git push origin main` **BLOCKED** by HTTP 403 — the `gh` token in this session (`yongjunshin`) has `viewerPermission: READ` on `Nove-Lab/Nove-Test`, same auth state Release team encountered in their handoff §"Risks" #1. Local merge + gate are complete; push to origin awaits CEO action under a write-capable account.

## Post-merge gate (run after BOTH slices merged — see also Release verification)

| Check | Result |
|---|---|
| `uv run mypy --strict src/novetest` | **PASS** — 109 source files, 0 issues (baseline 93 + 16 new renderer modules) |
| `uv run pytest -q tests/unit tests/integration` | **1281 passed + 23 skipped + 1 failed** (39.09s) |
| Test count delta vs prior baseline | **+52 net new** (46 unit renderer tests + 6 integration text-mode e2e tests) = exact match to handoff §"Verification" |
| Pre-existing failure | `tests/integration/run/test_dotnet_warnings.py::test_xunit_v3_deferral_emits_envelope_warning_via_adapter` (`dotnet` not on PATH; chronic dev-host-equip dependency, **unchanged by this slice**) |
| JSON/NDJSON byte-identity (regression guard) | snapshots unchanged; **zero `.ambr` drift** confirmed by orchestration team's verification surface |

## Files landed (orchestration slice)

### NEW package `src/novetest/cli/renderers/` — 16 modules (verified on merged HEAD)

```
src/novetest/cli/renderers/
├── __init__.py              # public surface: `render_text(envelope) -> str`
├── registry.py              # 4 public render_* fns (render_text/_error/_warnings/_fallback) + _RENDERERS verb→fn dispatch
├── _format.py               # glyphs ✓✗—⚠ + run_status_glyph/availability_glyph/format_timestamp/percent/target_label/format_table/indent_block
├── _outcomes.py             # kind-discriminated coverage/regression/localization/replay block formatters
├── onboarding.py            # render_version, render_help
├── init.py                  # render_init
├── run.py                   # render_run
├── test.py                  # render_test
├── status.py                # render_status
├── inspect.py               # render_inspect
├── compare.py               # render_compare
├── replay.py                # render_replay
├── memory.py                # render_memory_list / _show / _delete
├── coverage.py              # render_coverage_show / _diff
├── regression.py            # render_regression_compare / _latest
└── localization.py          # render_localization / _latest
```

### MODIFIED (one existing source file — verified by `git diff`)

- `src/novetest/cli/output.py::emit_envelope` — added `if mode == OutputMode.TEXT:` branch (deferred import of `render_text` to enforce one-way dep `renderers → output`). JSON / NDJSON branches **byte-identical** to pre-slice.

### Tests (new)

- `tests/unit/cli/renderers/` — 14 test modules + `conftest.py` + `__snapshots__/` (35 syrupy snapshots) = **46 unit tests**
- `tests/integration/cli/test_text_mode_end_to_end.py` — **6 subprocess e2e tests**

## Verification scenarios for Manual Test

### Scenario A — `--version --output {json,text}` shape pin (verbatim on merged HEAD)

```sh
git checkout main && git pull --ff-only       # AFTER CEO push
uv run novetest --version --output json
```

Pinned output (verbatim, captured directly on merged HEAD `c76dbbb`):

```json
{
  "command": "version",
  "data": {
    "commandName": "novetest",
    "installLocation": "/home/yjshin/dev/aispace/Nove-Test/.venv/bin/python3",
    "installedVersion": "0.1.1",
    "platform": "linux-x86_64",
    "pythonVersion": "3.11.15",
    "verifiedAt": "2026-06-18T07:06:16.921044Z"
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

- `data.installedVersion == "0.1.1"` — **importlib.metadata path is live** (per the 2026-06-10 version-importlib-metadata migration; the prior chronic `"0.0.0"` stub is closed). The wheel-internal version now matches `pyproject.toml::version`.

Text-mode for the same command:

```sh
uv run novetest --version --output text
```

```
novetest 0.1.1 (Python 3.11.15, linux-x86_64)
```

Manual Test confirms:
- `--output text` is NOT pretty-JSON (`assert not stdout.lstrip().startswith("{")`)
- Single-line, scannable, contains version + python + platform
- `verifiedAt` timestamp is omitted from text mode (it's CLI-noise for humans)

### Scenario B — `--help --output text` is scannable, NOT pretty-JSON

```sh
uv run novetest --help --output text | head -20
```

Pinned (verbatim head, from merged HEAD):

```
novetest — AI-first testing orchestration

Onboarding:
  novetest --version           Print CLI identity envelope.
  novetest --help              Print command surface envelope.
  novetest init                Initialize a Project Store under .novetest/ in the current workspace.

Operating:
  novetest test                Run tests with integrated orchestration and synthesize a recommendation.
  novetest run                 Execute a Test Target via the native engine and persist a Run Record.
  ...
```

Manual Test confirms: categorized section headers (`Onboarding:` / `Operating:` / …), 2-space indent, command-then-description columnar layout.

### Scenario C — JSON / NDJSON byte-identity regression guard

Critical contract: AI-agent consumers (the primary product audience) see
JSON/NDJSON envelopes verbatim — **zero byte drift** vs pre-slice:

```sh
# JSON mode — should be the canonical envelope shape, no text mixed in:
uv run novetest --help --output json | jq -r '.command, .schema, (.errors | length), .ok'
# expect: help  novetest/v1  0  true

# NDJSON mode — newline-delimited JSON envelopes:
uv run novetest --help --output ndjson | head -1 | jq -r '.command, .schema'
# expect: help  novetest/v1

# Env override (NOVETEST_OUTPUT=json wins over --output text):
NOVETEST_OUTPUT=json uv run novetest --help --output text | jq -r '.command, .schema'
# expect: help  novetest/v1   (NOT human text)
```

If any of these print human text instead of JSON, the env-override or
JSON-routing in `emit_envelope` has regressed. Escalate via
`agent-comms/findings/`.

### Scenario D — Empirical user smoke set (per handoff §"Empirical user smoke")

Manual Test runs through the smoke set on a real workspace with at least one
green run and one failing run already persisted. Each command should produce
human-readable scannable text per handoff §"Empirical user smoke" snippet:

```sh
# In a workspace with prior runs:
uv run novetest test --output text                      # rec block: ✓ all_green | ! investigate_location | — unavailable
uv run novetest run --output text                       # ✗ failed · 3/4 · run_id=...
uv run novetest memory list --output text               # 4 runs / table form
uv run novetest inspect <run_id> --output text          # per-sub-report availability summary
uv run novetest coverage show <run_id> --output text    # ✓ per-test · 10/11 statements (86.7%)
uv run novetest localization <run_id> --output text     # sbfl_per_test · ochiai · 6 entries
uv run novetest replay <run_id> --reruns 1 --output text # ✓ reproducible · 1/1
uv run novetest status --output text                    # ✗ status / uninitialized banner
```

Glyphs to verify: `✓ ✗ — ⚠ !` rendering correctly in the host terminal; no
ANSI color codes injected (per handoff: "no color/no new dep" Karpathy
posture).

### Scenario E — Renderer module surface audit (Note A: DoD #1 module granularity)

The handoff §"Note A — module granularity" pre-flagged a PM judgment call:
**DoD #1 literally reads "one renderer module per verb token in `_RENDERERS`"
(18 tokens), but the implementation lands 12 noun-grouped modules** (mirroring
`cli/app.py`'s `memory_app` / `coverage_app` / `regression_app` /
`localization_app` sub-app shape). Every token still has a dedicated render
function + dedicated snapshot test. Audit:

```sh
ls src/novetest/cli/renderers/ | grep -E '\.py$' | sort
# expect: 16 files (incl. __init__.py, registry.py, _format.py, _outcomes.py + 12 noun-grouped modules)

# Confirm every _RENDERERS verb token has a dedicated render function:
uv run python -c "
from novetest.cli.renderers.registry import _RENDERERS
print(f'tokens: {len(_RENDERERS)}'); print(*sorted(_RENDERERS.keys()), sep='\n')
"
# expect: tokens: 18 (all 18 verb tokens enumerated)
```

PM judges whether (a) the noun-grouped layout is the new canonical (Karpathy
"Simplicity First" applied: co-located per-noun helpers like the
kind-discriminated outcome blocks recur across 3+ verbs each), or
(b) request a mechanical 1-file-per-token split (no logic change). Manual
Test surfaces the audit data; PM decides.

### Scenario F — Snapshot stability (zero `.ambr` drift in EXISTING tests)

```sh
git diff main HEAD -- 'tests/**/__snapshots__/*.ambr' | head -5
# expect: empty (no diff against pre-slice — only NEW snapshots under tests/unit/cli/renderers/__snapshots__/)
```

The pre-slice JSON/NDJSON snapshots (`tests/unit/cli/test_output_envelope.py`,
`test_help_envelope_no_store.py`, etc.) must NOT have been updated by this
slice — DoD #7 explicit.

## Critical edge cases worth probing

1. **`NOVETEST_OUTPUT=json` env override** wins over `--output text`. Confirm via Scenario C's third command. AI agents rely on this to force JSON regardless of user shell config.
2. **TTY auto-detection** (per the broader output-mode policy). When stdout is a TTY and no `--output` flag passed, mode defaults to TEXT; when piped/redirected, defaults to JSON. Re-validate by `uv run novetest --version > /tmp/out` then inspecting `/tmp/out`.
3. **Empty / unavailable sub-reports** in `inspect` / `status` / `compare`. Renderers must produce the `— unavailable (<reason>)` line (em-dash + `—` glyph), not a Python traceback or empty string.
4. **Empty `warnings[]` vs non-empty**. When non-empty, renderer must emit a `⚠ warnings:` block per `render_warnings` (see `registry.py`); confirm visually with a known-warnings-bearing envelope.
5. **Error envelopes** (`ok: false`). Renderer must emit `render_error` block per `registry.py`; the exit-code routing in `cli/app.py` is independent (charter: renderer is pure presentation, exit code is `output.py` territory).
6. **18-token coverage**. Per Scenario E, every `_RENDERERS` key must map to a callable; missing keys cause `render_fallback` to fire — confirm no silent fallback for valid envelopes.

## Notes for PM (per handoff DoD ledger)

- **DoD #1 literal-vs-noun-grouped layout** ← Manual Test surfaces the audit data via Scenario E; PM judges whether to (a) accept noun-grouped as canonical (recommended per Karpathy Simplicity First) or (b) request a mechanical 1-file-per-token split. No logic change either way.
- **DoD #4 syrupy snapshot pinning** ← 35 snapshots in `tests/unit/cli/renderers/__snapshots__/` (per handoff). Manual Test confirms presence; coverage of every verb's ok / error / warnings / unavailable cases.
- **DoD #11 zero changes outside renderer scope** ← `git diff main..c76dbbb -- src/ ':!src/novetest/cli/renderers/' ':!src/novetest/cli/output.py'` should be empty (no `cli/app.py`, no `cli/handlers/`, no `orchestration/`, no engines, no `pyproject.toml::dependencies`).
- **Future-cycle queue #9** ← marked closed by this slice (queue is in `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md` Future-cycle section). PM updates the queue at cycle close.

## Cleanup

- Orchestration worktree `/home/yjshin/dev/aispace/Nove-Test-wt-textrenderer` — **removed** ✓
- Orchestration branch `orchestration/human-text-renderer` — **deleted** ✓
- Local main HEAD: `c76dbbb` (after this slice), `6b33383` (after the parallel Release slice merged on top)
- **`origin/main` push BLOCKED**: HTTP 403, READ-only token. CEO push required to land `dbd741b..6b33383` on origin (10 commits cumulative from prior unpushed PM prep + both merged slices + verification commits).

## CEO push procedure (READ-only auth blocker)

```bash
cd /home/yjshin/dev/aispace/Nove-Test
git log --oneline origin/main..HEAD       # confirms ~10 commits pending
git push origin main                       # requires write token on Nove-Lab/Nove-Test
```

Once `origin/main` is updated, the standard `ci.yml` matrix fires on the push
and Manual Test scenarios become runnable against the public state.
