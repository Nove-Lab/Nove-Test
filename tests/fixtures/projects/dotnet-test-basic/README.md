# dotnet-test-basic

Canonical xUnit v2 fixture for the .NET adapter. Mirrors the contract of
`pytest-basic` / `jest-basic` / `gotest-basic` / `junit-maven-basic` /
`cargo-test-basic`: **2 passing + 1 intentionally failing = 3 total**.

## Why two projects (not one)?

`MathLib/MathLib.csproj` is the library under test; `MathLib.Tests/
MathLib.Tests.csproj` is the test project that references it. This is the
canonical .NET pattern, AND it matters for the Coverlet path: when tests
and code-under-test live in the same assembly, Coverlet defaults to
excluding the test assembly (to avoid measuring the test fixtures' own
coverage), yielding empty coverage data. Splitting the projects lets the
Coverlet collector instrument `MathLib.dll` directly while leaving the
test assembly out.

## Test contract

| Test | Outcome | Notes |
|---|---|---|
| `TestAddPasses` | Passed | Baseline parity with sibling fixtures |
| `TestSubtractIntentionallyFails` | Failed | `Assert.Equal(5, Subtract(10, 4))` — `Subtract` returns `6`. Do NOT "fix" the assertion. |
| `TestParametrized(a: 1, b: 2, expected: 3)` | Passed | `[Theory]` + `[InlineData]`; R1 slug-correlation probe per `decisions/2026-06-03-coverlet-pertestcoverage-key.md` |

`dotnet test` exit code on this fixture: **1** (some user tests failed).
`metadata.native_exit_code = 1` on the Run Record.

## Floor versions (matrix-pinned)

- `Microsoft.NET.Test.Sdk` 17.8.0 — floor is 17.6 per supported-engine-matrix
- `xunit` 2.6.0 — floor pinned; do NOT downgrade to the 2.5.3 template default
- `xunit.runner.visualstudio` 2.5.3 — current template default; latest within the v2 line

## Coverage fixture sibling

`dotnet-test-basic-coverage/` mirrors this fixture but adds an explicit
`<PackageReference Include="coverlet.collector" Version="6.0.2" />`.
Used by `tests/integration/run/test_dotnet_coverage.py`.
