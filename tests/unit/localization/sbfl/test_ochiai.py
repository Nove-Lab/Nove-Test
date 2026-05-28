"""Ochiai formula unit tests — math correctness on hand-picked vectors."""

from __future__ import annotations

import math

import numpy as np

from novetest.localization.sbfl.ochiai import ochiai


def _arr(values: list[int]) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def test_ochiai_single_failure_single_location_returns_one() -> None:
    """One failing test hitting exactly one location: that location scores 1.0.

    ef=1, ep=0, nf=0, np_=0 ⇒ 1 / sqrt(1 * 1) = 1.0.
    """
    score = ochiai(_arr([1]), _arr([0]), _arr([0]), _arr([0]))
    assert math.isclose(float(score[0]), 1.0)


def test_ochiai_no_failures_returns_zero_everywhere() -> None:
    """When ef=0 across the board, every score is 0.0 (numerator-driven)."""
    score = ochiai(_arr([0, 0, 0]), _arr([3, 1, 0]), _arr([2, 2, 2]), _arr([0, 2, 3]))
    assert np.allclose(score, [0.0, 0.0, 0.0])


def test_ochiai_zero_denominator_returns_zero() -> None:
    """ef+nf=0 OR ef+ep=0 ⇒ denominator 0 ⇒ score 0.0 (no division-by-zero)."""
    # First column: no failed tests at all (ef+nf=0).
    # Second column: no test executed (ef+ep=0).
    score = ochiai(_arr([0, 0]), _arr([2, 0]), _arr([0, 5]), _arr([3, 0]))
    assert np.allclose(score, [0.0, 0.0])


def test_ochiai_pure_failing_coverage_outscores_mixed() -> None:
    """A location hit by all failures + zero passes outscores a mixed-coverage location."""
    # Location 0: hit by all 3 failing tests, 0 passing → ef=3, ep=0, nf=0, np_=5.
    # Location 1: hit by 2 of 3 failing + 5 of 5 passing → ef=2, ep=5, nf=1, np_=0.
    score = ochiai(_arr([3, 2]), _arr([0, 5]), _arr([0, 1]), _arr([5, 0]))
    # Location 0: 3 / sqrt(3 * 3) = 1.0
    # Location 1: 2 / sqrt(3 * 7) ≈ 0.4364
    assert math.isclose(float(score[0]), 1.0)
    assert float(score[0]) > float(score[1])


def test_ochiai_output_shape_matches_input() -> None:
    """Vector op preserves shape; 5-element input ⇒ 5-element output."""
    score = ochiai(
        _arr([1, 2, 0, 4, 1]),
        _arr([0, 1, 0, 2, 5]),
        _arr([3, 2, 4, 0, 3]),
        _arr([5, 4, 5, 3, 0]),
    )
    assert score.shape == (5,)
    assert score.dtype == np.float64


def test_ochiai_known_textbook_value() -> None:
    """Single hand-checked value: ef=2, ep=1, nf=1, np_=3 → 2/sqrt(3*3) = 2/3."""
    score = ochiai(_arr([2]), _arr([1]), _arr([1]), _arr([3]))
    assert math.isclose(float(score[0]), 2.0 / 3.0)
