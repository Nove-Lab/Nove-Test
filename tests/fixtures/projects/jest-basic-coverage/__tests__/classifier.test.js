const { classify } = require('../src/classifier');

describe('classify', () => {
  test('positive values are classified as positive', () => {
    expect(classify(7)).toBe('positive');
  });

  test('zero is classified as zero', () => {
    expect(classify(0)).toBe('zero');
  });

  // The negative branch (value < 0) is deliberately left uncovered to
  // exercise the Coverage engine's uncovered-line / uncovered-branch
  // extraction. Do NOT "fix" this by adding a negative-value test.
});
