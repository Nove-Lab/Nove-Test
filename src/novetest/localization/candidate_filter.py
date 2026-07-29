"""Exclude the run's own test files from the SBFL candidate set.

## Why this exists

SBFL is *structurally* biased toward test code. A failing test's own body
is executed by exactly one failing test and by no passing test, so its
counts are always ``ef = 1, ep = 0`` — the shape every suspiciousness
formula is designed to reward. When the coverage tool measures the test
files too (the pytest adapter runs ``--cov=.``), those lines enter the
spectra as candidate locations and outscore the real defect, which is
typically executed by passing tests as well (``ep > 0``).

Measured on ``tests/fixtures/projects/localization-shared-defect`` (7
tests, 2 failing), reproducing the wave-1 persona-P1 ranking exactly:

| location                                | ef | ep | nf | np | Ochiai |
|-----------------------------------------|----|----|----|----|--------|
| a failing test's own body               |  1 |  0 |  1 |  5 | 0.7071 |
| the defect (``totals.py::invoice_total``)|  2 |  3 |  0 |  2 | 0.6325 |

``ep = 0`` beats ``ef = 2``. This does not depend on the project, the
language or the defect — it follows from the definition of a test.

## The rule

Drop every candidate location whose file is the file of a **test node
discovered in this run**. The file set comes from the Run Record's own
``test_results`` node ids — ground truth, not a name pattern. Deliberately
NOT a ``test_*`` / ``*_test.go`` / ``tests/`` heuristic: with six
ecosystems in the matrix, a naming guess is wrong somewhere, and the run
already knows the answer.

## Node id → file path

Node ids that carry a file path spell it as the half before the first
``::`` (pytest ``tests/test_x.py::test_a``; jest
``src/x.test.ts::suite::case``). Ecosystems whose node ids carry no file
path (go ``package::Test``, cargo ``crate::mod::test``, JUnit
``Class#method``, dotnet FQNs) still produce a path half, but it can
never equal a real covered-file path, so the intersection with the
candidate set makes the filter a **no-op** there rather than a
mis-exclusion. That is the whole safety argument: the derived strings are
only ever compared for equality against paths the coverage tool actually
reported.

Files that hold no test node — ``conftest.py``, fixtures, test helpers —
are NOT excluded. A defect in shared test infrastructure stays rankable.

## Fallback

If the exclusion would leave the ranking with no positively-scored
candidate while the unfiltered ranking had one, it is **reverted** and
``reverted=True`` is reported. A user whose defect really does live in a
test file must not get silence.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from novetest.models.run_record import RunRecord


T = TypeVar("T")


def normalize_path(path: str) -> str:
    """Canonical comparison key for a workspace-relative path.

    Folds the two representational differences that can separate a node
    id's path half from a ``CoverageFactSet`` file path for the *same*
    file: Windows separators and a leading ``./``. Nothing else — this is
    a string key, never a filesystem probe (the file may not exist on the
    machine deriving the finding).
    """
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def discovered_test_files(record: RunRecord) -> frozenset[str]:
    """Normalized paths of the files owning ``record``'s test nodes.

    Every discovered test node counts, not just the failing ones: a
    passing test's file is just as non-actionable a suspect, and the
    passing tests are what make the failing tests' bodies stand out in
    the first place.
    """
    return frozenset(
        key
        for key in (
            normalize_path(tr.node_id.partition("::")[0])
            for tr in record.test_results
        )
        if key
    )


@dataclass(frozen=True, slots=True)
class ExclusionResult(Generic[T]):
    """Outcome of applying the exclusion to one mode's candidate list.

    - ``candidates`` — the list to rank (filtered, or the original when
      ``reverted``).
    - ``excluded_count`` — how many candidates the filter matched. Non-zero
      with ``reverted=True`` means "matched, then put back".
    - ``reverted`` — the filter emptied the positively-scored ranking and
      was undone.
    """

    candidates: list[T]
    excluded_count: int
    reverted: bool


def apply_test_file_exclusion(
    candidates: Sequence[T],
    *,
    test_files: frozenset[str],
    file_of: Callable[[T], str],
    score_of: Callable[[T], float],
) -> ExclusionResult[T]:
    """Drop test-file candidates, reverting rather than emptying the ranking.

    ``score_of`` reads the SELECTED formula's score. Only positively-scored
    candidates ever become entries (the ANA-08 rule both SBFL modes apply
    downstream), so "would this exclusion empty the ranking?" is decided on
    the positive candidates alone.
    """
    kept = [c for c in candidates if normalize_path(file_of(c)) not in test_files]
    excluded_count = len(candidates) - len(kept)
    if excluded_count == 0:
        return ExclusionResult(list(candidates), 0, False)
    if any(score_of(c) > 0 for c in kept):
        return ExclusionResult(kept, excluded_count, False)
    if any(score_of(c) > 0 for c in candidates):
        # Every positive suspect lives in a test file — surface them
        # rather than an empty ``entries`` list.
        return ExclusionResult(list(candidates), excluded_count, True)
    # Nothing is suspicious anywhere; the exclusion changes no output.
    return ExclusionResult(kept, excluded_count, False)


__all__ = [
    "ExclusionResult",
    "apply_test_file_exclusion",
    "discovered_test_files",
    "normalize_path",
]
