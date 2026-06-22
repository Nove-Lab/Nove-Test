---
from: novetest-pm-team
to: all
type: history
created: 2026-06-22
slug: novetest-licenses-cli-verb
cycle_window: 2026-06-22 (single-day; parallel with v0.1.2 publication)
related:
  - agent-comms/decisions/2026-06-03-junit-console-launcher-vendor.md
  - agent-comms/history/2026-06-19-notices-pip-deps-and-perf-bench-bundle.md
  - agent-comms/history/2026-06-18-human-text-renderer-cli-text-mode.md
  - agent-comms/history/2026-06-22-v0.1.2-publication.md  # companion cycle
---

# `novetest licenses` CLI verb — third-party attribution surface

## TL;DR

Nove Test now ships a `novetest licenses` top-level CLI verb that
enumerates all third-party components Nove Test redistributes or links
to as a `novetest/v1` envelope (5 entries: cyclopts, numpy, JUnit
Platform Console Standalone, PyApp, python-build-standalone). With
`--full`, the envelope additionally inlines the verbatim 15.5 KB
NOTICES.md body so AI agents and legal-audit tooling have a single,
byte-stable attribution surface.

**Closes Future-cycle queue item #2b** — the named Wave 2 follow-up
from the 2026-06-19 NOTICES expansion cycle. Satisfies decision
`2026-06-03-junit-console-launcher-vendor.md §3` (public attribution
surface mandate before any binary-redistribution licensing audit).

Manual Test verdict: **PASSED** — 7/7 scenarios + 4/4 critical edge
cases green; CI matrix (`ci.yml` run `27933604837` at merged HEAD
`438eb71`) shows 10/10 jobs SUCCESS across Ubuntu / macOS / Windows ×
Python 3.11 / 3.12 / 3.13.

## Cycle arc (single day, parallel with v0.1.2 publication)

| Event | Commit |
|---|---|
| PM parallel dispatch | `37f7838` |
| Orchestration code slice | `61ddd6d` |
| Orchestration handoff + INDEX | `2e0925b` |
| Main Branch verification routing | `03f2721` |
| Manual Test PASSED findings filed | _(at cycle close)_ |
| PM cycle-close (this entry + companion v0.1.2 history + release-notes + README + transient cleanup) | _(this commit)_ |

## What landed

### Source changes (5 files; 3 NEW, 2 MOD)

