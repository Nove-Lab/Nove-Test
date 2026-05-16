// Tiny library under test. Mirrors `pytest_basic.math_utils` so the jest
// fixture stays narrow in scope: just enough surface for 3 passing tests.
function add(a, b) {
  return a + b;
}

function subtract(a, b) {
  return a - b;
}

module.exports = { add, subtract };
