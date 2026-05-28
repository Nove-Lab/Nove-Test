# gotest-basic

Minimal `go test`-based fixture project used by Nove Test as software under
test. Parallel to `pytest-basic` (+ `pytest-failing`) and `jest-basic` for
the Go ecosystem — the engine-adapters plan calls out failure-detail
capture as the meaningful surface for Go, so this single fixture
consolidates one passing test and one (intentionally) failing test.

## What this fixture validates

A `go test -json` Run loop with the `go test` Native Engine:

- `assess_engine_readiness` should classify this workspace as `ready` once
  `go` is on `PATH` (no dependency-install step needed; `go test` resolves
  the standard library only).
- `novetest run` should detect the failing case and emit a Run Record with
  `summary_counts` matching pass=3 / fail=1 (the three subtest-aware
  invocations: `TestAdd`, `TestSubtract`, `TestAddSubtests/zero_left`,
  `TestAddSubtests/commutative` give 4 leaf tests — three pass, one fails).
- The adapter must reassemble multi-line `Output` events into a single
  failure log for `TestSubtract` and register a `failure_reference` path.

## Layout

```
gotest-basic/
├── go.mod            # module example.com/gotestbasic; go 1.21
├── math.go           # Add, Subtract — the SuT
└── math_test.go      # one pass, one intentional fail, one with subtests
```

## Isolation

The fixture is self-contained — `go.mod` declares no external dependencies,
so `go test` walks only the standard library. It does NOT import any
`novetest` code. `go test` is invoked with `cwd=` this directory and
`GOFLAGS=-mod=readonly` so no `go.sum` lookup or module download is ever
attempted.

## The deliberate failure

`TestSubtract` asserts `Subtract(10, 4) == 5` (the actual result is `6`).
This is the fixture's contract: the failure path is what the integration
test exercises end-to-end. Do NOT "fix" the assertion.
