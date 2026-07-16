# jest-basic

Minimal jest-based fixture project used by Nove Test as software under test.
Parallel to `pytest-basic` for the JavaScript / TypeScript ecosystem.

## What this fixture validates

A clean happy-path Run loop with the jest Native Engine:

- `probe_engine(<this dir>, "javascript-typescript", "jest")` should classify
  this workspace as `ready` once
  `node` is on `PATH` AND `node_modules/.bin/jest` is present (i.e. after
  a one-time `npm install`). Before `npm install` lands, readiness is
  `engine-misconfigured` (jest declared in `package.json` but not installed
  on disk) — that is the expected first-run state.
- `novetest run __tests__/` should succeed: 3 passing tests, no failures.
- A Run Record should be persisted with a stable Run Reference and the
  captured `jest-results.json` + stdout/stderr logs under
  `.novetest/run/artifacts/.../native/`.

## Layout

```
jest-basic/
├── package.json           # jest in devDependencies; "test": "jest"
├── src/
│   └── math.js            # add, subtract
└── __tests__/
    └── math.test.js       # 3 passing tests
```

## One-time setup before `novetest run`

```sh
cd tests/fixtures/projects/jest-basic
npm install --no-audit --no-fund
```

`node_modules/` is intentionally **not** checked in (it's huge and platform-
specific). The repo-level `.gitignore` excludes any `node_modules/` so a
local `npm install` here does not pollute the index.

## Isolation

The fixture's `package.json` is self-contained — it does not import any
`novetest` code. Jest is invoked via `npx jest` from the adapter with
`cwd=` this directory so the user-project's own jest config (none, in this
fixture) is the only config in scope. Unlike pytest, jest has no
`PLUGIN_AUTOLOAD` concept; isolation is purely workspace-local.
