---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-18
slug: human-text-renderer-cli-text-mode
related:
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md  # Future-cycle queue #9
  - agent-comms/decisions/2026-06-06-adapter-warning-surface-v1-metadata-channel.md  # envelope wire shape (frozen)
  - design/implementation-plan/foundations.md  # §6.2 "Mode selection" (design intent)
---

# Task: Human-readable TEXT renderer for `novetest` CLI

## Mission

Replace the current `OutputMode.TEXT` behavior — which emits pretty-printed JSON via `json.dumps(..., indent=2, sort_keys=True)` — with a true **human-readable text renderer** under `src/novetest/cli/renderers/` (new package). When a user types `novetest test` in a terminal, the output must be a scannable summary of the result, not a wall of JSON.

This closes Future-cycle queue item **#9** (Human-readable text renderer) from `agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md`.

**Critical contract preservation**: `OutputMode.JSON` and `OutputMode.NDJSON` envelope shapes are FROZEN. AI agents (Cursor, Claude Code, Cline, future MCP) pin against the `novetest/v1` schema; this slice cannot perturb a single byte of JSON / NDJSON output. The change is **purely additive at the TEXT branch** of `cli/output.py::emit_envelope`.

## Strategic context

`design/implementation-plan/foundations.md §6.2` ("Mode selection") states:

> Default is `text` on a TTY, `json` otherwise (`not sys.stdout.isatty()`). Override via `NOVETEST_OUTPUT=json` env var. **AI agents will set this; humans get pretty output by default.**

The CLI's mode resolution (`cli/output.py::resolve_output_mode`) already implements this correctly — TEXT on TTY, JSON on pipe, env override available. **The bug is that TEXT mode itself is just pretty JSON, not a human surface.** So `novetest test` typed in a terminal gives the user a 50+ line indented JSON dump. This slice fixes that.

Since the mode resolution is already humans-default, this slice does NOT flip any default. No backward-compat concern for AI agents — they either set `NOVETEST_OUTPUT=json` explicitly, or run via subprocess (non-TTY → auto-JSON). Either way the JSON wire contract is untouched.

## Scope (file footprint)

### New files

- **`src/novetest/cli/renderers/__init__.py`** — public API surface: `render_text(envelope: Envelope) -> str`.
- **`src/novetest/cli/renderers/registry.py`** — verb → renderer dispatch. Single source of truth for which verb maps to which renderer function.
- **`src/novetest/cli/renderers/_format.py`** — shared formatting primitives: status glyphs (✓/✗/—), key-value column layout, indent helpers. **NO ANSI color in this slice** (color is post-MVP polish; see §"Out of scope"). Hand-rolled, no new runtime dep.
- **`src/novetest/cli/renderers/<verb>.py`** per verb that has a meaningful human surface (see §"Verb coverage" below).
- **`tests/unit/cli/renderers/test_<verb>.py`** per renderer module. Assert the exact text output against deterministic fixtures.
- **`tests/integration/cli/test_text_mode_end_to_end.py`** — subprocess invocations of `novetest <verb> --output text` against fixture projects, asserting the rendered text shape end-to-end (mirrors the existing JSON-mode integration tests).

### Modified files

- **`src/novetest/cli/output.py`** — modify `emit_envelope` so the `OutputMode.TEXT` branch calls `render_text(envelope)` (from the new `renderers` package) instead of `json.dumps`. JSON / NDJSON branches unchanged byte-for-byte.

### Touch budget

- Source delta: ~10-20 small renderer modules (one per verb), each <80 LOC. Plus the registry + format helpers. Plus the 1-line `emit_envelope` switch.
- Test delta: ~20-30 unit tests + ~5-10 integration tests.
- Total ~600-1000 LOC including tests. Single-cycle.

## Verb coverage (current CLI surface, audited 2026-06-18 against `src/novetest/cli/app.py`)

All 16 implemented verbs MUST have a human renderer. The renderer surface for stubs (`not_implemented_envelope`) is also required because the user might type any of them.

