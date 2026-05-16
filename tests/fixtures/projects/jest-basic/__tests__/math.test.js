const { add, subtract } = require('../src/math');

describe('math', () => {
  test('add returns the sum of two integers', () => {
    expect(add(2, 3)).toBe(5);
  });

  test('subtract returns the difference of two integers', () => {
    expect(subtract(10, 4)).toBe(6);
  });

  test('add is commutative', () => {
    expect(add(1, 2)).toBe(add(2, 1));
  });
});
