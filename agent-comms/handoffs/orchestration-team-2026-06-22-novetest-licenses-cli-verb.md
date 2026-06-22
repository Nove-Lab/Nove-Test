---
from: novetest-orchestration-team
to: novetest-main-branch-team
type: handoff
status: ready
created: 2026-06-22
slug: novetest-licenses-cli-verb
branch: orchestration/novetest-licenses-cli-verb
base_commit: 37f7838
related:
  - agent-comms/tasks/orchestration-team-2026-06-22-novetest-licenses-cli-verb.md
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
  - agent-comms/tasks/release-team-2026-06-22-v0.1.2-publication.md
---

# Handoff: `novetest licenses` CLI verb — third-party attribution surface

Worktree `orchestration/novetest-licenses-cli-verb` off `main@37f7838` is
**ready for FF-merge**. Closes Future-cycle queue item #2b; satisfies
decision `2026-06-03-junit-console-launcher-vendor.md §3` (public
attribution surface mandate before any binary-redistribution licensing
audit).

## Commits on the branch (FF-merge both)

| Commit | Slice |
|---|---|
| `61ddd6d` | `cli: novetest licenses verb — third-party attribution envelope` (src + tests + WORKLOG) |
| _(this commit)_ | `comms: orchestration handoff + INDEX for novetest-licenses-cli-verb` |

## Files

| File | Status |
|---|---|
| `src/novetest/orchestration/licenses/__init__.py` | NEW — `LicenseEntry`, `LICENSE_ENTRIES` const, `LicensesView`, `build_licenses_view`, `SUMMARY`/`NOTICES_REFERENCE` |
| `src/novetest/orchestration/licenses/notices_loader.py` | NEW — `read_notices_text()` (source-tree-first, distribution-fallback) |
| `src/novetest/cli/renderers/licenses.py` | NEW — `render_licenses` |
| `src/novetest/cli/renderers/registry.py` | MOD — +import +`"licenses"` key in `_RENDERERS` |
| `src/novetest/cli/app.py` | MOD — `licenses_cmd` handler + `"licenses"` in `_SUBCOMMAND_TOKENS` |
| `tests/unit/orchestration/licenses/{__init__,test_licenses_view,test_notices_drift_guard,test_notices_loader}.py` | NEW — 14 unit tests |
| `tests/unit/cli/renderers/test_licenses.py` + `__snapshots__/test_licenses.ambr` | NEW — 3 renderer tests, 2 snapshots |
| `tests/integration/cli/test_licenses_verb.py` + `__snapshots__/test_licenses_verb.ambr` | NEW — 5 e2e tests, 1 snapshot |
| `WORKLOG.md` | MOD — 2026-06-22 entry prepended |

