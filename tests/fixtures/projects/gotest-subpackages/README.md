# gotest-subpackages

Go fixture whose tests live ONLY in a subpackage (`./pkg`); the root
package compiles but has **no tests**. Built for the RUN-01 (W1/S1)
regression tests: pre-fix, `novetest run .` invoked `go test -json … .`
— the root package alone, non-recursively — which ran zero tests,
exited 0, and was normalized to `status="passed"` (silent false green).
`novetest run ./pkg` was normalized to the bare `pkg`, which `go test`
read as an import path and failed before compiling (fake build failure).

## What this fixture validates

- Directory target `.` converts to `./...` and the `./pkg` tests
  actually run (no zero-test "passed").
- Directory target `pkg` (the normalized form of `./pkg`) converts to
  `./pkg/...` and runs normally instead of raising
  `AdapterInvocationError(unparseable-output)`.
- Nodeid `pkg::TestAdd` decomposes to `-run '^TestAdd$' ./pkg` and
  selects exactly one test — `TestAddCommutative` shares the prefix, so
  a non-anchored pattern would over-select.
- Engine-native `./...` still passes through verbatim.

## Layout

```
gotest-subpackages/
├── go.mod            # module example.com/gotestsubpackages; go 1.21
├── rootlib.go        # root package: compiles, NO tests (contract!)
└── pkg/
    ├── mathx.go      # Add, Double — the SuT
    └── mathx_test.go # TestAdd, TestAddCommutative, TestDouble — all pass
```

## Isolation

Self-contained: `go.mod` declares no dependencies, `go test` resolves
only the standard library, and no `novetest` code is imported. Invoked
with `GOFLAGS=-mod=readonly` by the adapter, so no module download is
ever attempted.

## Contracts

- The root package must NEVER gain a `_test.go` file — the whole point
  is "root has no tests".
- All tests in `./pkg` pass deterministically (no intentional failure
  here; `gotest-basic` covers the failure path).
- `TestAdd` / `TestAddCommutative` must keep their shared prefix.
