"""Op2 formula unit tests — math correctness on hand-picked vectors."""

from __future__ import annotations

import math

import numpy as np

from novetest.localization.sbfl.op2 import op2


def _arr(values: list[int]) -> np.ndarray:
    return np.array(values, dtype=np.int64)


def test_op2_zero_passes_score_equals_ef() -> None:
    """ep=0, np_=0 ⇒ score = ef - 0/(0+0+1) = ef (max signal)."""
    score = op2(_arr([3, 1, 0]), _arr([0, 0, 0]), _arr([0, 2, 3]), _arr([0, 0, 0]))
    assert np.allclose(score, [3.0, 1.0, 0.0])


def test_op2_no_failures_score_is_negative_or_zero() -> None:
    """ef=0, mixed passes ⇒ score = -ep/(ep+np_+1), all <= 0."""
    score = op2(_arr([0, 0, 0]), _arr([3, 1, 0]), _arr([2, 2, 2]), _arr([0, 2, 3]))
    assert all(s <= 0.0 for s in score)
    # Specifically: 0 - 3/(3+0+1) = -0.75, 0 - 1/(1+2+1) = -0.25, 0 - 0/(0+3+1) = 0.0
    assert math.isclose(float(score[0]), -0.75)
    assert math.isclose(float(score[1]), -0.25)
    assert math.isclose(float(score[2]), 0.0)


def test_op2_known_textbook_value() -> None:
    """ef=2, ep=1, nf=1, np_=3 ⇒ 2 - 1/(1+3+1) = 2 - 0.2 = 1.8."""
    score = op2(_arr([2]), _arr([1]), _arr([1]), _arr([3]))
    assert math.isclose(float(score[0]), 1.8)


def test_op2_pure_failing_coverage_outscores_mixed() -> None:
    """A location hit by all failing + 0 passing outscores a mixed-coverage location."""
    # Location 0: ef=3, ep=0, nf=0, np_=5 → 3 - 0/(0+5+1) = 3.0
    # Location 1: ef=2, ep=5, nf=1, np_=0 → 2 - 5/(5+0+1) ≈ 1.167
    score = op2(_arr([3, 2]), _arr([0, 5]), _arr([0, 1]), _arr([5, 0]))
    assert math.isclose(float(score[0]), 3.0)
    assert float(score[0]) > float(score[1])
