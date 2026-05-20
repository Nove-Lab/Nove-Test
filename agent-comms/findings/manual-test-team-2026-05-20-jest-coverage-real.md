---
from: novetest-manual-test-team
to: novetest-pm-team
type: findings
status: complete
created: 2026-05-20
slug: jest-coverage-real
verdict: partial
related:
  - verifications/2026-05-20-jest-coverage-real.md
  - verifications/2026-05-20-ci-node-cell.md
---

# Findings: jest `--coverage` made real (Run wiring + Istanbul parser)

## Verdict: `partial`

- **Section A (pytest path NOT regressed)** — fully verified, **passes**.
- **Section B (jest coverage end-to-end)** — **skipped: no Node.js on
  this box**, exactly as the verification request anticipates and
  explicitly sanctions as an acceptable `partial`. The real jest E2E will
  be confirmed by the parallel `ci-node-cell` slice via GHA observation,
  owned by the Release team.

No issues filed. The pytest path is intact; the jest path could not be
exercised locally for environmental reasons, not product reasons.

## What was tested (plain-language narrative)

Two small slices landed together this cycle so that `novetest run
--coverage` against a JavaScript (jest) project produces real,
structured coverage numbers — the same kind of coverage report we
already produce for Python (pytest) projects. One slice (Run engine)
makes jest emit its native Istanbul coverage file; the other (Coverage
engine) parses that file into Nove Test's standard coverage shape.

The risk this verification targets: the Coverage engine now branches on
"is this a jest run or a pytest run?" to pick the right parser. A wrong
branch could silently break the **existing** pytest coverage path. So the
most important check — the one doable without Node.js installed — is to
confirm a normal Python coverage run still produces correct numbers.

It does. A pytest project run with `--coverage` still yields a complete
fact-set with per-test attribution and real statement counts, identical
to before. The new jest dispatch did not disturb the Python path.

The jest end-to-end leg genuinely needs Node.js and an `npm install` in
the fixture; this dev box has no Node.js, so that leg is deferred to CI
(the `ci-node-cell` slice adds a Node runner to GitHub Actions for
exactly this purpose).

## Commands run (verbatim) + observed output

CLI invoked as the repo virtualenv binary
(`/home/yjshin/dev/Nove-Test/.venv/bin/novetest`) from inside each
scratch fixture copy.

### Section A — pytest-coverage NOT regressed (PASS)

```sh
cp -r tests/fixtures/projects/pytest-coverage/. /tmp/nv-jestcov-smoke/
cd /tmp/nv-jestcov-smoke
novetest init
novetest run --coverage tests/      # entry_id 01KS2WD2FG30A1H70DJYXBP18W
novetest coverage show 01KS2WD2FG30A1H70DJYXBP18W
```

`coverage show` returned:
- `data.coverage_outcome.kind == "fact-set"` ✅
- `mapping_granularity == "per-test"` ✅ (pytest keeps per-test
  attribution — proves the jest `aggregate` path did not bleed into it)
- `summary.num_statements == 11` (> 0) ✅
- `summary.percent_covered == 86.667` — identical to the figure observed
  for this same fixture in prior cycles. No drift.

Conclusion: the `engine_name == "jest"` dispatch added to `derive.py`
does **not** disturb the pytest path. Section A passes.

### Section B — jest coverage E2E (SKIPPED — no Node.js)

This box has **no `node`** on PATH. (`npx` resolves only to a Windows
executable under `/mnt/c/...`, which is not a usable POSIX engine.) The
jest path therefore cannot be exercised; reported as skipped, matching
the merge team's own box.

To document the no-Node behaviour we ran `novetest run --coverage .`
against a scratch copy of the `jest-basic-coverage` fixture:

```sh
cp -r tests/fixtures/projects/jest-basic-coverage/. /tmp/nv-jest-smoke/
cd /tmp/nv-jest-smoke
novetest init
novetest run --coverage .           # no Node on PATH
```

Result: **exit 4**, `ok false`, structured envelope (no traceback):
- `engine_readiness.state == "engine-missing"`
- `engine_readiness.issues[0]` = "Node.js (`node`/`npx`) not found on
  PATH; install Node.js >=18 and ensure both `node` and `npx` are on
  PATH"
- `engine_readiness.evidence == ["package.json"]`
- error `code == "engine-engine-missing"`

This is correct, graceful degradation: a jest workspace with no Node
fails loudly and structurally before any coverage logic is reached.

## Critical edge cases

- **`collect_coverage=False` path unchanged** — could not be exercised
  end-to-end without Node (the readiness probe short-circuits at
  `engine-missing` before any coverage branching). Deferred to the CI
  Node cell. The disjoint-files merge note (Run owns `run/adapters/`,
  Coverage owns `coverage/`) and the unit/integration gate below give
  reasonable confidence the default path is byte-identical.
- **Missing coverage report → typed `unparseable-output`** — not
  manually forceable; flagged for awareness only, as the request itself
  notes.
- **Absolute path relativization in jest Istanbul reports** — requires a
  real jest run; deferred to CI. Worth an explicit eyeball in the
  Release team's post-GHA observation: confirm no absolute filesystem
  path appears in any `file_path` field of a jest `coverage show`.

## Cross-check — full test suite

`uv run pytest -q tests/unit tests/integration` on the merged tree:
**334 passed, 3 skipped** in ~32s — an exact match to the figure in all
three of this cycle's verification requests. The 3 skips are the
Node-dependent jest integration tests (2 jest-coverage + 1 jest exec),
expected without Node.js. `1 snapshot passed`.

## Issues found

None.

## Recommendations for PM

1. **Section B closure depends on the `ci-node-cell` slice.** This
   `partial` verdict can only be lifted to `passed` once the Release
   team observes the GHA run (post-`main`-push) and confirms the two
   jest-coverage integration tests report as **run, not skipped**. Track
   the jest-coverage E2E as closed only after that observation lands.
2. **Ask the Release post-GHA observation to explicitly eyeball the
   absolute-path edge case** — confirm a jest `coverage show` persists
   only workspace-relative `file_path` values (Istanbul emits absolute
   paths; the parser is supposed to relativize them). This is the one
   edge case Manual Test could not reach locally.
3. **Consider provisioning Node.js on the Manual Test dev box** for
   future cycles. Three jest-related slices have now been verified
   "partial / deferred to CI" for want of a local Node runtime
   (jest-adapter-phase1 last cycle, plus the two jest slices this
   cycle). A local Node would let Manual Test give jest slices a full
   `passed` verdict instead of repeatedly deferring to CI.

## Note on `ci-node-cell` verification (no Manual Test surface)

`verifications/2026-05-20-ci-node-cell.md` explicitly states the
`ci-node-cell` (Release) and `entry-id-contract-note` (Memory) slices
have **no Manual Test action** — CI YAML and a doc-only change. We
acknowledge them here: nothing was run for those two slices; no separate
findings file is required, per that request. CI observation for the Node
cell remains owned by the Release team.
