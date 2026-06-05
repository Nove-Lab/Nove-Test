using MathLib;

namespace MathLib.Tests;

/// <summary>
/// Coverage-fixture variant of `dotnet-test-basic`. Same 3 tests,
/// same contract (2 pass + 1 fail), with an explicit `coverlet.collector`
/// PackageReference in the csproj. Exercised by
/// `tests/integration/run/test_dotnet_coverage.py`.
/// </summary>
public class MathTests
{
    [Fact]
    public void TestAddPasses()
    {
        Assert.Equal(5, MathOps.Add(2, 3));
    }

    [Fact]
    public void TestSubtractIntentionallyFails()
    {
        Assert.Equal(5, MathOps.Subtract(10, 4));
    }

    [Theory]
    [InlineData(1, 2, 3)]
    public void TestParametrized(int a, int b, int expected)
    {
        Assert.Equal(expected, MathOps.Add(a, b));
    }
}
