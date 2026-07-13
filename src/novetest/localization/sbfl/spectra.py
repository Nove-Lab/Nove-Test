"""Build the (tests × statements) spectra matrix from per-test Coverage Facts.

The spectra matrix is the load-bearing data structure for SBFL: rows are
tests, columns are (file, line) locations, cell ``(i, j)`` is ``1`` when
test ``i`` executed location ``j`` and ``0`` otherwise. Combined with a
per-test outcome vector (1=failed, 0=passed), the four formulas
(Ochiai / Op2 / DStar / Tarantula) become single numpy vector ops over
the matrix.

Dense representation only at this slice. A sparse fallback is Open
Question #11 (``design/implementation-plan/localization-strategy.md``
Open Items §3 / engine-adapters.md) — revisit when a real fixture
exceeds the threshold; for Phase 4 entry the dense path satisfies
NFR-LOC-002.

**Empirically validated 2026-06-01** at the NFR-LOC-002 scale (500
failed-test references × 50,000 covered locations, per-test spectra
of shape 3500 × 50000) via
``tests/perf/localization/test_perf_derive_per_test.py``: median
1.33 s on the reference dev host vs the 8.0 s NFR ceiling — comfortably
under the 5.0 s internal budget. Open Q #11 (sparse repr threshold) is
**not** the binding NFR constraint at this scale; the hot paths the
perf slice surfaced were in ``derive.py`` (per-location
``Path.resolve`` and per-failed-row ``.sum()`` calls in
``_aggregate_by_symbol``) and were addressed there. Sparse
representation stays a forward-looking concern for
**larger-than-NFR** suites (post-MVP).

Preconditions enforced by the caller (``derive_localization_findings``):
- ``coverage_facts.mapping_granularity == "per-test"``
- ``failed_test_ids`` is non-empty (otherwise we surface
  ``REASON_NO_FAILED_TESTS`` upstream).

This module fails loudly when ``line_contexts`` is empty everywhere
(defensive parsing): a Coverage Fact set claiming per-test granularity
with no actual per-test attribution is malformed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np
from numpy.typing import NDArray

from novetest.models.coverage_fact_set import CoverageFactSet


@dataclass(slots=True, frozen=True)
class Spectra:
    """Built (tests × statements) spectra ready for SBFL formula application.

    - ``test_ids[i]``     — the pytest nodeid (or equivalent) of row ``i``.
    - ``locations[j]``    — the ``(file_path, line)`` tuple of column ``j``.
    - ``matrix[i, j]``    — ``1`` if test ``i`` executed location ``j``.
    - ``test_outcomes[i]``— ``1`` if test ``i`` failed, ``0`` if passed.

    All four arrays are aligned by index. The location ordering is stable
    (sorted by file, then by line) so two calls with the same input
    produce byte-identical matrices — needed for cache determinism and
    reproducible ranking ties.
    """

    # NOT a wire model — no schema_version needed. ClassVar pinned for
    # symmetry with the persisted models so future serialization (e.g. a
    # cached spectra debug dump) is a clean evolution rather than a
    # backwards-compatibility hazard.
    CURRENT_SCHEMA_VERSION: ClassVar[int] = 1

    test_ids: tuple[str, ...]
    locations: tuple[tuple[str, int], ...]
    matrix: NDArray[np.uint8]
    test_outcomes: NDArray[np.uint8]


class SpectraBuildError(ValueError):
    """Raised when the spectra matrix cannot be built from the inputs."""


def build_spectra(
    coverage_facts: CoverageFactSet,
    failed_test_ids: frozenset[str],
    passed_test_ids: frozenset[str],
) -> Spectra:
    """Build the per-test spectra from ``coverage_facts.files[*].line_contexts``.

    Outcome vocabulary (ANA-11, pinned S30): the caller supplies BOTH
    outcome sets explicitly — ``failed_test_ids`` (the
    ``models.FAIL_LIKE_OUTCOMES`` bucket: ``failed`` / ``errored``) and
    ``passed_test_ids`` (strictly ``outcome == "passed"``). Tests
    discovered in the coverage contexts that are in NEITHER set
    (``skipped`` / ``xfailed`` / ``xpassed``, or nodeids the Run Record
    does not attest at all) are EXCLUDED from the SBFL sample: they get
    no matrix row and contribute to neither ``ef``/``nf`` nor
    ``ep``/``np_``. The pre-S30 behavior inferred "not failed ⇒ passed",
    so a covered ``xfailed``/``xpassed`` test inflated ``ep`` and
    diluted suspicion in all four formulas.

    Two-pass:

    1. Walk every file's ``line_contexts`` to discover the set of tests
       AND the set of (file, line) locations actually attested by the
       coverage. The discovered test set is the union of all per-line
       nodeids across all files (passing AND failing — passing tests are
       needed to populate ``ep`` / ``np_``), filtered to the two outcome
       sets per the exclusion contract above. The discovered location
       set is every line with at least one nodeid in its context (a
       location stays a column even when every attesting test is
       excluded — its counts are then all zero).
    2. Allocate the dense ``(len(tests), len(locations))`` uint8 matrix
       and stamp 1s by replaying the contexts (excluded nodeids are
       skipped).

    The failed-test outcome vector is built by intersecting
    ``failed_test_ids`` with the discovered test set: failed tests that
    do not appear in any line context (e.g. collection errors, tests
    that never executed any covered code) are still recorded as rows
    with all-zero coverage so ``ef`` is correctly zero for them. To make
    that work, ``failed_test_ids`` outside the discovered union are
    included as rows too. ``passed_test_ids`` outside the discovered
    union get NO row — an unattested passing test carries no per-line
    evidence, and adding all-zero passing rows would shift ``np_`` for
    every location. When every non-failed discovered test is excluded,
    the sample degrades to failing rows only (``ep == np_ == 0``).

    Raises ``SpectraBuildError`` when every file's ``line_contexts`` is
    empty — the caller has already validated
    ``mapping_granularity == "per-test"`` so this state indicates a
    malformed Coverage Fact set rather than a normal "no coverage" path.
    """
    # Pass 1: discover tests and locations from non-empty line_contexts.
    discovered_tests: set[str] = set()
    discovered_locations: list[tuple[str, int]] = []
    seen_locations: set[tuple[str, int]] = set()
    any_context = False

    for file_cov in coverage_facts.files:
        for line, nodeids in file_cov.line_contexts.items():
            if not nodeids:
                continue
            any_context = True
            for nodeid in nodeids:
                discovered_tests.add(nodeid)
            location = (file_cov.file_path, line)
            if location not in seen_locations:
                seen_locations.add(location)
                discovered_locations.append(location)

    if not any_context:
        raise SpectraBuildError(
            "CoverageFactSet has mapping_granularity='per-test' but every "
            "FileCoverage.line_contexts is empty — cannot build spectra"
        )

    # Exclusion contract (ANA-11): keep only discovered tests with an
    # attested failed/passed outcome; then include failed tests that the
    # coverage never attested to (e.g. collection errors, tests that
    # crashed before any covered code ran) — they count as rows with
    # all-zero coverage so ef stays correct.
    sampled_tests = discovered_tests & (failed_test_ids | passed_test_ids)
    all_test_ids = sorted(sampled_tests | set(failed_test_ids))
    sorted_locations = sorted(discovered_locations)

    test_index = {tid: i for i, tid in enumerate(all_test_ids)}
    location_index = {loc: j for j, loc in enumerate(sorted_locations)}

    matrix = np.zeros(
        (len(all_test_ids), len(sorted_locations)), dtype=np.uint8
    )

    # Pass 2: stamp 1s for every (test, location) pair attested.
    # Excluded nodeids (skipped/xfailed/xpassed/unattested) have no row
    # in ``test_index`` and are skipped.
    for file_cov in coverage_facts.files:
        for line, nodeids in file_cov.line_contexts.items():
            if not nodeids:
                continue
            j = location_index[(file_cov.file_path, line)]
            for nodeid in nodeids:
                i = test_index.get(nodeid)
                if i is None:
                    continue
                matrix[i, j] = 1

    test_outcomes = np.array(
        [1 if tid in failed_test_ids else 0 for tid in all_test_ids],
        dtype=np.uint8,
    )

    return Spectra(
        test_ids=tuple(all_test_ids),
        locations=tuple(sorted_locations),
        matrix=matrix,
        test_outcomes=test_outcomes,
    )