| File | Change |
|---|---|
| `src/novetest/orchestration/licenses/__init__.py` | NEW — `LicenseEntry` dataclass, `LICENSE_ENTRIES` static const list of 5 entries, `LicensesView`, `build_licenses_view()`, pinned `SUMMARY`/`NOTICES_REFERENCE` strings |
| `src/novetest/orchestration/licenses/notices_loader.py` | NEW — `read_notices_text()` source-tree-first walker, falls through to `importlib.metadata.Distribution.read_text` candidates, then `LookupError` |
| `src/novetest/cli/renderers/licenses.py` | NEW — `render_licenses()` text renderer (grouped by source: runtime / vendored / install-time-bootstrap) |
| `src/novetest/cli/renderers/registry.py` | MOD — `+import render_licenses`, `+"licenses": render_licenses` in `_RENDERERS` |
| `src/novetest/cli/app.py` | MOD — `licenses_cmd` handler with `--full` flag, `"licenses"` added to `_SUBCOMMAND_TOKENS` (load-bearing — see learning #3) |

### Test changes (8 files NEW; 22 new tests + 3 snapshots)

- `tests/unit/orchestration/licenses/{test_licenses_view, test_notices_drift_guard, test_notices_loader}.py` — 14 unit tests
- `tests/unit/cli/renderers/test_licenses.py` + 2 snapshots
- `tests/integration/cli/test_licenses_verb.py` + 1 snapshot

### Empirical CI evidence

`ci.yml` run `27933604837` at merged HEAD `438eb71` — **10/10 jobs SUCCESS**:

| Cell | Conclusion |
|---|---|
| Ubuntu × Py 3.11 | success |
| Ubuntu × Py 3.12 | success |
| Ubuntu × Py 3.13 | success |
| macOS × Py 3.11 | success |
| macOS × Py 3.12 | success |
| macOS × Py 3.13 | success |
| Windows × Py 3.11 | success |
| Windows × Py 3.12 | success |
| Windows × Py 3.13 | success |
| perf | success |

### Verbatim envelope (default `--output json`)

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

`--full` mode appends a 15573-byte `data.notices_text` string starting
`'# Third-Party Notices'` — the complete verbatim NOTICES.md body.

## Load-bearing learnings (4)

### 1. `Distribution.read_text("NOTICES.md")` returns `None` under PEP 639 — source-tree-first is the correct inversion

The brief recommended `Distribution.from_name("novetest").read_text("NOTICES.md")` as the preferred resource-loading mechanism. Empirically this returns **`None`** — PEP 639 stores the file at `*.dist-info/licenses/NOTICES.md` (note the `licenses/` prefix), and the bare name resolves to the unpopulated `*.dist-info/NOTICES.md`.

Worse, even the prefix-correct `read_text("licenses/NOTICES.md")` returns a **STALE 2,054-byte copy** in an editable install — the snapshot from the last `pip install`, pre-dating any subsequent `NOTICES.md` edit on disk.

**Resolution adopted**: `notices_loader.read_notices_text()` tries the **source tree FIRST** (walks up from `__file__` to the first ancestor holding both `pyproject.toml` AND `NOTICES.md`), then falls through to dist-info candidates (both `NOTICES.md` and `licenses/NOTICES.md`), then `LookupError`. Dev/test/CI always read the live working-tree file; an installed PyApp binary (no `pyproject.toml` ancestor) correctly falls to the current dist-info copy.

**Implication for future resource loaders**: never assume `Distribution.read_text(<bare-name>)` works for license / attribution files. The `licenses/`-prefix is load-bearing; the source-tree fallback is load-bearing for editable installs. Pin both.

### 2. Bidirectional drift guard via `project_url` join key — id-form const + display-form NOTICES.md, joined on URLs

The brief said `package` is "as it appears in the NOTICES.md `### <package>` heading". Empirically NOTICES.md uses **human display form** (`### JUnit Platform Console Standalone (1.11.4)`, `### python-build-standalone CPython` with no version paren) while the pinned JSON data contract uses **id form** (`junit-platform-console-standalone`, `python-build-standalone` + separate `"CPython"` version field).

The drift guard reconciles via the `project_url` join key — URLs are byte-identical on both sides for all 5 entries — with normalized/relaxed license matching (treats `Apache-2.0` and `Apache 2.0` as equivalent).

**Pattern reusable for any future static-const-mirroring-a-doc surface**:
- Const uses tooling-friendly form (SPDX ids, machine-parseable versions, normalized fields).
- Doc uses human-readable form (display names, marketing copy, prose explanations).
- Join key = URL or some other byte-stable identifier present in both surfaces.
- Test asserts bidirectional cover (every const entry has a doc section AND every doc section has a const entry).

This pattern lets both audiences (tooling and humans) keep their preferred form without forcing either to compromise.

### 3. `_SUBCOMMAND_TOKENS` registration is required for every new top-level verb

A non-obvious foot-gun: without `"licenses"` in `_SUBCOMMAND_TOKENS` (`src/novetest/cli/app.py`, line 92), the `_inject_default_verb_alias` pre-Cyclopts pre-processor silently rewrites `novetest licenses` → `novetest test licenses` (treats "licenses" as a test target).

The brief's app.py skeleton showed the command function but did NOT mention the token-set entry. Orchestration team caught this during integration and surfaced it as a deviation.

**Implication for every future top-level verb addition**: the addition is TWO lines, not one:
1. The `@app.command` handler function.
2. The `"<verb>"` entry in `_SUBCOMMAND_TOKENS` (immediately adjacent to where Cyclopts registers the verb).

Scenario F in the verification doc empirically pins this — asserts `envelope.command == "licenses"` (NOT silently rewritten to `"test"`). Adopt this assertion pattern as a regression guard template for every future verb addition.

### 4. The verb is functional but NOT auto-discoverable via top-level `novetest --help` — a fast-follow cycle is needed

`describe_command_surface()` (the JSON structure backing `novetest --help --output json`'s `data.operating` list) currently enumerates 14 commands. `licenses` is the 15th-but-absent — adding the `CommandSpec` requires regenerating the protected snapshot `tests/integration/cli/__snapshots__/test_help_envelope_no_store.ambr`, which the brief explicitly forbade ("Existing snapshot files (`*.ambr`) — except your new `test_licenses_verb.ambr`").

Net effect: the verb is fully discoverable via `novetest licenses --help` (Cyclopts auto-help, exit 0), but **AI agents scanning the top-level command surface programmatically will NOT see `licenses` in the enumerated list** until a 1-`CommandSpec` + 1-snapshot-regen fast-follow cycle lands.

**Follow-up cycle**: minimal scope (~1 hour wall). Add `CommandSpec(name="licenses", ...)` to `command_surface.py`, regen `test_help_envelope_no_store.ambr` via `pytest --snapshot-update`, commit as `cli: enumerate licenses verb in top-level command surface`. Surfaced as next-cycle candidate; CEO to decide sequencing.

## Future-cycle queue impact

- **#2b `novetest --licenses` CLI verb** ← **CLOSED** by this cycle (verb operational; envelope contract pinned; drift guard CI-tested in both directions; `ci.yml` 10/10 on merged HEAD).

Remaining open queue items:
- **#10 `novetest workspaces test` orchestrator** — optional, gated on user feedback per 2026-06-09 disposition.

**Carry surfaced this cycle (not in original queue)**:
- Top-level command surface enumeration for `licenses` (Nit #1 from Manual Test findings) — minimal fast-follow cycle.

## Cycle transcript (commits)

- `37f7838` — PM: parallel dispatch (licenses verb + v0.1.2 publication)
- `61ddd6d` — Orchestration: `cli: novetest licenses verb — third-party attribution envelope`
- `2e0925b` — Orchestration: handoff for novetest-licenses-cli-verb
- `a460c96` — Release: `bump version to 0.1.2 (Path A 1-line)` (companion cycle)
- `cc47132` — Release: handoff for v0.1.2 publication (companion cycle)
- `5519ccf` — Release: amend handoff + WORKLOG with resolved push state (companion cycle)
- `03f2721` — Main Branch: verification routing (licenses verb)
- `438eb71` — Main Branch: verification routing (v0.1.2 publication; companion cycle)
- _(this commit)_ — PM: cycle-close (this history + companion v0.1.2 history + release-notes + README badge/Status + transient cleanup + INDEX regen)

## Closure

The third-party attribution surface mandated by decision `2026-06-03-junit-console-launcher-vendor.md §3` is now publicly discharged via the CLI. Apache 2.0 §4(d) attribution requirements are user-discoverable in one command (`novetest licenses --full`). Future-cycle queue #2b — the last named Wave 2 follow-up from the 2026-06-09 MVP release-ready sign-off — is operationally closed.

**Companion entry**: `2026-06-22-v0.1.2-publication.md` carries the version-bump mechanics; both slices compose cleanly on the same merged HEAD.

The next natural follow-up is the top-level command-surface enumeration cycle (Nit #1 — ~1 hour scope, atomic 1-commit). CEO to sequence at next session.
