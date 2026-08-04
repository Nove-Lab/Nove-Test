using MathLib;

namespace MathLib.Tests;

/// <summary>
/// The same 3-test contract as `dotnet-test-basic` (2 passing + 1
/// intentionally failing), authored against a project that sits at
/// depth 2 under a solution root. Identical assertions on purpose —
/// this fixture exists to prove DISCOVERY, so everything downstream of
/// discovery must be indistinguishable from its flat sibling.
/// </summary>
public class MathTests
{
    /// <summary>Baseline pass case.</summary>
    [Fact]
    public void TestAddPasses()
    {
        Assert.Equal(5, MathOps.Add(2, 3));
    }

    /// <summary>
    /// Intentional contract failure. ``Subtract(10, 4)`` is correctly
    /// ``6``; asserting ``== 5`` is the fixture's deliberate failure.
    /// Do NOT "fix" the assertion.
    /// </summary>
    [Fact]
    public void TestSubtractIntentionallyFails()
    {
        Assert.Equal(5, MathOps.Subtract(10, 4));
    }

    /// <summary>
    /// Parametrized [Theory] — keeps TRX display-name parity with the
    /// flat fixture (parens / colons / commas in the test identity).
    /// </summary>
    [Theory]
    [InlineData(1, 2, 3)]
    public void TestParametrized(int a, int b, int expected)
    {
        Assert.Equal(expected, MathOps.Add(a, b));
    }
}
