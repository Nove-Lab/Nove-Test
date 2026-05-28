# gotest-basic-coverage

`go test`-based fixture project used by Nove Test to validate the Run
engine's **coverage-emission path** for the Go ecosystem. Parallel to
`pytest-coverage` and `jest-basic-coverage`.

## What this fixture validates

- The `gotest_adapter`, invoked with `collect_coverage=True`, must run
  `go test -cover -coverprofile=<...>/cover.out -covermode=atomic
  -coverpkg=./...` and register the resulting `cover.out` in
  `NativeResult.artifact_paths` under the key `coverage_profile`. (The
  key is deliberately NOT `coverage_json` — that key is used by the
  pytest / jest adapters for the Istanbul-/coverage.py JSON format, and
  reusing it would mislead the Coverage engine. The future Coverage-team
  slice will dispatch on `engine_name == "go-test"` to parse the
  cover-profile format.)
- `cover.out`'s first line must be `mode: atomic` (per `go doc
  cmd/cover`). Subsequent lines have the form
  `<file>:<startLine>.<startCol>,<endLine>.<endCol> <numStmts> <count>`.
- The fixture has TWO source files (`classifier.go`, `arithmetic.go`) so
  the report carries interesting block structure across files.
- `Classify`'s negative branch is **intentionally not covered** by any
  test, so `cover.out` carries at least one uncovered region (`count=0`).
  Do NOT "fix" this by adding a negative-value test.

## Expected outcomes

| Test | Status |
| --- | --- |
| `TestAdd` | passed |
| `TestSubtract` | passed |
| `TestClassifyPositive` | passed |
| `TestClassifyZero` | passed |

(No failing tests — coverage gaps are the fixture's only signal.)

## Layout

```
gotest-basic-coverage/
├── go.mod                # module example.com/gotestbasiccoverage; go 1.21
├── classifier.go         # Classify — three branches, negative intentionally uncovered
├── arithmetic.go         # Add, Subtract — fully covered
└── arithmetic_test.go    # 4 passing tests
```

## Isolation

The fixture is self-contained — `go.mod` declares no external
dependencies. `go test -coverpkg=./...` measures every package under the
module; the `-coverpkg=./...` flag is mandatory because without it Go
only measures the test's own package (per engine-adapters.md §4 edge
cases). The fixture does NOT import any `novetest` code.
