"""Small statistics helpers with one deliberately-buggy operation.

Three top-level functions. ``average`` is the seeded fault: it divides
``sum(numbers)`` by ``len(numbers)`` without handling the empty-list
case, so the corresponding pytest case raises ``ZeroDivisionError``
*inside the SuT*. pytest's failure capture identifies the SuT file as
the crash site, so the adapter normalizer emits a ``failure_reference``
of the form ``"localization_no_coverage/statistics.py:N: ZeroDivisionError"``.

Combined with the run being invoked WITHOUT ``--coverage``, the
Localization engine routes to ``failure_proximity`` mode and the
file-mention frequency ranks ``statistics.py`` top-1.

**Do not "fix" the bug** — the fixture's contract is the bug.
"""


def total(numbers: list[int]) -> int:
    """Sum of a list of integers."""
    return sum(numbers)


def maximum(numbers: list[int]) -> int:
    """Largest element in a non-empty list."""
    return max(numbers)


def average(numbers: list[int]) -> float:
    """Arithmetic mean of a list of integers.

    Deliberate bug: divides by ``len(numbers)`` without handling the
    empty-list case. Calling ``average([])`` raises
    ``ZeroDivisionError`` from this function's body, which is what makes
    pytest's ``crash.path`` resolve to THIS file rather than the test
    file (assertions inside the test would resolve to the test file
    instead, which is the failure_proximity boundary failure mode we
    want to avoid).
    """
    return sum(numbers) / len(numbers)
