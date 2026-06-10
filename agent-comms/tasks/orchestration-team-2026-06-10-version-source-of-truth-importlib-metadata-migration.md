---
from: novetest-pm-team
to: novetest-orchestration-team
type: task
status: pending
created: 2026-06-10
slug: orchestration-team-2026-06-10-version-source-of-truth-importlib-metadata-migration
related:
  - agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md
  - agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md
---

# Orchestration team task: migrate `src/novetest/__init__.py::__version__` to `importlib.metadata.version()`

## Mission

Close the version source-of-truth duality surfaced by the v0.1.1 release
cycle. `pyproject.toml::version` becomes the single source of truth;
`__version__` resolves dynamically via Python's standard
`importlib.metadata` at import time.

After this slice merges, future Release-team version-bump cycles are
exactly 1 line (`pyproject.toml::version` only). Release team never
touches `src/` again for version bumps.

**This is the architectural close of the foot-gun documented in the
v0.1.1 cycle. Single file edit. Estimated ~20 minutes including local
verification.**

## Pre-flight reading

1. `agent-comms/decisions/2026-06-10-version-source-of-truth-via-importlib-metadata.md` — the binding decision (read first; this brief is just operational)
2. `agent-comms/history/2026-06-10-v0.1.1-first-public-release-and-version-source-of-truth-followup.md` §"Load-bearing learnings / Item 1" — context on why this matters
3. Current `src/novetest/__init__.py` — the file you're editing
4. `src/novetest/cli/app.py` (around line 98) and `src/novetest/orchestration/onboarding/identity.py` (around line 38) — the readers of `__version__`; do NOT modify these, but understand the read pattern

## File to modify (ONE)

### `src/novetest/__init__.py`

Current shape (1 line + likely a module docstring):

```python
"""Nove Test - AI-first testing orchestration."""

__version__ = "0.1.1"
```

Replace with:

```python
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

That is the ENTIRE source change. No other file modifications required.

Preserve whatever module docstring or other content was present before
the `__version__` line. The `import` lines go between the docstring and
the `__version__` assignment.

If the current file has additional imports, top-level constants, or
package-init logic, preserve all of it — only the `__version__` literal
assignment is being replaced.

## Verification (local; cite all outputs in handoff)

```sh
# 1. Type-check stays clean (93 src files expected baseline)
uv run mypy --strict src/novetest
# Expected: Success: no issues found in 93 source files

# 2. Test suite baseline maintained
uv run pytest -q tests/unit tests/integration
# Expected: identical pass/skip/fail counts vs pre-edit baseline.
# If `tests/integration/cli/test_envelope_snapshots.py` (or similar
# snapshot test for --version envelope) exists, it MUST pass without
# snapshot regeneration — the resolved __version__ is byte-identical
# to the pre-migration hardcoded literal when the package is installed.

# 3. The CLI envelope still reports the correct version
uv run novetest --version --output json
# Expected: "installedVersion": "0.1.1"  (or whatever pyproject.toml::version is at HEAD)
# The resolved value is read from package METADATA at runtime;
# matches pyproject.toml byte-for-byte for installed packages.

