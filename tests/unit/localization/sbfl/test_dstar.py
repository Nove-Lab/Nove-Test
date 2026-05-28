"""DStar(*=2) formula unit tests — math correctness on hand-picked vectors."""

from __future__ import annotations

import math

import numpy as np

from novetest.localization.sbfl.dstar import dstar2


def _arr(values: list[int]) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def test_dstar2_zero_denominator_returns_zero() -> None:
    """ep+nf == 0 ⇒ score 0.0 (no division-by-zero)."""
    # Only failing tests AND every failing test executed the location:
    # nf=0; ep also 0 → denom 0.
    score = dstar2(_arr([3]), _arr([0]), _arr([0]), _arr([0]))
    assert math.isclose(float(score[0]), 0.0)


def test_dstar2_known_textbook_value() -> None:
    """ef=2, ep=1, nf=1, np_=3 ⇒ 4 / (1 + 1) = 2.0."""
    score = dstar2(_arr([2]), _arr([1]), _arr([1]), _arr([3]))
    assert math.isclose(float(score[0]), 2.0)


def test_dstar2_no_failures_returns_zero() -> None:
    """ef=0 across the board ⇒ numerator 0 ⇒ score 0.0."""
    score = dstar2(_arr([0, 0, 0]), _arr([3, 1, 0]), _arr([2, 2, 2]), _arr([0, 2, 3]))
    assert np.allclose(score, [0.0, 0.0, 0.0])


def test_dstar2_higher_ef_dominates() -> None:
    """ef^2 grows quadratically; high-ef locations rank well above low-ef ones."""
    # Both with denom 1, but ef of 5 vs ef of 1: 25 vs 1.
    score = dstar2(_arr([5, 1]), _arr([1, 1]), _arr([0, 0]), _arr([4, 4]))
    assert math.isclose(float(score[0]), 25.0)
    assert math.isclose(float(score[1]), 1.0)


def test_dstar2_output_shape_matches_input() -> None:
    score = dstar2(_arr([1, 2, 0]), _arr([0, 1, 0]), _arr([3, 2, 4]), _arr([5, 4, 5]))
    assert score.shape == (3,)
    assert score.dtype == np.float64
