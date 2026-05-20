# jest-basic-coverage

Jest-based fixture project used by Nove Test to validate the Run engine's
**coverage-emission path** for the JavaScript / TypeScript ecosystem.
Parallel to `pytest-coverage` for the Python ecosystem.

## What this fixture validates

- The jest adapter, invoked with `collect_coverage=True`, must emit
  `native/coverage/coverage-final.json` — Istanbul's raw JSON coverage
  format — and register it in `NativeResult.artifact_paths` under the
  `coverage_json` key.
- `coverage-final.json` is a map keyed by **absolute** source file path;
  each entry carries `statementMap` / `fnMap` / `branchMap` plus the
  `s` / `f` / `b` hit counters. The Coverage engine's Istanbul parser
  converts the absolute paths to workspace-relative.
- `src/classifier.js`'s third branch (`value < 0`) is **not** exercised
  by the test suite, so the Istanbul report carries a concrete uncovered
  region — proof for the Coverage engine that the artifact carries the
  uncovered-branch evidence it needs (`mapping_granularity: per-test-file`
  / degraded, since Istanbul does not tag coverage by individual test).

## The deliberate gap

`src/classifier.js`'s `classify(value)` has three branches: positive,
zero, negative. The test suite covers only positive and zero. The
negative branch is the fixture's contract — **do not "fix" the test
suite by adding a negative-value test**.

## Expected test outcomes

| Test | Status |
| --- | --- |
| `positive values are classified as positive` | passed |
| `zero is classified as zero` | passed |

(No failing tests — coverage gaps are the fixture's only signal.)

## Layout

```
jest-basic-coverage/
├── package.json              # jest in devDependencies; "test": "jest"
├── src/
│   └── classifier.js         # three branches, one intentionally uncovered
└── __tests__/
    └── classifier.test.js    # 2 passing tests covering 2 of 3 branches
```

## One-time setup before `novetest run`

```sh
cd tests/fixtures/projects/jest-basic-coverage
npm install --no-audit --no-fund
```

`node_modules/` is intentionally **not** checked in (it's huge and
platform-specific). The local `.gitignore` excludes it so a local
`npm install` here does not pollute the index.

## Isolation

The fixture's `package.json` is self-contained — it does not import any
`novetest` code. Jest is invoked via `npx jest` from the adapter with
`cwd=` this directory. The adapter passes `--coverageDirectory` so the
Istanbul report lands under the per-run artifact directory, never the
fixture's own tree.
