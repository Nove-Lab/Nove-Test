---
from: novetest-main-branch-team
to: novetest-manual-test-team
type: verification
status: ready
created: 2026-06-22
slug: novetest-licenses-cli-verb
merged_commit: 2e0925b
source_handoff: agent-comms/handoffs/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
related:
  - agent-comms/tasks/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
---

# Verification — `novetest licenses` CLI verb (merged at `2e0925b`)

## Merge summary

Worktree `orchestration/novetest-licenses-cli-verb` FF-merged on top of
`37f7838` (PM parallel dispatch). 2 commits replayed verbatim:

| Commit | Slice |
|---|---|
| `61ddd6d` | `cli: novetest licenses verb — third-party attribution envelope` |
| `2e0925b` | `comms: orchestration handoff for novetest-licenses-cli-verb` |

Zero conflicts. Closes Future-cycle queue item **#2b**; satisfies decision
`2026-06-03-junit-console-launcher-vendor.md §3` (public attribution surface
mandate). Followed by the Release v0.1.2 bump merging on top (`5519ccf` HEAD
after both slices land — see the companion verification doc
`2026-06-22-v0.1.2-publication.md`).

## Source files landed (orchestration slice only)

| File | Status |
|---|---|
| `src/novetest/orchestration/licenses/__init__.py` | NEW |
| `src/novetest/orchestration/licenses/notices_loader.py` | NEW |
| `src/novetest/cli/renderers/licenses.py` | NEW |
| `src/novetest/cli/renderers/registry.py` | MOD (+import + `"licenses"` key in `_RENDERERS`) |
| `src/novetest/cli/app.py` | MOD (`licenses_cmd` handler + `"licenses"` in `_SUBCOMMAND_TOKENS`) |
| `tests/unit/orchestration/licenses/{__init__,test_licenses_view,test_notices_drift_guard,test_notices_loader}.py` | NEW (14 unit tests) |
| `tests/unit/cli/renderers/test_licenses.py` + `__snapshots__/test_licenses.ambr` | NEW (3 + 2 snapshots) |
| `tests/integration/cli/test_licenses_verb.py` + `__snapshots__/test_licenses_verb.ambr` | NEW (5 + 1 snapshot) |
| `WORKLOG.md` | MOD (2026-06-22 entry) |

**+22 new tests**. `src/novetest/cli/output.py` NOT touched (TEXT routes
through existing `render_text`; JSON/NDJSON byte-frozen). `pyproject.toml`
NOT touched. `command_surface.py` deliberately NOT touched (handoff §1
flagged for PM follow-up — see "Critical edge cases" §1 below).

## Post-merge gate (on `5519ccf` after release slice also lands)

| Check | Result |
|---|---|
| `unset PYTHONPATH && uv run mypy --strict src/novetest` | **Success — 112 source files** (baseline 109 + 3 new modules) |
| `unset PYTHONPATH && uv run pytest -q tests/unit tests/integration --deselect tests/integration/run/test_jest_basic.py --deselect tests/integration/run/test_jest_coverage.py --deselect tests/integration/coverage/test_jest_coverage.py` | **1327 passed + 0 failed** (40 snapshots; jest deselected — see "Critical edge cases" §3) |
| Wheel build | `dist/novetest-0.1.2-py3-none-any.whl` produced cleanly |

## Empirical envelope pins (verbatim — copy-paste from merged `2e0925b`+`5519ccf`)

### `novetest licenses --output json` (default)

```json
{
  "command": "licenses",
  "data": {
    "licenses": [
      {"license": "Apache-2.0", "package": "cyclopts", "project_url": "https://github.com/BrianPugh/cyclopts", "source": "runtime", "version": ">=3.0"},
      {"license": "BSD-3-Clause", "package": "numpy", "project_url": "https://github.com/numpy/numpy", "source": "runtime", "version": ">=1.26"},
      {"license": "EPL-2.0", "package": "junit-platform-console-standalone", "project_url": "https://github.com/junit-team/junit5", "source": "vendored", "version": "1.11.4"},
      {"license": "Apache-2.0 OR MIT", "package": "PyApp", "project_url": "https://github.com/ofek/pyapp", "source": "install-time-bootstrap", "version": "0.22.0"},
      {"license": "PSF + permissive (OpenSSL, libffi, ncurses, etc.)", "package": "python-build-standalone", "project_url": "https://github.com/indygreg/python-build-standalone", "source": "install-time-bootstrap", "version": "CPython"}
    ],
    "notices_reference": "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)",
    "summary": "Nove Test redistributes or links to 5 third-party components."
  },
  "errors": [],
  "ok": true,
  "schema": "novetest/v1",
  "warnings": []
}
```

**Pinned access paths** (use these in any assertion / scenario):
- `data.licenses` → list of 5 objects, ordered exactly as above
- `data.licenses[].license` / `.package` / `.project_url` / `.source` / `.version` (5 string fields per entry)
- `data.summary` (str) — `"Nove Test redistributes or links to 5 third-party components."`
- `data.notices_reference` (str) — `"NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)"`
- `data.notices_text` — **absent** in default mode
- `schema` (top-level) — `"novetest/v1"` (unchanged additive extension)
- `command` (top-level) — `"licenses"`
- `ok` / `errors` / `warnings` — `true` / `[]` / `[]`

