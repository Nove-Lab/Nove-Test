"""Tiny domain function with three branches, one deliberately untested.

The test suite covers the ``positive`` and ``zero`` branches; the
``negative`` branch is intentionally left uncovered so the Coverage
engine's ``missing_branches`` / ``missing_lines`` extraction has
something concrete to point at.
"""


def classify(value: int) -> str:
    if value > 0:
        return "positive"
    if value == 0:
        return "zero"
    # Intentionally unreached by the fixture's test suite.
    return "negative"