### Onboarding (special — argv-pre-Cyclopts)

| Verb | Renderer hint |
|---|---|
| `novetest -v` / `--version` | One line: `novetest <version> (Python <pyver>, <platform>)` |
| `novetest -h` / `--help` / bare `novetest` | List of verbs grouped by section (Onboarding / Operating / Stubs); short one-line per verb |

### Operating verbs (with successful outcomes)

| Verb | Renderer hint |
|---|---|
| `init` | `Initialized .novetest/ at <path> (engine readiness: <state> — <ecosystem>/<engine>)` |
| `test [target]` | Summary line: `<N> recommendations · <K> categories · run_id=<id>`. Per-recommendation: glyph + category + headline + first citation. **This is the most user-facing verb — invest the most rendering care here.** |
| `run [target] [--coverage]` | Summary: `<status> · <passed>/<total> · run_id=<id> [· coverage: <mapping_granularity>]`. Failed test list if any. |
| `status` | Latest run summary + sub-report availability table (4 columns × 4 rows: coverage / regression / localization / replay × availability). |
| `inspect <run_id>` | Composite — run summary + each sub-section (coverage, regression, localization) with one-line each; if section is `unavailable`, just say so. |
| `compare <baseline> <target>` | Composite: regression headline + coverage delta summary. |
| `replay <run_id> [--reruns N]` | Classification glyph + count: `✓ reproducible · 3/3` / `✗ inconsistent · 2/5 failed` / `? unable_to_replay · <reason>`. |

### Sub-app verbs

| Verb | Renderer hint |
|---|---|
| `memory list` | Table: run_id / target / status / created_at, one row per entry. |
| `memory show <run_id>` | Key-value block: run_id, target, status, duration, created_at, plus availability flags. |
| `memory delete <run_id>` | One line: `Tombstoned run_id=<id>`. |
| `coverage show <run_id>` | One line + summary: `<mapping_granularity> · <covered>/<total> covered · run_id=<id>`. |
| `coverage diff <baseline> <target>` | Headline + per-file delta count: `+<N> covered · -<M> uncovered · <K> files changed`. |
| `regression compare <baseline> <target>` | One line: `<status> · <new_failures>/<fixed>/<flipped>`. |
| `regression latest` | Same as `regression compare` but with the resolved pair shown. |
| `localization <run_id> [--formula] [--top-n]` | Headline mode + formula + top entries: `<mode> · <formula> · <K> entries`. Per-entry: `<rank>. <code_location.symbol>@<line> (<score>)`. |
| `localization latest` | Same as `localization <run_id>` but with the resolved run shown. |

### Error / unavailable envelopes

When `envelope.ok == False`, the renderer emits a 2-3 line block:

```
✗ <command>
  <error.code>: <error.message>
  <relevant context if details is non-empty, e.g. install_hint>
```

When `data.<subreport>.kind == "unavailable"`, the renderer emits:

```
— <subreport>: unavailable (<reason>)
```

### Warnings

When `envelope.warnings` is non-empty, append a one-line-each block AFTER the main payload:

```
warnings:
  ⚠ <warning.code>: <warning.message>
```

## Architectural shape

### Renderer registry pattern

```python
# src/novetest/cli/renderers/registry.py
from typing import Callable
from novetest.cli.output import Envelope

# verb token → renderer function
_RENDERERS: dict[str, Callable[[Envelope], str]] = {
    "init": render_init,
    "test": render_test,
    "run": render_run,
    "status": render_status,
    "inspect": render_inspect,
    "compare": render_compare,
    "replay": render_replay,
    "memory.list": render_memory_list,
    "memory.show": render_memory_show,
    "memory.delete": render_memory_delete,
    "coverage.show": render_coverage_show,
    "coverage.diff": render_coverage_diff,
    "regression.compare": render_regression_compare,
    "regression.latest": render_regression_latest,
    "localization": render_localization,
    "localization.latest": render_localization_latest,
    "version": render_version,
    "help": render_help,
}

def render_text(envelope: Envelope) -> str:
    if envelope.errors:
        return render_error(envelope)
    renderer = _RENDERERS.get(envelope.command, render_fallback)
    body = renderer(envelope)
    if envelope.warnings:
        body += "\n" + render_warnings(envelope.warnings)
    return body
```