### `novetest licenses --full --output json`

Identical structure to default **plus** `data.notices_text` populated:

```python
e["data"]["notices_text"]  # type: str, length 15573, starts with "# Third-Party Notices"
```

### `novetest licenses --output text` (the pinned `.ambr` snapshot)

```
licenses (5 third-party components)

  runtime dependencies
    cyclopts (>=3.0)                            Apache-2.0
    numpy (>=1.26)                              BSD-3-Clause

  vendored binary
    junit-platform-console-standalone (1.11.4)  EPL-2.0

  install-time bootstrap
    PyApp (0.22.0)                              Apache-2.0 OR MIT
    python-build-standalone (CPython)           PSF + permissive (OpenSSL, libffi, ncurses, etc.)

  full verbatim license texts: novetest licenses --full
  attribution file (in wheel): *.dist-info/licenses/NOTICES.md
```

`--full` text mode appends a blank line, `  --- VERBATIM NOTICES.md ---`,
and the un-indented NOTICES.md body.

## Verification scenarios for Manual Test

Run all commands from the repo root with `unset PYTHONPATH &&` prefix on
this dev host (ROS2 `PYTHONPATH` pollution leaks py3.10 numpy onto py3.11
venv — handoff Gotcha context).

### Scenario A — `novetest licenses --output json` default surface

```bash
unset PYTHONPATH && uv run novetest licenses --output json \
  | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['ok'] is True
assert e['command'] == 'licenses'
assert e['schema'] == 'novetest/v1'
assert e['errors'] == []
assert e['warnings'] == []
assert len(e['data']['licenses']) == 5
assert e['data']['summary'] == 'Nove Test redistributes or links to 5 third-party components.'
assert e['data']['notices_reference'] == 'NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)'
assert 'notices_text' not in e['data']
pkgs = sorted(x['package'] for x in e['data']['licenses'])
assert pkgs == ['PyApp', 'cyclopts', 'junit-platform-console-standalone', 'numpy', 'python-build-standalone']
sources = sorted(set(x['source'] for x in e['data']['licenses']))
assert sources == ['install-time-bootstrap', 'runtime', 'vendored']
print('OK Scenario A')
"
```

**Pass criteria**: `OK Scenario A` printed; exit 0.

### Scenario B — `novetest licenses --full --output json` adds verbatim NOTICES.md

```bash
unset PYTHONPATH && uv run novetest licenses --full --output json \
  | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['ok'] is True
t = e['data']['notices_text']
assert isinstance(t, str)
assert len(t) > 15000
assert t.startswith('# Third-Party Notices')
assert 'Apache' in t
assert 'EPL-2.0' in t
print(f'OK Scenario B (notices_text len={len(t)})')
"
```

**Pass criteria**: `OK Scenario B (notices_text len=15573)` (length may vary
by ≤2 bytes for line-ending edge — anything ≥15000 is acceptable).

### Scenario C — `novetest licenses --output text` (human-readable summary)

```bash
unset PYTHONPATH && uv run novetest licenses --output text
```

**Pass criteria**: Eyeball the output against the snapshot block above.
Five sections grouped by `runtime dependencies` / `vendored binary` /
`install-time bootstrap`. Two footer lines pointing at `--full` and the
in-wheel attribution file.

### Scenario D — `novetest licenses --full --output text` (text mode verbatim append)

```bash
unset PYTHONPATH && uv run novetest licenses --full --output text \
  | grep -E "^  --- VERBATIM NOTICES.md ---$"
```

**Pass criteria**: Exactly one line matching the divider; output not empty.
(The full body of NOTICES.md follows un-indented after the divider.)

### Scenario E — `novetest licenses --help` (cyclopts auto-help)

```bash
unset PYTHONPATH && uv run novetest licenses --help
echo "exit=$?"
```

**Pass criteria**: Cyclopts auto-help text printed; **exit 0** (NOT exit 2
or 1). `--full` flag documented in the options block.

### Scenario F — `_SUBCOMMAND_TOKENS` correctness guard (Gotcha 2 binding)

```bash
unset PYTHONPATH && uv run novetest licenses --output json \
  | python3 -c "
import sys, json
e = json.load(sys.stdin)
assert e['command'] == 'licenses', f'WRONG COMMAND: got {e[\"command\"]!r}; default-verb alias should NOT have rewritten to test'
print('OK Scenario F — command pinned to literal licenses, not test+target')
"
```

**Pass criteria**: `OK Scenario F`. If this fails with
`WRONG COMMAND: 'test'`, the `_SUBCOMMAND_TOKENS` registration in `app.py`
regressed (handoff Gotcha 2).

### Scenario G — drift guard both directions (`const ↔ NOTICES.md`)

```bash
unset PYTHONPATH && uv run pytest -q tests/unit/orchestration/licenses/test_notices_drift_guard.py -v 2>&1 | tail -10
```

