"""DStar(*=2) formula unit tests — math correctness on hand-picked vectors.

The S30 (ANA-10) section pins the zero-denominator contract:
``denom == 0 AND ef > 0`` is MAXIMUM suspicion (mathematically +inf),
mapped to a deterministic finite ceiling strictly above every
finite-denominator slot in the same call — never ``0.0`` (the pre-S30
fill, which inverted the ranking for all-fail runs).
"""

from __future__ import annotations

import json
import math

import numpy as np

from novetest.localization.sbfl.dstar import dstar2


def _arr(values: list[int]) -> np.ndarray:
    return np.array(values, dtype=np.int64)


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


# ---------------------------------------------------------------------------
# S30 / ANA-10 — zero-denominator contract.
# ---------------------------------------------------------------------------


def test_dstar2_denom_zero_with_ef_is_maximum_not_zero() -> None:
    """ep+nf == 0 with ef > 0 ⇒ MAXIMUM suspicion, not 0.0.

    Every failing test executed the location AND no passing test did —
    the mathematical D* value is +inf. Pre-S30 this returned 0.0
    (minimum suspicion); this test is the named ANA-10 A/B tripwire at
    the formula layer. Single-slot call: ceiling is 0.0, so the score is
    ``0.0 + ef^2 = 9.0``.
    """
    score = dstar2(_arr([3]), _arr([0]), _arr([0]), _arr([0]))
    assert math.isclose(float(score[0]), 9.0)


def test_dstar2_denom_zero_with_ef_ranks_strictly_above_every_finite_slot() -> None:
    """The ANA-10 all-fail-run inversion scenario, at the vector level.

    Slot 0 = the true bug line (ef=2, ep=0, nf=0 → denom 0). Slots 1-2 =
    noise lines with large finite scores (ef=2/denom=1 → 4.0; ef=1/
    denom=1 → 1.0). Pre-S30 the bug line scored 0.0 — BELOW both noise
    lines. Post-fix it must score strictly above every finite slot.
    """
    score = dstar2(
        _arr([2, 2, 1]), _arr([0, 0, 0]), _arr([0, 1, 1]), _arr([0, 0, 0])
    )
    bug, noise_hi, noise_lo = float(score[0]), float(score[1]), float(score[2])
    assert math.isclose(noise_hi, 4.0)
    assert math.isclose(noise_lo, 1.0)
    assert bug > noise_hi > noise_lo
    # Deterministic mechanism pin: ceiling (max finite = 4.0) + ef^2 (4).
    assert math.isclose(bug, 8.0)


def test_dstar2_denom_zero_with_zero_ef_stays_zero() -> None:
    """ep+nf == 0 with ef == 0 (no failing tests at all) ⇒ 0.0 — the true
    dead-input edge keeps the old guard."""
    score = dstar2(_arr([0]), _arr([0]), _arr([0]), _arr([5]))
    assert math.isclose(float(score[0]), 0.0)


def test_dstar2_denom_zero_slots_order_by_ef_within_class() -> None:
    """Two maximum-suspicion slots keep their natural ef-descending order."""
    score = dstar2(
        _arr([3, 1, 2]), _arr([0, 0, 1]), _arr([0, 0, 1]), _arr([0, 0, 0])
    )
    # Slot 2 is finite (4/2 = 2.0); slots 0/1 are the infinite class.
    assert float(score[0]) > float(score[1]) > float(score[2])


def test_dstar2_denom_zero_scores_are_finite_json_floats() -> None:
    """No inf/nan anywhere — the lifted slots must serialize as plain JSON
    floats (``json.dumps(..., allow_nan=False)`` succeeds)."""
    score = dstar2(
        _arr([500, 1, 0]), _arr([0, 3, 2]), _arr([0, 0, 1]), _arr([0, 2, 2])
    )
    assert bool(np.isfinite(score).all())
    json.dumps([float(s) for s in score], allow_nan=False)


def test_dstar2_is_deterministic() -> None:
    """Two calls on the same vectors produce byte-identical outputs."""
    args = (
        _arr([2, 0, 1, 3]),
        _arr([0, 2, 1, 0]),
        _arr([0, 1, 2, 0]),
        _arr([4, 2, 1, 0]),
    )
    first = dstar2(*args)
    second = dstar2(*args)
    np.testing.assert_array_equal(first, second)