# 4. The fallback path is reachable in source-checkout-only state
python3 -c "
import sys
# Simulate the 'package not installed' state by manipulating sys.path
# to ensure novetest imports from src/ not from installed dist-info.
# (The actual fallback behavior is environment-dependent; this is
# just a sanity check that the import works in a worst-case scenario.)
sys.path.insert(0, 'src')
from novetest import __version__
print(f'__version__ = {__version__}')
"
# Expected: prints either "0.1.1" (if the package IS installed and
# its METADATA is found via sys.path lookup) OR "0.0.0+local"
# (if metadata is not found). Both outcomes are correct behavior.
# Cite whichever observed.
```

If verification step 2 surfaces a snapshot test failure that CANNOT
be resolved without regeneration, surface as a question — do NOT
auto-regenerate. Snapshot regeneration would mask a real semantic
shift if one exists.

## Out of scope (explicitly NOT this slice)

- `pyproject.toml::version` change — value stays at current `"0.1.1"`. The whole point of this migration is to NOT touch it.
- Any other `src/novetest/**` files. Only `__init__.py` literal-assignment line is touched.
- Snapshot test regeneration. If snapshots fail, surface a question instead.
- Release-test workflow changes. The wheel METADATA already carries the version; nothing changes from the build pipeline's perspective.
- New `git tag` push. This slice does not warrant a new release tag — it's pure internal refactoring with zero user-observable behavior change.
- THIRD_PARTY_NOTICES updates. `importlib.metadata` is part of Python's standard library (added in 3.8); no new dependency, no notice.

## Definition of done

8 bullets:

1. [ ] `src/novetest/__init__.py` edited per the canonical pattern above (try/except with PEP-440 fallback)
2. [ ] `uv run mypy --strict src/novetest` clean (93 source files unchanged)
3. [ ] `uv run pytest -q tests/unit tests/integration` baseline maintained (same pass/skip/fail counts)
4. [ ] `uv run novetest --version --output json` returns the SAME `installedVersion` value as pre-edit (cite both pre- and post-edit envelopes for confirmation)
5. [ ] (If snapshot tests exist for --version envelope) all pass without regeneration
6. [ ] Fallback path empirically reachable per verification step #4 (cite output)
7. [ ] WORKLOG entry per format
8. [ ] Handoff at `agent-comms/handoffs/orchestration-team-2026-06-10-version-source-of-truth-importlib-metadata-migration.md` with DoD bullets-believed-closed list
9. [ ] `python3 tools/regen_comms_index.py`

## Procedural posture

Standard 4-stage flow expected: Orchestration -> Main Branch FF-merge ->
Manual Test verification -> PM cycle-close. This slice is small and
low-risk, so 일괄 self-merge IS authorized per the same precedent the
v0.1.0 and v0.1.1 cycles established. CEO's dispatch will indicate.

## Failure modes to anticipate (PM-pinned)

1. **`importlib.metadata.version("novetest")` raises `PackageNotFoundError` even when the package IS installed** — usually indicates an editable-install metadata gap. Resolution: run `uv pip install --force-reinstall -e .` to rebuild the egg-info / dist-info. Surface in a question if force-reinstall doesn't fix it.

2. **`mypy --strict` complains about the `_pkg_version` alias or the try/except scope** — Python's standard library is fully typed via stubs. If mypy fails, the import or alias is wrong; fix per the canonical pattern verbatim.

3. **Snapshot test fails with `installedVersion` field byte difference** — should NOT happen if the package is installed and the pyproject version matches. If it does, surface a question — do NOT regenerate.

4. **The fallback `"0.0.0+local"` shows up in production** — would indicate the binary or wheel install lost its dist-info METADATA. Strong signal of a packaging defect; PM-route as a Release-team concern.

## Handoff "DoD bullets believed closed" list (template)

```markdown
## DoD bullets believed closed — PM to verify and tick

This slice closes:
- Architectural duality between pyproject.toml::version and src/novetest/__init__.py::__version__ (resolves decision 2026-06-10-version-source-of-truth-via-importlib-metadata.md)
- Future Release-team version-bump charter conflict (now all bumps are 1-line pyproject.toml edits)

No Phase 0 DoD tick changes (this is internal architecture, not user-facing surface).
```

## Cycle close direction

After Manual Test verifies + PM cycle-closes:
- Future v0.1.2+ release cycles use the 1-line pyproject.toml bump pattern only
- PM may note in the cycle-close history that Path A is operationally live
- No follow-up architecture work needed for version handling

## Reporting back (in handoff)

- Worktree path / branch / commit SHA
- Verbatim diff of `src/novetest/__init__.py` (the entire file before + after, since the file is small)
- All verification command outputs (mypy, pytest, --version envelope BEFORE and AFTER, fallback path probe)
- WORKLOG entry text
- Confirmation that no `pyproject.toml` change was made
- Confirmation that no other `src/novetest/**` file was touched
- Any surprises (e.g., snapshot test interactions, mypy edge cases)
