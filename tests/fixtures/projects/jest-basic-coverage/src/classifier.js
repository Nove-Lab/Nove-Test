// Tiny library under test with three branches, one deliberately left
// untested so the Istanbul `coverage-final.json` carries a concrete
// uncovered region. Mirrors `pytest_coverage.classifier` so the jest
// coverage fixture stays narrow: just enough surface for a per-file
// degraded coverage signal.
function classify(value) {
  if (value > 0) {
    return 'positive';
  }
  if (value === 0) {
    return 'zero';
  }
  // Intentionally unreached by the fixture's test suite.
  return 'negative';
}

module.exports = { classify };
