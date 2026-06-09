# Advanced CLI — Memo

> **Scope of this memo.** This page is intentionally **short**.
> It enumerates the deeper CLI verbs and flags that the
> [quick-start.md](./quick-start.md) happy-case walkthrough
> does **not** cover. Each verb gets one-line treatment with
> a pointer to the source-of-truth design doc. A full advanced
> user document is **not yet written** and will be authored as
> a separate deliverable after the v0.1.0 release.

The happy path uses just four verbs:

- `novetest --version`
- `novetest --help`
- `novetest init`
- `novetest test [<target>]` (plus the bare alias
  `novetest <target>`)

Every other verb listed below is **optional for the happy path**.
Reach for them when you need their specific capability.

---

## Optional but commonly useful (covered in `after-test.md`)

These two are already documented in
[after-test.md](./after-test.md) because they slot naturally
into the happy-case follow-up flow:

- **`novetest status`** — read-only snapshot: latest run +
  per-stage availability across the whole store.
- **`novetest inspect <run_id>`** — aggregated single-run view:
  run record + all derived outcomes for one run.

---

## Deeper verbs (not covered in this MVP user doc)

### Run engine, raw

- **`novetest run [<target>] [--coverage]`** — execute the
  native engine and persist a Run Record, **without** the
  orchestration stages that `novetest test` chains
  (no auto-regression, no auto-localization, no
  recommendation synthesis). Useful when you want fine-grained
  control over the pipeline (e.g. CI splitting run + analyze).

### Coverage engine

- **`novetest coverage show <run_id>`** — print the persisted
  Coverage Facts envelope for a specific run. Cache-read only;
  never derives. Useful for re-querying without re-running.
- **`novetest coverage diff <baseline_run_id> <target_run_id>`**
  — compute and print the per-file coverage delta between two
  runs (newly-covered lines, newly-uncovered lines, branch
  changes). Useful for PR review automation.

### Regression engine

- **`novetest regression compare <baseline_run_id> <target_run_id>`**
  — explicit pair comparison. Use when you want a specific
  baseline (overriding the auto-latest heuristic).
- **`novetest regression latest`** — re-derive (or read from
  cache) the regression facts for the latest comparable pair on
  the active target. `novetest test` already does this; the
  standalone verb is mainly diagnostic.

### Localization engine

- **`novetest localization <run_id>`** — re-rank suspicious code
  locations for one run via SBFL.
  - `--formula <ochiai | op2 | dstar2 | tarantula>` — pick the
    formula. Default: `ochiai`.
  - `--top-n <int>` — cap the ranked list. Default: 10.
- **`novetest localization latest`** — same as above, applied to
  the latest analyzable run on the active target.

### Replay engine

- **`novetest replay <run_id>`** — re-execute a prior run under
  the same reconstructed conditions; classify reproducibility
  as `reproducible` / `inconsistent` / `unable_to_replay`.
  - `--reruns <int>` (default 1) — for flakiness investigation
    bump to 5 or 10.
  - `--timeout <seconds>` (default 600.0) — per-rerun ceiling.

### Compose verbs

- **`novetest compare <baseline_run_id> <target_run_id>`** —
  composed regression + coverage delta for a pair, in a single
  envelope. Useful when reviewing one specific pair end-to-end.

### Memory / history management

- **`novetest memory list`** — list Run History newest-first
  (tombstones included with their tombstoned-at marker).
- **`novetest memory show <run_id>`** — show the raw Memory
  Entry (live or tombstoned).
- **`novetest memory delete <run_id>`** — tombstone a Memory
  Entry (atomic POSIX rename; recoverable until garbage
  collection).

### Output format override

- **`--output {json | text | ndjson}`** — global flag, may be
  set per invocation or via `NOVETEST_OUTPUT=...`. `json` is
  the default when piped; `text` is the default on a TTY.
  `ndjson` streams one envelope per line — useful for the few
  long-running verbs (`replay --reruns 20`, future
  `regression --watch`).

---

## Flags the happy-case walkthrough deliberately omits

`novetest test`, `novetest init`, and `novetest run` accept
extra flags that the user doc does not show. They are not
needed for the happy path; mentioning them here only as
breadcrumbs to the future advanced doc:

- Target-resolution flags (e.g. pytest nodeid filtering, jest
  test-name regex, gotest `-run` regex, nextest filter
  expressions) — passed-through to the native engine; engine
  docs are the source of truth.
- Coverage tuning (engine-specific tooling switches; the
  adapter usually does the right thing).
- Workspace overrides — `--workspace <path>` if you want to
  drive a project from elsewhere; rarely needed if you `cd`
  first.

---

## Where the source-of-truth design docs live

For each verb listed above, the binding spec lives under the
team's interface contract or workflow document:

- Run engine: `design/workflows/run.md`,
  `design/interace-contract/run.md`,
  `design/implementation-plan/engine-adapters.md`.
- Memory engine: `design/workflows/memory.md`,
  `design/interace-contract/memory.md`.
- Coverage engine: `design/workflows/coverage.md`,
  `design/interace-contract/coverage.md`.
- Regression engine: `design/workflows/regression.md`,
  `design/interace-contract/regression.md`.
- Localization engine: `design/workflows/localization.md`,
  `design/interace-contract/localization.md`,
  `design/implementation-plan/localization-strategy.md`.
- Replay engine: `design/workflows/replay.md`,
  `design/interace-contract/replay.md`.
- Orchestration (recommendation synthesis,
  `test`/`status`/`inspect`/`compare`):
  `design/workflows/orchestration.md`,
  `design/interace-contract/orchestration.md`,
  `design/implementation-plan/recommendation-synthesis.md`.

The advanced user doc (when written) will translate those into
copy-pasteable user examples. Until then, the design docs are
the authoritative reference.

---

## What this doc explicitly will NOT become

This memo will **stay short**. When the advanced user doc
ships, it will live under `design/user-doc/advanced/` as a
proper companion to the happy-case docs you are reading now.
This page will then become a one-line "the advanced doc lives
over there →" pointer.
