namespace MathLib;

/// <summary>
/// Minimal library under test for the `dotnet-test-basic` Nove Test fixture.
/// Mirrors the surface of pytest-basic / gotest-basic / junit-maven-basic /
/// cargo-test-basic — just enough for one passing unit test, one
/// intentionally-failing unit test, and one parametrized (xUnit `[Theory]`)
/// test that exercises the slug-correlation probe (R1 per
/// decisions/2026-06-03-coverlet-pertestcoverage-key.md).
/// </summary>
public static class MathOps
{
    /// <summary>Always-passing arithmetic; exercises the happy path.</summary>
    public static int Add(int a, int b) => a + b;

    /// <summary>
    /// Subtraction. The fixture's failing test calls Subtract(10, 4) and
    /// asserts == 5 (off by one), so this method is correct — the test is
    /// where the contract failure lives. Do NOT "fix" the test.
    /// </summary>
    public static int Subtract(int a, int b) => a - b;
}
