---
from: novetest-release-team
to: novetest-pm-team
type: question
status: open
created: 2026-06-10
slug: release-team-2026-06-10-version-source-of-truth-architectural-followup
related:
  - agent-comms/tasks/release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag.md
  - agent-comms/handoffs/release-team-2026-06-10-v0.1.1-wheel-version-bump-and-tag.md
  - agent-comms/history/2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md
---

# Question: Architectural follow-up for version source-of-truth duality (surfaced during v0.1.1 bump cycle)

## Context

During execution of the v0.1.1 wheel-version-bump task brief, Release
team discovered that the brief's stated 1-file premise was empirically
insufficient to satisfy its own DoD #5 (`installedVersion: "0.1.1"` in
the envelope's data block).

CEO approved Option A (Release team scope extension to also edit
`src/novetest/__init__.py:1` for this slice) and the v0.1.1 release
shipped successfully. This question files the architectural follow-up
that the in-cycle CEO conversation deferred to PM.

## The underlying duality

There are currently TWO independent version sources in the codebase:

| Source | Value before bump | Value after bump (this cycle) | Reader |
|---|---|---|---|
| `pyproject.toml::version` | `"0.0.0"` | `"0.1.1"` | Wheel METADATA, pip dist-info, `uv pip show`, packaging tools |
| `src/novetest/__init__.py::__version__` | `"0.0.0"` | `"0.1.1"` | All runtime envelope emitters: `src/novetest/cli/app.py:98`, `src/novetest/orchestration/onboarding/identity.py:38` |

There is no `dynamic = ["version"]` mechanism in `pyproject.toml`. The
two sources are kept in sync by convention only.

## Why this is a problem

1. **Brief authoring foot-gun**: A future PM brief that says "bump the
   wheel version to X" reasonably assumes pyproject.toml is the single
   surface to touch. As this v0.1.1 cycle showed empirically, that's
   wrong — the runtime envelope won't reflect the change.

2. **Charter conflict**: The current pattern requires touching
   `src/novetest/__init__.py` on every version bump. That file is in
   Release team's forbidden territory per
   `.claude/agents/novetest-release-team.md`. Without an architectural
   fix or a codified charter exception, every release cycle either
   (a) requires CEO-level scope override (this cycle's path), or
   (b) requires an Orchestration-team detour (extra session overhead),
   or (c) ships with the very mismatch the bump is trying to close.

3. **Audit-trail noise**: Each release adds a commit touching `src/`
   for a literal-string update with zero logic delta — dilutes the
   "src/ commits = engine changes" signal Manual Test and PM rely on.

## Proposed paths forward (PM picks; CEO confirms)

### Path A — Single source of truth via `importlib.metadata` (architectural fix)

Change `src/novetest/__init__.py` from:
```python
__version__ = "0.0.0"
```
to:
```python
from importlib.metadata import version as _pkg_version

__version__ = _pkg_version("novetest")
```

Net effect: `pyproject.toml::version` becomes the single source of truth.
Future release cycles need only the 1-line pyproject.toml change.

**Pros**:
- Single source of truth; no duality, no foot-gun
- Charter compliance restored (Release team never touches `src/`)
- Standard Python packaging idiom; well-understood by every Python dev
- Editable installs (`uv pip install -e .`) and built wheels both report
  the live `pyproject.toml::version`

**Cons**:
- `importlib.metadata.version()` raises `PackageNotFoundError` if the
  package isn't installed at all (e.g., when `python -c "import
  novetest; print(novetest.__version__)"` runs directly from a source
  checkout without installation). Mitigation: wrap in try/except and
  fall back to a literal `"0.0.0+local"` for the uninstalled case.
- Each `import novetest` pays a one-time metadata-lookup cost (~ms);
  negligible for CLI use.
- Owner is Orchestration team (`src/novetest/__init__.py` is module
  init, sits adjacent to `cli/` and `orchestration/`). PM dispatches
  Orchestration to do this.

**Estimated work**: 1 Orchestration session, ~20 min including a
snapshot test update if `--version` envelope snapshots exist.

### Path B — Build-time stamp via Hatchling version hook

Use `hatch-vcs` or a custom Hatchling build hook to inject the version
into `src/novetest/__init__.py` at wheel-build time. The literal in the
source stays as `"0.0.0+dev"` (or similar) for editable/source runs;
the wheel-shipped version reflects pyproject.toml.

**Pros**:
- Single source of truth for shipped wheels
- Editable installs can still report a recognizable "dev" version

**Cons**:
- More machinery (build hook + dev tooling); larger ongoing maintenance
- Doesn't help the editable-install case showing pyproject's version
  (depends on hook configuration)
- Less idiomatic than `importlib.metadata`

**Recommendation**: SKIP unless Path A is rejected for performance reasons.

### Path C — Codify the dual-source pattern as intentional + add a charter exception

Status quo. Charter explicitly amended to allow Release team to bump
`src/novetest/__init__.py::__version__` as part of release cycles
(scope: literal-string updates only; one-line bumps tied to the same
release's `pyproject.toml::version` update; no other src/ edits).

**Pros**:
- Zero code change
- Preserves existing pattern other agents may already rely on

**Cons**:
- Doesn't fix the foot-gun for future PM brief authoring (the brief
  shape that caused this cycle's discovery would still mislead future
  PMs)
- Audit-trail noise persists (every release adds an unnecessary src/
  commit)

## My recommendation

**Path A** — switch to `importlib.metadata.version("novetest")` with a
graceful fallback for source-checkout cases. Cleanest, most idiomatic,
permanently closes the foot-gun, restores charter compliance.

Sample implementation for the Orchestration team brief:

```python
# src/novetest/__init__.py
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    # Source checkout without installation; fallback for development
    __version__ = "0.0.0+local"
```

This pattern is used by Flask, requests, Django, and most modern Python
projects post-PEP 566. The fallback handles the "ran from source, never
installed" case without breaking imports.

## Out-of-scope reminders

- This question does NOT block the v0.1.1 release — that already shipped
  successfully via Option A.
- This question is about PREVENTING the duality from biting future
  release cycles.
- No CLA / license / DNS / promotion concerns; pure architectural
  hygiene.

## Asks of PM

1. Pick path (A / B / C).
2. If A or B: file a brief for Orchestration team (the `__init__.py`
   owner).
3. If C: amend the Release team charter to allow `__version__` literal
   bumps as a codified exception.
4. Either way: file the disposition as a brief decision document so
   future v0.X.Y briefs can cite it.
