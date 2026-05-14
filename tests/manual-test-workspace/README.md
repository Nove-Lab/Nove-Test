# Manual Test Workspace

A scratch space for **showing intermediate command results to a human**, not for
automated tests. The user (or an agent on their behalf) copies a fixture project
here, runs commands against it, inspects the on-disk result, then deletes the
folder when done.

Contents are gitignored (see `.gitignore` next to this file); only this README
and the gitignore are tracked.

## When to use this

- "Show me what `novetest init` produces on the pytest-basic fixture."
- "Run X against fixture Y and let me poke at the resulting `.novetest/`."
- Any time the user wants to *see* a side-effect on disk that automated tests
  exercise but don't expose.

Not for: real test cases (those go in `tests/unit/` or `tests/integration/`),
nor for shared fixtures (those live in `tests/fixtures/projects/`, read-only).

## Convention

```
tests/manual-test-workspace/
└── <scenario-slug>/        # one folder per demo, e.g. pytest-basic-init
    └── <fixture-copy>/     # `cp -r` of a fixture from tests/fixtures/projects/
                            # plus whatever the command produced
```

Pick a slug that reads like `<fixture>-<command>`: `pytest-basic-init`,
`pytest-failing-test`, etc.

## Typical flow

```bash
# 1. Copy a fixture
cp -r tests/fixtures/projects/pytest-basic \
      tests/manual-test-workspace/pytest-basic-init/

# 2. Run the command inside the copy
cd tests/manual-test-workspace/pytest-basic-init/pytest-basic
uv run novetest init

# 3. Inspect (open the folder, cat files, etc.)

# 4. Delete when done
rm -rf tests/manual-test-workspace/pytest-basic-init/
```

The fixture under `tests/fixtures/projects/` is never modified — always work
from a copy here.
