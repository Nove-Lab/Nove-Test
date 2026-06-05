using MathLib;

namespace MathLib.Tests;

/// <summary>
/// Canonical 3-test xUnit fixture for the dotnet adapter. Mirrors the
/// shape of pytest-basic / gotest-basic / junit-maven-basic /
/// cargo-test-basic — 2 passing + 1 intentionally failing test plus a
/// parametrized [Theory] for the R1 slug-correlation probe.
/// </summary>
public class MathTests
{
    /// <summary>
    /// Baseline pass case. Mirrors `pytest-basic::test_add`,
    /// `gotest-basic::TestAdd`, `cargo-test-basic::tests::test_add_passes`.
    /// </summary>
    [Fact]
    public void TestAddPasses()
    {
        Assert.Equal(5, MathOps.Add(2, 3));
    }

    /// <summary>
    /// Intentional contract failure. ``Subtract(10, 4)`` is correctly ``6``;
    /// asserting ``== 5`` is the fixture's deliberate failure so the adapter's
    /// failure-detail capture path runs against a real ``dotnet test``
    /// invocation. Do NOT "fix" the assertion.
    /// </summary>
    [Fact]
    public void TestSubtractIntentionallyFails()
    {
        Assert.Equal(5, MathOps.Subtract(10, 4));
    }

    /// <summary>
    /// Parametrized [Theory] using [InlineData] — the R1 slug-correlation
    /// probe per decisions/2026-06-03-coverlet-pertestcoverage-key.md §R1.
    /// xUnit emits this test's TRX `testName` as
    /// ``"MathLib.Tests.MathTests.TestParametrized(a: 1, b: 2, expected: 3)"``
    /// (note the parens, colons, commas, spaces that Coverlet's slugifier
    /// must handle). One data point keeps the probe minimal.
    /// </summary>
    [Theory]
    [InlineData(1, 2, 3)]
    public void TestParametrized(int a, int b, int expected)
    {
        Assert.Equal(expected, MathOps.Add(a, b));
    }
}
