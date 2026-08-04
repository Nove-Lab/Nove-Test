namespace MathLib;

/// <summary>
/// Library under test for the `dotnet-test-solution-nested` fixture.
/// Deliberately byte-identical in behavior to `dotnet-test-basic`'s
/// MathOps: the two fixtures differ ONLY in directory layout, so any
/// difference in the Run Record is attributable to project discovery
/// and nothing else.
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
