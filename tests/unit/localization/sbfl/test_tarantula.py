"""Tarantula formula unit tests — math correctness on hand-picked vectors."""

from __future__ import annotations

import math

import numpy as np

from novetest.localization.sbfl.tarantula import tarantula


def _arr(values: list[int]) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def test_tarantula_no_failures_returns_zero() -> None:
    """ef+nf == 0 ⇒ failing ratio undefined ⇒ score 0.0."""
    # Only passing tests touched these locations.
    score = tarantula(_arr([0, 0]), _arr([2, 1]), _arr([0, 0]), _arr([3, 4]))
    assert np.allclose(score, [0.0, 0.0])


def test_tarantula_no_test_executed_returns_zero() -> None:
    """ef=0 AND ep=0 ⇒ denom 0 ⇒ score 0.0 (no NaN leak)."""
    score = tarantula(_arr([0]), _arr([0]), _arr([5]), _arr([5]))
    assert math.isclose(float(score[0]), 0.0)


def test_tarantula_known_textbook_value() -> None:
    """ef=2, ep=1, nf=1, np_=3 ⇒ (2/3) / (2/3 + 1/4) = (2/3) / (11/12) = 8/11."""
    score = tarantula(_arr([2]), _arr([1]), _arr([1]), _arr([3]))
    assert math.isclose(float(score[0]), 8.0 / 11.0)


def test_tarantula_bounded_in_unit_interval() -> None:
    """Tarantula scores must always be in [0, 1] (provable bound)."""
    score = tarantula(
        _arr([3, 2, 1, 0, 5]),
        _arr([0, 5, 1, 0, 2]),
        _arr([0, 1, 2, 3, 0]),
        _arr([5, 0, 4, 5, 3]),
    )
    assert all(0.0 <= s <= 1.0 for s in score)


def test_tarantula_pure_failing_score_is_one() -> None:
    """A location touched only by failing tests has Tarantula score 1.0.

    ef=3, ep=0, nf=0, np_=5 ⇒ (3/3) / (3/3 + 0/5) = 1.0 / 1.0 = 1.0.
    """
    score = tarantula(_arr([3]), _arr([0]), _arr([0]), _arr([5]))
    assert math.isclose(float(score[0]), 1.0)
