from pytest_coverage.classifier import classify


def test_classify_positive() -> None:
    assert classify(7) == "positive"


def test_classify_zero() -> None:
    assert classify(0) == "zero"


# The negative branch (value < 0) is deliberately left uncovered to
# exercise the Coverage engine's missing_lines / missing_branches paths.
