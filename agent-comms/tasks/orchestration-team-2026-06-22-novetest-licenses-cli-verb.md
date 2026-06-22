---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-22
slug: novetest-licenses-cli-verb
related:
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
  - agent-comms/history/2026-06-18-human-text-renderer-cli-text-mode.md
  - agent-comms/history/2026-06-09-mvp-release-ready-positive-sign-off.md
---

# `novetest licenses` CLI verb — expose third-party attribution to users + AI agents

## Mission

Add a new top-level CLI verb `novetest licenses` that surfaces all third-party
dependencies (runtime, vendored, install-time-bootstrap) as a structured
`novetest/v1` envelope. With the `--full` flag, the envelope also carries
the verbatim NOTICES.md text body.

**Closes Future-cycle queue item #2b** (the named Wave 2 follow-up from
the 2026-06-19 NOTICES expansion cycle). Satisfies decision
`2026-06-03-junit-console-launcher-vendor.md §3` mandate that a CLI surface
for third-party attribution must exist before any binary-redistribution
licensing audit.

This cycle runs in parallel with a Release-team **v0.1.2 publication
cycle** that includes this verb in the next user-visible release. The
Release brief explicitly depends on this slice merging first — file
your handoff promptly so Release can pick up `pyproject.toml::version`
bump and CEO can tag.

## Pre-flight reading (mandatory, in order)

1. `CLAUDE.md` — project-wide rules.
2. `.claude/agents/novetest-orchestration-team.md` — your charter.
3. `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`
   §3 ("Public attribution surface") — the binding mandate.
4. `NOTICES.md` — the canonical attribution document (REPO ROOT). All
   five entries you must enumerate are here.
5. `agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md`
   — what got inlined into NOTICES.md (verbatim Apache 2.0 + BSD 3-Clause
   texts) and PEP 639 wheel-license auto-discovery context.
6. `agent-comms/history/2026-06-18-human-text-renderer-cli-text-mode.md`
   — text renderer registry pattern (noun-grouped, 7-glyph palette,
   `cli/renderers/registry.py` dispatch). You add a new entry here.
7. `src/novetest/cli/app.py` — existing verb registration patterns. The
   relevant precedents: top-level `@app.command def status()` (line 346,
   single verb) and `@app.command def init()` (line 205).
8. `src/novetest/cli/output.py` — `Envelope` dataclass, `emit_envelope`,
   exit-code constants.
9. `src/novetest/cli/renderers/registry.py` — `_RENDERERS` dict and
   `render_text` entry point. You wire a new key here.

## Scope (CEO-confirmed at brief authoring)

Four design points locked at PM↔CEO synthesis 2026-06-22:

- **Q1 (verb shape) = subcommand-style `novetest licenses`** — not a
  global flag. Consistent with the 16 existing verbs. Registered as a
  top-level command via `@app.command` (no nested `App` instance —
  there are no sub-subcommands).
- **Q2 (output content) = `--full` flag toggles verbatim** — default
  emits a compact summary list of 5 packages; `--full` additionally
  embeds the entire NOTICES.md text body in `data.notices_text`. Default
  keeps the envelope under ~2 KB; `--full` is opt-in for the ~15 KB
  payload.