**Not touched** (deliberate): `src/novetest/cli/output.py` (TEXT routes through
existing `render_text`; JSON/NDJSON byte-frozen), `pyproject.toml`, `NOTICES.md`,
any decision file, any other verb's handler/renderer,
`orchestration/onboarding/command_surface.py` (see PM decision item #1).

## Verification

| Check | Result |
|---|---|
| `uv run mypy --strict src/novetest` | **Success — 112 source files** (109 + 3 new modules) |
| `uv run pytest -q tests/unit tests/integration` | **1327 passed, 3 skipped, 0 failed** (40 snapshots) — +22 new tests, equipped host (no dotnet failure) |
| Byte-identity guard | `git status` shows ONLY new untracked `.ambr` files; ZERO existing snapshot modified; only `app.py` + `registry.py` modified under `src/` |
| Drift guard (both directions) | 3 tests green — const ↔ NOTICES.md joined on `project_url` |

Run all commands with a clean `PYTHONPATH` (this dev host has ROS2 py3.10
workspaces leaking onto `PYTHONPATH` that shadow numpy; prefix `env -u
PYTHONPATH`). This is host pollution, not a slice defect.

## Empirical CLI smoke (verbatim — DoD #2 and #3)

### #2 default `novetest licenses --output json`

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

### #3 `novetest licenses --full --output json` (notices_text truncated for this doc)

Identical to #2 **plus** `data.notices_text`: a **15573-character** UTF-8
string starting `'# Third-Party Notices\n\nNove Test r…'` — the complete
verbatim NOTICES.md body. (`--full` JSON envelope confirmed `ok==True`,
`len(data.notices_text) > 15000`.)

### default `novetest licenses --output text` (the pinned `.ambr` snapshot)

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

`--full` text mode appends a blank line, `  --- VERBATIM NOTICES.md ---`, and
the raw NOTICES.md body (un-indented = truly verbatim).

## Institutional learning — did `Distribution.read_text("NOTICES.md")` work first try?

**No.** Two empirical findings drove the loader design (this is the
load-bearing learning the brief asked for):

1. `Distribution.from_name("novetest").read_text("NOTICES.md")` returns
   **`None`**. PEP 639 embeds the file at `*.dist-info/licenses/NOTICES.md`,
   so the bare name resolves to the unpopulated `*.dist-info/NOTICES.md`. The
   `licenses/`-prefixed name (`read_text("licenses/NOTICES.md")`) does work.
2. Even the working `licenses/`-prefixed read returns a **STALE 2054-byte**
   copy in an editable install — the snapshot from the last `pip install`,
   pre-dating the 2026-06-19 NOTICES expansion. The live working-tree file is
   15.5 KB.

**Resolution:** `notices_loader` tries the **source tree FIRST** (walk up from
`__file__` to the first ancestor holding both `pyproject.toml` and
`NOTICES.md`), then distribution metadata (both `NOTICES.md` and
`licenses/NOTICES.md` candidates), then `LookupError`. Dev/test/CI always read
the live file; a real installed wheel/PyApp binary (no `pyproject.toml`
ancestor) correctly falls to the current dist-info copy. The brief's suggested
distribution-first order would have failed the `--full` length assertions in
this environment. **No `pyproject.toml` change was needed** for either path.

## DoD bullets believed closed (PM verifies + ticks — do NOT tick here)

- **#1** New verb registered — `novetest licenses --help` → cyclopts auto-help, exit 0. ✓
- **#2** Default envelope correct — see §"Empirical CLI smoke" #2 (5 packages, no `notices_text`, `summary`/`notices_reference` pinned, schema `novetest/v1`). ✓
- **#3** `--full` envelope correct — `data.notices_text` = full 15573-char NOTICES.md body. ✓
- **#4** Text mode summary renders — see the pinned snapshot above (5 packages, grouped). ✓
- **#5** Text mode `--full` appends verbatim — integration test asserts `--- VERBATIM NOTICES.md ---` + Apache-2.0 body substring. ✓
- **#6** Drift guard both directions — `test_notices_drift_guard.py` (const→NOTICES + NOTICES→const, joined on `project_url`). ✓
- **#7** mypy --strict GREEN — 112 source files. ✓
- **#8** Full suite GREEN — 1327 passed / 0 failed (≥ baseline + 22). ✓
- **#9** Snapshot pinned — `tests/integration/cli/__snapshots__/test_licenses_verb.ambr` (default text mode). ✓
- **#10** Registry wired — `_RENDERERS["licenses"] = render_licenses`. ✓

## Envelope-schema implications

Compatible additive extension: new keys live under `data` only
(`summary`, `licenses`, `notices_reference`, and `notices_text` when `--full`).
The `schema` string stays `"novetest/v1"`. No schema bump, no `decisions/`
entry required. No existing key modified or renamed. JSON/NDJSON byte shape of
every other verb is untouched (`output.py` not modified).

## Decisions needed from PM (non-blocking — slice is complete + green)

1. **`command_surface` discoverability fast-follow.** `novetest --help`
   (the `describe_command_surface()` JSON listing) does NOT yet enumerate
   `licenses`. Adding the `CommandSpec` would change the help envelope and
   force a regen of `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`
   — which the brief's "Files NOT to touch: existing `.ambr`" forbids — so I
   left it out. The verb works and is discoverable via `novetest licenses
   --help`, but AI agents scanning the top-level command surface won't see it
   until a 1-`CommandSpec` + help-snapshot-regen follow-up. **Recommend PM
   scope it** (trivially small; just snapshot-coupled).

2. **Data-contract ↔ NOTICES.md display divergence** (Gotcha 3). The brief's
   §"Field semantics" prose says `package` is "as it appears in the NOTICES.md
   `### <package>` heading", but the pinned JSON data contract uses package
   *ids* that differ from the human display headings:
   - NOTICES `### JUnit Platform Console Standalone (1.11.4)` vs const id
     `junit-platform-console-standalone`.
   - NOTICES `### python-build-standalone CPython` (no `(version)` paren) vs
     const package `python-build-standalone` + version `CPython`.
   - License bullets carry a `— verbatim text: [...]` suffix; p-b-s license is
     wrapped prose ("Python Software Foundation License plus permissive
     licenses for sub-components (...)") vs const "PSF + permissive (...)".

   I implemented the const **exactly** per the pinned JSON (DoD #2 is strict),
   and the drift guard reconciles via the **`project_url`** join key (byte-
   identical on both sides for all 5 entries) with normalized/relaxed license
   matching. **PM to confirm** this reconciliation is acceptable, or scope a
   future cycle to realign NOTICES.md headings to SPDX/package-id form. Not a
   blocker — the verb + drift guard are green today.

## Deviation from the brief's app.py skeleton (correctness, not scope creep)

`"licenses"` was added to `_SUBCOMMAND_TOKENS` (brief §5 showed only the
command function). Without it, `_inject_default_verb_alias` rewrites
`novetest licenses` → `novetest test licenses` (treats "licenses" as a test
target). The integration test asserting `command == "licenses"` is the
binding guard. Renderer dict placement: `"licenses"` sits after `"replay"`
among the top-level single verbs (the actual `_RENDERERS` dict is logically
grouped, not alphabetical as the brief assumed).

## Parallel cycle / Release coordination

Zero file-footprint overlap with the parallel Release `v0.1.2-publication`
cycle (Release: `pyproject.toml` + `uv.lock` only; this slice: never touches
either). **Merge order: this slice FIRST**, Release rebases its `::version`
bump on top. Release can pick up v0.1.2 immediately after this merges — the
verb does NOT touch `pyproject.toml::version`.