**Pass criteria**: 3 tests pass. Asserts `LICENSE_ENTRIES` const and
`NOTICES.md` join cleanly on `project_url` in both directions.

## Critical edge cases worth probing

### 1. `novetest --help` (top-level) does NOT list `licenses` yet

The handoff §"Decisions needed from PM" #1 flagged that
`describe_command_surface()` (the JSON top-level help) does NOT yet
enumerate `licenses`. Adding it forces a regen of the protected
`tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`
which the brief forbade. **Result**: the verb is discoverable via
`novetest licenses --help` (Scenario E above), but **AI agents scanning
`novetest --help` for the top-level command surface will NOT see `licenses`
in the list**. This is a PM-scoped fast-follow cycle (1 `CommandSpec` +
help snapshot regen). Eyeball check Manual Test should run:

```bash
unset PYTHONPATH && uv run novetest --help --output json 2>&1 | head
```

**Expected**: the JSON `data.commands` list (or equivalent surface) does NOT
contain `licenses`. If it DOES, the slice exceeded its declared scope —
flag to PM.

### 2. NOTICES.md drift behavior on a stale editable install

Handoff §"Institutional learning" pinned that
`Distribution.read_text("NOTICES.md")` returns either `None` or a STALE
2054-byte snapshot in an editable install, because PEP 639 stores the file
at `*.dist-info/licenses/NOTICES.md` (the prefix matters) and `pip install
-e` doesn't refresh it on every working-tree edit. The `notices_loader`
mitigates by reading the **source tree FIRST** (walks up from `__file__`
to the first ancestor holding both `pyproject.toml` AND `NOTICES.md`), then
falling back to distribution metadata. **Manual Test corroboration**:

```bash
unset PYTHONPATH && uv run python3 -c "
from novetest.orchestration.licenses.notices_loader import read_notices_text
t = read_notices_text()
print(f'len={len(t)} starts={t[:21]!r}')
"
```

**Expected**: `len=15573 starts='# Third-Party Notices'` (live working-tree
file via source-tree-first path). If you see `len=2054`, the source-tree
walk failed and the loader fell to the stale distribution copy — flag to
orchestration team.

### 3. jest tests host-Node-12 exoneration (NOT slice-introduced)

Post-merge gate showed 3 failures in `tests/integration/run/test_jest_*.py`
+ `tests/integration/coverage/test_jest_coverage.py`. **Exonerated** by:
(a) the slice does NOT touch `src/novetest/run/adapters/jest_adapter.py`
(`git diff 37f7838..2e0925b -- src/novetest/run/adapters/jest_adapter.py`
returns empty); (b) host has Node 12.22.9 vs `node_modules/jest-cli` version
29.7.0 (jest 29 requires Node ≥14); (c) at pre-merge commit `37f7838` the
same tests SKIP in a fresh worktree (no `node_modules`) — they would also
fail in the cached-`node_modules` main worktree at `37f7838`, so the cause
is host state, not commit state. The binding gate is CI on Ubuntu runners
with modern Node (`ci.yml` + `release-test.yml`). Manual Test on a modern-
Node host should see these tests pass cleanly; if they fail there, escalate.

### 4. Data-contract ↔ NOTICES.md display divergence (handoff §"Decisions needed from PM" #2)

The brief said `package` is "as it appears in the NOTICES.md `### <package>`
heading", but the const uses package **ids** that differ from the human
display headings:

| Const `package` (id form) | NOTICES.md `### <heading>` (display form) |
|---|---|
| `junit-platform-console-standalone` | `JUnit Platform Console Standalone (1.11.4)` |
| `python-build-standalone` | `python-build-standalone CPython` (no version paren) |

The drift guard reconciles via the **`project_url` join key** (byte-
identical across both sides for all 5 entries) with normalized/relaxed
license matching. PM-scoped decision: confirm the reconciliation OR scope a
future cycle to realign NOTICES.md headings to SPDX/package-id form. Not a
Manual Test pass/fail criterion — just flag any observed mismatch.

## What wasn't obvious during merge

- **WORKLOG.md conflict resolution** (the only conflict): Release branch
  rebase onto orchestration-merged main hit a WORKLOG.md collision because
  both teams prepended `2026-06-22` entries on top. Resolved by Python
  heredoc script applying the "newest-on-top + `---` divider" convention,
  with **Release entry on top** (handoff filed 10:20) and **orchestration
  entry below** (handoff filed 10:13). Post-resolution: collapsed
  triple-blank-line noise around the new divider via `re.sub`. Both entries
  preserved byte-equivalent.

- **WORKLOG handoff convention**: confirmed for future merges — when two
  teams in a parallel cycle add same-day entries, the one filed LATER goes
  on top (matches "newest-on-top" doc-level convention; handoff timestamps
  serve as the tie-breaker).

- **Empirical validation that v0.1.2 bump and licenses verb compose cleanly**:
  After release slice rebased + merged on top, both surfaces re-verified
  unchanged. The `data.installedVersion` went 0.1.1 → 0.1.2 in the version
  envelope, and `licenses` verb's outputs were byte-identical pre/post
  release bump (no shared state between the two slices' files).