- **Q3 (envelope schema) = compatible extension to `novetest/v1`** —
  add new keys under `data` only; never modify or rename existing keys.
  Schema string stays `"novetest/v1"`. This is the "additive
  extension" pattern documented in `foundations.md §JSON envelope
  versioning`.
- **Q4 (release notes tone)** — handled by Release brief; not your
  concern.

## Data contract (PIN VERBATIM)

### Envelope shape — default (no `--full`)

```json
{
  "command": "licenses",
  "ok": true,
  "schema": "novetest/v1",
  "data": {
    "summary": "Nove Test redistributes or links to 5 third-party components.",
    "licenses": [
      {
        "package": "cyclopts",
        "version": ">=3.0",
        "license": "Apache-2.0",
        "source": "runtime",
        "project_url": "https://github.com/BrianPugh/cyclopts"
      },
      {
        "package": "numpy",
        "version": ">=1.26",
        "license": "BSD-3-Clause",
        "source": "runtime",
        "project_url": "https://github.com/numpy/numpy"
      },
      {
        "package": "junit-platform-console-standalone",
        "version": "1.11.4",
        "license": "EPL-2.0",
        "source": "vendored",
        "project_url": "https://github.com/junit-team/junit5"
      },
      {
        "package": "PyApp",
        "version": "0.22.0",
        "license": "Apache-2.0 OR MIT",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/ofek/pyapp"
      },
      {
        "package": "python-build-standalone",
        "version": "CPython",
        "license": "PSF + permissive (OpenSSL, libffi, ncurses, etc.)",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/indygreg/python-build-standalone"
      }
    ],
    "notices_reference": "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)"
  },
  "errors": [],
  "warnings": []
}
```

### Envelope shape — with `--full`

Identical to above, **plus** one additional key under `data`:

```json
{
  "data": {
    "...everything above...": "...",
    "notices_text": "<verbatim NOTICES.md content as a single UTF-8 string>"
  }
}
```

`notices_text` is the COMPLETE NOTICES.md file body verbatim (15,581
bytes as of `9c5abbf`). Encoding: UTF-8. Line endings: LF (preserve
exactly what's in the source file).

### Field semantics (pinned)

| Field | Meaning |
|---|---|
| `package` | The canonical package name as it appears in NOTICES.md `### <package>` heading. |
| `version` | Version pin or range as it appears in the NOTICES.md `### <package> (<version>)` parenthetical. For `python-build-standalone` use the literal string `"CPython"` (no specific pin — version varies per PyApp release). |
| `license` | The SPDX identifier (or comma-separated SPDX list) from the NOTICES.md `- License:` bullet. For PyApp use `"Apache-2.0 OR MIT"`. For python-build-standalone use the full string above. |
| `source` | One of `"runtime"` / `"vendored"` / `"install-time-bootstrap"`. Maps to the NOTICES.md `## Runtime dependencies` / `## Vendored binary` / `## Install-time bootstrap` section. |
| `project_url` | The `https://...` URL from the NOTICES.md `- Project:` bullet. |
| `summary` | The literal string above; do NOT compute "X components" dynamically — pin to `"5 third-party components"`. (Drift guard test below catches divergence.) |
| `notices_reference` | The literal string above. Documents where the verbatim file lives in the installed wheel. |
| `notices_text` | Only present when `--full`. Verbatim NOTICES.md file content. UTF-8, LF-terminated. |

## Files to write / modify

### 1. NEW — `src/novetest/orchestration/licenses/__init__.py`

Small new package under `orchestration/` (your territory). Houses:

- `LicenseEntry` dataclass (5 fields above).
- `LICENSE_ENTRIES: tuple[LicenseEntry, ...]` — the static const list of
  5 entries, hand-written to match the data contract verbatim.
- `read_notices_text() -> str` — returns the verbatim NOTICES.md text.
- `build_licenses_view(include_full: bool) -> LicensesView` — assembles
  the `data` dict payload. Pure function; no I/O when
  `include_full=False`.

### 2. NEW — `src/novetest/orchestration/licenses/notices_loader.py`

The resource-loading mechanism for the NOTICES.md text body. Implementation:

- **Preferred path (installed wheel)**: use `importlib.metadata.Distribution.from_name("novetest").read_text("NOTICES.md")`. Returns the dist-info-embedded copy per PEP 639. Returns `None` if the file is absent (defensive).
- **Fallback (editable install / source checkout)**: walk up from
  `Path(__file__)` to find a directory containing both `pyproject.toml`
  and `NOTICES.md`. Read it. This handles `uv pip install -e .` and
  `python -c "import novetest..."` from a fresh clone.
- **Last-resort failure**: if neither resolves, raise a `LookupError`
  with a clear message. Surfaced as an envelope error code
  `notices-unavailable` at the CLI handler boundary.

Implementation is Orchestration's call — choose the simplest path that
works for both installed wheel AND editable install. Karpathy
"Simplicity First" applies.

### 3. NEW — `src/novetest/cli/renderers/licenses.py`

Text renderer module. Signature: `render_licenses(envelope: Envelope) -> str`.

Output shape (pinned at brief level — Orchestration may polish glyph
spacing per the 7-glyph palette):

```
licenses (5 third-party components)

  runtime dependencies
    cyclopts (>=3.0)                              Apache-2.0
    numpy (>=1.26)                                BSD-3-Clause

  vendored binary
    junit-platform-console-standalone (1.11.4)    EPL-2.0

  install-time bootstrap
    PyApp (0.22.0)                                Apache-2.0 OR MIT
    python-build-standalone (CPython)             PSF + permissive

  full verbatim license texts: novetest licenses --full
  attribution file (in wheel): *.dist-info/licenses/NOTICES.md
```

When `--full` was supplied, append a divider line and the verbatim
NOTICES.md body:

