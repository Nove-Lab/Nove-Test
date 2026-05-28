"""Small calculator with one deliberately-buggy operation.

Five top-level functions plus a class with one method. The ``divide``
function is the seeded fault: it returns ``a + b`` instead of ``a / b``,
so the corresponding pytest case fails. Every other function is
correctly implemented and its test passes.

Combined with ``--cov-context=test`` per-test coverage attribution, the
SBFL engine should rank ``divide`` top-1 under Ochiai because:
- The failing ``test_divide_yields_quotient`` is the only test that
  executes ``divide``'s line.
- ``ef = 1, ep = 0, nf = 0, np_ = N_other_tests`` → Ochiai score 1.0.

The other functions are touched only by passing tests, so their Ochiai
suspicion is 0.
"""


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def multiply(a: int, b: int) -> int:
    return a * b


def divide(a: int, b: int) -> float:
    # Deliberate bug — should be ``a / b``. The test
    # ``test_divide_yields_quotient`` fails because of this line.
    return a + b


def negate(x: int) -> int:
    return -x


class Counter:
    """Trivial side-effectful helper to round the file out.

    Not directly involved in the fault — exists so the SBFL slice has
    multiple symbols (function + method) to aggregate against.
    """

    def __init__(self) -> None:
        self._count = 0

    def increment(self) -> int:
        self._count += 1
        return self._count
