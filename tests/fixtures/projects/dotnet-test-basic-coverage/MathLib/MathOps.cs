namespace MathLib;

/// <summary>
/// Library under test for the `dotnet-test-basic-coverage` fixture. Same
/// surface as `dotnet-test-basic`; the only difference between the two
/// fixtures is the coverage variant pins `coverlet.collector` >= 6.0.2
/// explicitly in the test project so the coverage integration test has a
/// reliable Coverlet to instrument with. Mirroring sibling adapters'
/// basic / basic-coverage split (cargo-test-basic + cargo-test-basic-
/// coverage; junit-maven-basic + Maven coverage probe inline; etc).
/// </summary>
public static class MathOps
{
    public static int Add(int a, int b) => a + b;
    public static int Subtract(int a, int b) => a - b;
}