```
  ...(summary as above)...

  --- VERBATIM NOTICES.md ---
  <full text>
```

Column alignment: padding the package-with-version field to a fixed
width (e.g., 46 chars) is sufficient. No ANSI color is required (the
TEXT renderer cycle established no-color is the baseline; future polish
can layer color in via the existing `apply_no_color` hook).

### 4. MODIFY — `src/novetest/cli/renderers/registry.py`

Add:
```python
from novetest.cli.renderers.licenses import render_licenses
```

And add the entry to `_RENDERERS`:
```python
"licenses": render_licenses,
```

(Place alphabetically — after `localization.latest`, before `memory.list` — to keep the dict grep-friendly.)

### 5. MODIFY — `src/novetest/cli/app.py`

Add a new top-level command after `status` (line 354), before the
`# Memory subcommand group` section:

```python
@app.command(name="licenses")
def licenses_cmd(
    *,
    full: Annotated[bool, Parameter(name=["--full"])] = False,
) -> None:
    """List third-party components Nove Test redistributes or links to.

    With ``--full``, the envelope also carries the verbatim NOTICES.md
    text body in ``data.notices_text``.
    """
    from novetest.orchestration.licenses import build_licenses_view
    try:
        view = build_licenses_view(include_full=full)
    except LookupError as exc:
        _emit_and_exit(
            Envelope(
                command="licenses",
                ok=False,
                errors=(EnvelopeError(code="notices-unavailable", message=str(exc)),),
            ),
            EXIT_GENERIC,
        )
    _emit_and_exit(
        Envelope(command="licenses", ok=True, data=view.to_dict()),
        EXIT_OK,
    )
```

`LicensesView.to_dict()` returns the `data` payload per the data
contract above.

### 6. NEW — `tests/unit/orchestration/licenses/test_licenses_view.py`

- `test_default_view_enumerates_5_packages` — assert
  `len(view.licenses) == 5`, asserts exact package names in expected
  source-group order.
- `test_default_view_omits_notices_text` — assert
  `"notices_text" not in view.to_dict()`.
- `test_full_view_includes_notices_text` — assert
  `view.notices_text.startswith("# Third-Party Notices\n")` and
  `len(view.notices_text) > 15000` (current size ~15.5 KB).
- `test_summary_string_is_pinned` — assert
  `view.summary == "Nove Test redistributes or links to 5 third-party components."`
  (drift guard).
- `test_notices_reference_is_pinned` — assert
  `view.notices_reference == "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)"`.

### 7. NEW — `tests/unit/orchestration/licenses/test_notices_drift_guard.py`

The critical guard against NOTICES.md / `LICENSE_ENTRIES` drift:

- `test_every_static_entry_has_matching_notices_section` — for each
  `LicenseEntry` in `LICENSE_ENTRIES`, assert NOTICES.md contains a
  `### <package>` heading whose immediately-following lines include
  `- License: <license>` matching the const's license field.
- `test_every_notices_section_has_matching_static_entry` — parse
  NOTICES.md for every `### <package> (<version>)` heading under one of
  the three target sections (`## Runtime dependencies`, `## Vendored
  binary`, `## Install-time bootstrap`); assert each appears in
  `LICENSE_ENTRIES` with matching package + version + license.

This is a unit test, not an integration test — it reads NOTICES.md from
the repo root (resolved via the same `notices_loader.py` fallback path).
The test runs against the source-checkout NOTICES.md and catches any
manual edit to NOTICES.md that doesn't mirror into the const (or vice
versa) before merge.

### 8. NEW — `tests/integration/cli/test_licenses_verb.py`

- `test_novetest_licenses_default_envelope_json` — subprocess
  `novetest licenses --output json`; assert exit 0, envelope has
  `command=="licenses"`, `ok==True`, `data.licenses` has 5 entries,
  `"notices_text" not in data`.
- `test_novetest_licenses_full_envelope_json` — subprocess
  `novetest licenses --full --output json`; assert exit 0,
  `data.notices_text.startswith("# Third-Party Notices\n")`,
  `len(data.notices_text) > 15000`.
- `test_novetest_licenses_text_mode_summary` — subprocess
  `novetest licenses --output text`; assert "licenses (5 third-party
  components)" appears in stdout, "cyclopts (>=3.0)" appears, "Apache-2.0"
  appears, "PyApp (0.22.0)" appears.
- `test_novetest_licenses_full_text_mode_includes_verbatim` —
  subprocess `novetest licenses --full --output text`; assert
  "--- VERBATIM NOTICES.md ---" appears in stdout AND
  "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" (from
  the verbatim Apache 2.0 text) appears.