The registry dispatch is by `envelope.command` (the exact string the verb handler sets). For unknown commands (e.g. a stub `coverage.show` that's not yet implemented), the `render_fallback` renderer emits a brief "<command>: not implemented" line.

### `emit_envelope` change

In `src/novetest/cli/output.py`, the TEXT branch becomes:

```python
def emit_envelope(envelope: Envelope, mode: OutputMode, stream: TextIO | None = None) -> None:
    target = stream if stream is not None else sys.stdout
    if mode == OutputMode.TEXT:
        from novetest.cli.renderers import render_text
        text = render_text(envelope)
        target.write(text + "\n")
    elif mode == OutputMode.NDJSON:
        payload = envelope.to_dict()
        line = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        target.write(line + "\n")
    else:  # JSON
        payload = envelope.to_dict()
        text = json.dumps(payload, indent=2, sort_keys=True)
        target.write(text + "\n")
    flush = getattr(target, "flush", None)
    if callable(flush):
        flush()
```

The import is deferred inside the function so `cli/output.py` does NOT import from `cli/renderers/` at module load time (preserving the existing dependency direction `cli/handlers → cli/output`; the new `cli/renderers` lives at a sibling level and only imports from `cli/output` for the `Envelope` dataclass).

### Per-verb renderer signature

```python
def render_test(envelope: Envelope) -> str:
    data = envelope.data
    recs = data.get("recommendations", [])
    target = data.get("target_expression", "")
    run_id = data.get("run_reference", {}).get("run_id", "?")
    summary = f"✓ {len(recs)} recommendations · run_id={run_id}"
    if not recs:
        return summary
    lines = [summary, ""]
    for r in recs:
        glyph = _category_glyph(r["category"])
        lines.append(f"  {glyph} {r['category']}: {r.get('headline', '')}")
    return "\n".join(lines)
```

All renderers are pure functions taking `Envelope`, returning `str`. No `print`, no stream writes. The dispatcher (`render_text`) handles the final string assembly.

## Out of scope — DO NOT do in this cycle

- **ANSI color**: deferred to a follow-up cycle. The renderer output is plain ASCII / Unicode (glyphs ✓✗⚠— are OK as Unicode literals; they render fine on every modern terminal including Windows Terminal). No `colorama`, no `rich`, no `\033[...m` escapes anywhere.
- **TTY-feature detection beyond what `resolve_output_mode` already does**: this slice does not touch mode resolution. The existing `isatty()` check stays as-is.
- **JSON / NDJSON envelope shape change**: PROHIBITED. Any `json.dumps(payload)` output must be byte-identical before and after this slice. Pin via snapshot regression.
- **`rich` library or any new runtime dep**: hand-rolled only. The renderer is plain Python f-strings + minimal table formatting.
- **NDJSON streaming renderer** for `--stream` mode (post-MVP per `foundations.md §"NDJSON stream"`): this slice handles `OutputMode.TEXT` and `OutputMode.JSON` / `OutputMode.NDJSON` only.
- **Localization mode/formula carve-outs** (the `localization-formula-noop-in-mode` warning logic): warnings render via the generic `warnings:` block; no per-warning-code custom rendering.
- **CLI handler changes** in `cli/app.py` / `cli/handlers/`: the only `cli/` change is `cli/output.py::emit_envelope` (the 1-line `if mode == OutputMode.TEXT` branch switch). All verb handlers stay byte-identical.
- **Help-text content changes**: the `describe_command_surface()` output (Cyclopts-derived) stays as-is; `render_help` just formats the existing surface.

## Verification surface

### Per-renderer snapshot tests

Use `syrupy` to snapshot-pin the text output for each renderer. The fixture envelopes can be constructed inline (no need to invoke the engines) — the renderer is a pure function.

Example:

```python
# tests/unit/cli/renderers/test_test_renderer.py
from novetest.cli.output import Envelope
from novetest.cli.renderers import render_text

def test_render_test_with_recommendations(snapshot):
    envelope = Envelope(
        command="test",
        ok=True,
        data={
            "target_expression": "tests/test_foo.py",
            "run_reference": {"run_id": "01HXYZ..."},
            "recommendations": [
                {"category": "investigate_location", "headline": "divide@34 (Ochiai 1.0)"},
                {"category": "all_green", "headline": "all tests passing"},
            ],
        },
    )
    assert render_text(envelope) == snapshot
```

### Integration tests (end-to-end)

For at least the 3 most user-facing verbs (`test`, `run`, `localization`), add subprocess-invocation tests under `tests/integration/cli/test_text_mode_end_to_end.py`:

```python
def test_novetest_test_text_mode_against_pytest_basic_fixture():
    result = subprocess.run(
        ["uv", "run", "novetest", "test", "--output", "text"],
        cwd=PYTEST_BASIC_FIXTURE,
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    # No bare JSON braces in TEXT mode output (regression guard against
    # the pre-slice "pretty JSON" bug):
    assert not result.stdout.lstrip().startswith("{")
    # The summary line is present:
    assert "recommendations" in result.stdout
```

### JSON / NDJSON byte-identity regression guard

Run the existing JSON / NDJSON snapshot tests (`tests/unit/cli/test_output_envelope.py`, `tests/integration/orchestration/test_test_workflow.ambr`) and confirm **zero snapshot changes**. Any byte-diff in JSON / NDJSON output indicates the slice broke the AI-agent contract.

### Empirical user smoke

After implementation:

```bash
uv run novetest --help                          # should be readable text, not JSON
uv run novetest test --output text              # in pytest-basic fixture
uv run novetest memory list --output text       # tabular human surface
uv run novetest --output json --help            # still emits JSON envelope verbatim
NOVETEST_OUTPUT=json uv run novetest --help     # env override still wins
```

Capture stdout of each in the handoff for Manual Test to field.

## Definition of Done (claim closed in handoff §"DoD bullets believed closed")

1. `src/novetest/cli/renderers/` package created with `__init__.py`, `registry.py`, `_format.py`, and one renderer module per verb token in `_RENDERERS`.
2. `render_text(envelope: Envelope) -> str` is the single public entry point; consumers (only `cli/output.py::emit_envelope`) call this.
3. `cli/output.py::emit_envelope` TEXT branch routes to `render_text` instead of `json.dumps`. JSON / NDJSON branches **byte-identical** to pre-slice (snapshot-pinned).
4. Per-renderer unit tests (snapshot-pinned via `syrupy`) cover every verb listed in §"Verb coverage" above — error envelopes + ok envelopes + unavailable sub-reports + non-empty warnings.
5. Integration tests demonstrate end-to-end TEXT-mode rendering for `test`, `run`, `localization` against existing fixture projects.
6. The `--output text` output for `novetest test` in `tests/fixtures/projects/pytest-basic/` is **NOT** pretty JSON (regression guard via `assert not stdout.lstrip().startswith("{")`).
7. `--output json` and `--output ndjson` snapshots unchanged (zero `syrupy` updates needed).
8. `NOVETEST_OUTPUT=json` env var override still routes to JSON envelope verbatim.
9. `uv run mypy --strict src/novetest` → success (no new typing surface added beyond the renderer functions).
10. `uv run pytest -q tests/unit tests/integration` → green minus pre-existing dotnet host-equip failure (`1226+ passed`, no NEW failures introduced).
11. Zero changes to: `cli/app.py`, `cli/handlers/`, `orchestration/`, any engine layer, any decision file, `foundations.md`, `pyproject.toml::dependencies`.
12. WORKLOG entry written; handoff filed at `agent-comms/handoffs/orchestration-team-2026-06-18-human-text-renderer-cli-text-mode.md`; `tools/regen_comms_index.py` run before commit.

## Failure modes (PM-anticipated; mitigation in your hands)

1. **Verb completeness gap**: if a new verb is added in a future cycle and its renderer is missing, `render_fallback` should produce a sensible "no human renderer for `<command>`; here's the JSON" output. This is the safety net for stubs and any future addition.
2. **Unicode glyph rendering on Windows CMD**: ✓✗⚠— glyphs are fine on Windows Terminal (modern default) and PowerShell ISE; legacy cmd.exe may show `?` boxes. Acceptable — modern Windows users get the right rendering, and cmd.exe users still get the textual code (`<status> · <count>/<total>`). If you want a fallback ASCII path, gate via `os.environ.get("NOVETEST_TEXT_ASCII")` env var (post-MVP polish; not a DoD bullet).
3. **Localization `formula_noop` warning rendering**: the generic `warnings:` block renders this verbatim. Do not add per-warning-code special-cases in this slice — that's the renderer code smell that grows fast and dies hard.
4. **Snapshot churn during dev**: use `syrupy --snapshot-update` liberally during iteration; the final commit must NOT have uncommitted snapshot updates. Run `pytest --snapshot-update` on the final renderer version, commit the .ambr files, and let CI re-verify.
5. **Test rendering of unstable fields**: `run_id` is a ULID (unique per test invocation), `verifiedAt` is a timestamp. Snapshot tests should use deterministic constructed envelopes (inline dicts, not engine output), so these fields are reproducible. The integration tests can use regex / substring assertions instead of snapshot equality for the unstable fields.

## Procedural posture

- **Karpathy skill**: invoke `andrej-karpathy-skills:karpathy-guidelines` before any code edit. Goal-driven, surgical, simplicity-first. This slice is exactly the kind where "simplicity first" matters — resist the temptation to add color, tables-with-borders, or `rich`-style fanciness. Plain f-strings + glyphs.
- **Charter scope**: `cli/` and `cli/renderers/` are Orchestration territory (per `.claude/agents/novetest-orchestration-team.md`). No charter exception needed.
- **Worktree**: branch `orchestration/human-text-renderer` off `main`. After CI green + tests passing, handoff to Main Branch for FF-merge.
- **Manual Test**: required (this is user-visible behavior). Manual Test should run the empirical smoke commands listed in §"Empirical user smoke" and field-test the text output.

## Cycle close direction (PM perspective)

- Manual Test verifies the text-mode output is genuinely human-friendly across the 16+ verbs.
- PM cycle-close: tick no DoD bullet in `delivery-phasing.md` (this is Future-cycle queue item, not a Phase 0 DoD bullet). Cycle-close history entry under `agent-comms/history/2026-06-18-human-text-renderer-cli-text-mode.md`. The Future-cycle queue carries forward minus #9.
- **No new decision required.** The architectural shape (per-verb renderers under `cli/renderers/`) is bounded by this brief; no policy-level question that needs CEO sign-off.

## Coordination with parallel cycle (Release team, B안)

The Release team is dispatched simultaneously with `agent-comms/tasks/release-team-2026-06-18-windows-install-ps1-and-binary-pipeline.md` (Future-cycle queue #4). **Zero file-footprint overlap** — Release touches `scripts/`, `.github/workflows/`, `foundations.md`, `README.md`; Orchestration touches `src/novetest/cli/` + `tests/`. Either may FF-merge first; no merge conflict expected.

**One consideration**: if Release's Windows pipeline lands first and adds CI runs on `windows-latest`, your text-mode tests will also run there. The Unicode glyphs ✓✗⚠— must render correctly on Windows. They do on Windows Terminal + modern PowerShell. If a Windows CI cell fails on glyph rendering, that's the signal to add the ASCII fallback gate from §"Failure modes" #2. Probably won't happen; mentioned for completeness.
