---
from: novetest-pm-team
to: all
type: decision
status: resolved
created: 2026-06-10
slug: version-source-of-truth-via-importlib-metadata
related:
  - agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md
  - agent-comms/history/2026-06-10-v0.1.0-inaugural-release-and-apache-2.0-license-adoption.md
---

# Decision: `pyproject.toml::version` is the single source of truth; `__version__` resolves dynamically via importlib.metadata

CEO-approved on 2026-06-10.

## Decision

`src/novetest/__init__.py` migrates from the hardcoded literal pattern:

```python
__version__ = "X.Y.Z"
```

to dynamic resolution via Python's standard `importlib.metadata`:

```python
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
```

**Effect**: `pyproject.toml::version` becomes the single source of truth for the version string at every layer (wheel METADATA, runtime envelope, packaging tools, PyPI metadata). Future release cycles' version-bump briefs become exactly 1 line — `pyproject.toml::version` edit only.

The fallback `"0.0.0+local"` handles the "source-checkout, never installed" case (e.g., a developer running `python -c "import novetest; print(novetest.__version__)"` from a fresh clone without `uv pip install -e .`). The `+local` suffix is a PEP 440 local-version identifier that clearly signals "uninstalled development state".

## Rationale

The v0.1.1 release cycle (history `2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md`) empirically surfaced that the codebase carried TWO independent version sources:

| Source | Reader |
|---|---|
| `pyproject.toml::version` | Wheel METADATA, pip dist-info, `uv pip show`, packaging tools |
| `src/novetest/__init__.py::__version__` (hardcoded literal) | Runtime envelope emitters: `src/novetest/cli/app.py:98`, `src/novetest/orchestration/onboarding/identity.py:38` |

Kept in sync by convention only. No `dynamic = ["version"]` mechanism in `pyproject.toml`. This duality is the foot-gun:

1. **PM brief authoring**: a brief saying "bump the version to X" reasonably assumes pyproject.toml is the single surface to touch. Empirically wrong — the runtime envelope won't reflect the change without a parallel `__init__.py` edit.
2. **Charter conflict**: every version bump touches `src/novetest/__init__.py` which is in Release team's forbidden territory. Each release cycle requires either CEO scope override, Orchestration team detour, or shipping the mismatch.
3. **Audit-trail noise**: every release adds a `src/` commit for a literal-string update with zero logic delta — dilutes the "src/ commits = engine changes" signal Manual Test and PM rely on.

The Path A pattern (`importlib.metadata.version()`) is the standard Python idiom post-PEP 566, used by Flask, Django, requests, urllib3, and most modern Python projects. It is taught as the canonical "single source of truth for package version" pattern in PyPA documentation.

**Why NOT Path B** (Hatchling build hook injection): more machinery, ongoing maintenance burden, less idiomatic, doesn't help editable-install case.

**Why NOT Path C** (codify duality as intentional + Release charter exception): doesn't fix the foot-gun for future PM briefs; audit-trail noise persists. Status quo is the worst option.

## What this decision rules in

- Future version-bump cycles are exactly 1 line: `pyproject.toml::version`. Release team never touches `src/`.
- The `__version__` attribute remains accessible via `novetest.__version__` for any downstream code that imports it — semantic compatibility preserved.
- Editable installs (`uv pip install -e .`) report the live `pyproject.toml::version` at runtime — standard Python behavior.
- The runtime envelope's `installedVersion` field continues to reflect `__version__` — no envelope schema change.

## What this decision rules out

- Custom version-string parsing logic in `__init__.py` (e.g., reading a `VERSION` text file, git tag inspection) — unnecessary complexity.
- Caching the resolved version in a module-level constant beyond the import-time lookup — the `importlib.metadata.version()` call already memoizes inside `importlib.metadata`'s machinery.
- Removing `__version__` entirely (e.g., forcing downstream code to call `importlib.metadata.version("novetest")` directly) — would break semantic compatibility for any external code that imports `novetest.__version__`.

## Implementation pattern (canonical)

```python
# src/novetest/__init__.py
"""Nove Test - AI-first testing orchestration."""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("novetest")
except PackageNotFoundError:
    # Source checkout without installation; fallback for development.
    # The `+local` suffix is a PEP 440 local-version identifier that
    # clearly signals "uninstalled development state".
    __version__ = "0.0.0+local"
```

The 4-line pattern is the entire change to `__init__.py`. No other file modifications required.

**Snapshot test impact**: any test snapshot that captures the `--version --output json` envelope's `installedVersion` field must still pass (the resolved value will be byte-identical to the pre-migration hardcoded literal when the package is installed). If a snapshot has been previously regenerated with `__version__ = "X.Y.Z"`, no regeneration needed post-migration as long as the test is run from a properly-installed package state.

## Affected files / teams

This decision triggers a single Orchestration-team follow-up cycle that:

1. Modifies `src/novetest/__init__.py` per the canonical pattern above.
2. Runs `uv run novetest --version --output json` to confirm `installedVersion` still resolves correctly.
3. (If snapshot tests exist for the version envelope) verifies snapshots pass without regeneration.
4. WORKLOG + handoff + INDEX regen per standard.

Brief at `agent-comms/tasks/orchestration-team-2026-06-10-version-source-of-truth-importlib-metadata-migration.md`.

## Non-binding follow-ups

None. This is a complete architectural close.

## Effective date

2026-06-10. Becomes operationally effective when Orchestration team's follow-up cycle merges.

## Supersedes

Closes the implicit "two-source duality" pattern in the codebase. Resolves the architectural follow-up question filed at `agent-comms/questions/release-team-2026-06-10-version-source-of-truth-architectural-followup.md` (deleted in cycle-close transient cleanup; the disposition lives here permanently).

## Future amendments anticipated

None anticipated. The pattern is well-established and unlikely to require revision.