### 9. NEW — `tests/integration/cli/__snapshots__/test_licenses_verb.ambr`

syrupy snapshot for the default `novetest licenses --output text`
output. Pinned per the renderer cycle's snapshot pattern (#9).
Snapshot the FULL text including the trailing hint lines.

Do NOT snapshot the `--full` output — its body is 15 KB of verbatim
license text and snapshot-pinning that creates massive diff noise on
any NOTICES.md edit. The drift-guard unit test (#7) plus the
substring-based integration test (#8) cover `--full` adequately.

### 10. MODIFY — `pyproject.toml` (resource inclusion, IF needed)

If your `notices_loader.py` chooses the `importlib.metadata` /
`importlib.resources` path, you may need to ensure NOTICES.md is
embedded such that the chosen API can read it.

- **If using `Distribution.from_name("novetest").read_text("NOTICES.md")`**:
  PEP 639 auto-discovery already embeds NOTICES.md at
  `*.dist-info/licenses/NOTICES.md` (verified empirically in
  2026-06-19 NOTICES cycle — Manual Test confirmed `uv build --wheel`
  ships it). `Distribution.read_text("NOTICES.md")` reads from
  dist-info; this works out of the box. **No `pyproject.toml` change
  needed.**

- **If using `importlib.resources.files("novetest").joinpath(...)`**:
  this reads from inside the package directory, not dist-info. You'd
  need a `[tool.hatch.build.targets.wheel.force-include]` entry mapping
  `NOTICES.md` to `src/novetest/_data/NOTICES.md`. Adds machinery; only
  do this if the `importlib.metadata` path proves unreliable in
  practice.

**Recommendation**: try `Distribution.from_name("novetest").read_text("NOTICES.md")` first. The fallback for editable install / source checkout is independent of the embed mechanism — it walks up from `Path(__file__).parent` to find repo-root NOTICES.md.

## Files NOT to touch

- `NOTICES.md` itself — the canonical source. Any drift between the
  static `LICENSE_ENTRIES` const and NOTICES.md must be resolved by
  editing the const, not the doc. Surface a question to PM if you
  believe NOTICES.md has a bug.
- `pyproject.toml::version` — Release team's territory. The v0.1.2
  bump is a separate cycle (this cycle's twin).
- Any other CLI verb's handler / renderer.
- `src/novetest/__init__.py` — version-resolution machinery; out of
  scope.
- Existing snapshot files (`*.ambr`) — except your new
  `test_licenses_verb.ambr`.
- `agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md`
  — historical record; do not amend.

## Verification commands (must-pass before reporting done)

```bash
# 1. mypy
uv run mypy --strict src/novetest

# 2. Full unit + integration suite (baseline: ~1300 passed pre-slice)
uv run pytest -q tests/unit tests/integration

# 3. Empirical CLI smoke — JSON envelope
uv run novetest licenses --output json | python3 -c 'import sys,json; e=json.load(sys.stdin); assert e["ok"] and e["command"]=="licenses" and len(e["data"]["licenses"])==5 and "notices_text" not in e["data"], e; print("DEFAULT JSON OK")'

# 4. Empirical CLI smoke — --full JSON
uv run novetest licenses --full --output json | python3 -c 'import sys,json; e=json.load(sys.stdin); assert e["ok"] and len(e["data"]["notices_text"]) > 15000, len(e["data"].get("notices_text", "")); print("FULL JSON OK")'

# 5. Empirical CLI smoke — text mode
uv run novetest licenses --output text   # eyeball: shows summary block

# 6. Snapshot stability (one snapshot for the default text mode)
uv run pytest tests/integration/cli/test_licenses_verb.py --snapshot-warn-unused
```

## Definition of Done (10 bullets — PM ticks at cycle close)

- [ ] **#1 New verb registered**: `novetest licenses --help` returns
      a structured envelope describing the verb (cyclopts auto-help).
- [ ] **#2 Default envelope correct**: `novetest licenses --output json`
      emits the data contract above byte-equivalent (5 packages, no
      `notices_text`, `summary` + `notices_reference` strings pinned).
- [ ] **#3 `--full` envelope correct**: `novetest licenses --full
      --output json` carries the same envelope PLUS
      `data.notices_text` = full NOTICES.md text body.
- [ ] **#4 Text mode summary renders**: `novetest licenses` (TTY-auto
      → text) shows the summary block per the renderer pseudocode above
      with 5 enumerated packages.
- [ ] **#5 Text mode `--full` appends verbatim**: `novetest licenses
      --full` (text mode) shows the summary block AND the verbatim
      NOTICES.md content after the divider.
- [ ] **#6 Drift-guard test passes both directions**: every entry in
      the static const has a matching `### <package>` section in
      NOTICES.md AND every NOTICES.md `### <package>` section appears
      in the const.
- [ ] **#7 mypy --strict GREEN**: no new mypy errors; baseline 109
      source files unchanged ± your new modules.
- [ ] **#8 Full suite GREEN**: pytest pass count ≥ pre-slice baseline +
      N (your new tests). Chronic dotnet-host-equip skip stays as-is.
- [ ] **#9 Snapshot pinned**: one new `.ambr` snapshot file for the
      default-mode text rendering. `--snapshot-update` not in CI; you
      generate locally and commit.
- [ ] **#10 Registry wired**: `cli/renderers/registry.py::_RENDERERS`
      contains `"licenses"` key mapping to `render_licenses`.

## Karpathy guidelines (mandatory invocation)

Before writing any code in `src/` or `tests/`, invoke the
`andrej-karpathy-skills:karpathy-guidelines` skill via the Skill tool.
Apply all four:

1. **Think Before Coding** — sketch the module shape mentally before
   typing; what does the import graph look like? Where does the
   NOTICES.md text actually flow?
2. **Simplicity First** — prefer the importlib.metadata path over
   force-include + importlib.resources. Prefer a single Python module
   over splitting into 3 files. Static const list over runtime regex
   parsing of NOTICES.md.
3. **Surgical Changes** — touch only the files enumerated above. Do
   not refactor `cli/app.py`'s structure or the renderers/ layout.
4. **Goal-Driven Execution** — DoD bullets are the unambiguous gate.
   Verify each against your code before filing the handoff.

## Reporting back to PM (in your handoff)

Standard handoff at `agent-comms/handoffs/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md`. Include:

- "DoD bullets believed closed" list (cite each).
- Empirical CLI smoke output for #2 and #3 verbatim — paste the JSON
  envelopes.
- A note: did `Distribution.from_name(...).read_text("NOTICES.md")`
  work first try, or did you fall back to the alternative resource path?
  This is load-bearing institutional learning for future similar
  cycles.
- Any deviations from the data contract above (e.g., field-name
  changes) — surface as questions to PM, do not silently land.
- Confirm Release team can pick up `v0.1.2` immediately after merge —
  your slice does NOT touch `pyproject.toml::version`.

## Parallel cycle awareness

Release team is running the **v0.1.2 publication** cycle in parallel:

- Their file footprint: `pyproject.toml` (single 1-line `version` bump).
- Your file footprint: `src/novetest/orchestration/licenses/...`,
  `src/novetest/cli/...`, `tests/unit/orchestration/licenses/...`,
  `tests/integration/cli/...`, possibly `pyproject.toml` IF you choose
  the force-include path (avoid this if possible).
- **Merge order**: your slice merges FIRST; Release's `pyproject.toml`
  bump merges on top of yours.
- **If you end up touching `pyproject.toml`** (force-include section
  only — NOT the version field): communicate immediately via a question
  to PM. PM coordinates the rebase / merge order with Release.

## Estimated effort

- Module skeleton + const list + envelope: ~1 hour
- Renderer: ~1 hour
- Tests (drift guard is the trickiest — needs a small NOTICES.md
  section parser): ~2 hours
- Snapshot + integration: ~1 hour
- Verification + handoff: ~30 min

Total: ~1 working day (1 sitting). The drift-guard test is the only
non-trivial design surface; everything else is mechanical wiring on
top of existing patterns.

## Why this matters

Three independent users benefit immediately:

1. **End users** running `novetest licenses` in a Cyclopts/Anthropic-CLI
   context see what third-party code their installation depends on
   without having to find and open NOTICES.md in a wheel's dist-info.
2. **AI coding agents** (the intended consumer profile) get a
   machine-parseable JSON envelope with stable field names — license
   compatibility checks become a single CLI invocation.
3. **Legal / compliance audits** for binary redistribution (the
   2026-06-03 decision's load-bearing trigger) get a single
   authoritative surface that's CI-tested for drift against the
   canonical NOTICES.md.

The verb closes Future-cycle queue item #2b, the last named carry from
the 2026-06-09 MVP release-ready sign-off backlog (the other open item
#10 — `workspaces test` orchestrator — is gated on user feedback per
the 2026-06-09 disposition, not this cycle).
