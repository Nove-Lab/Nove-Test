"""``FORMULA_NAMES`` SSoT + divergence guards (W2/S29, ANA-19).

The four-formula name set used to be replicated 8+ times (six inline
4-tuples in ``derive.py``, the ``FORMULAS`` frozenset in the model, the
dispatch dict in ``_compute_all_formula_scores``). ANA-19's failure
scenario: add/remove a formula, update ``FORMULAS`` (validation passes),
miss a ``derive.py`` replica → the new formula is silently absent from
computed/emitted scores.

Post-S29 there is ONE canonical definition —
``novetest.models.localization_finding.FORMULA_NAMES`` — consumed by
every former replica, plus ONE deliberate remnant: the name→callable
dispatch dict inside ``derive._compute_all_formula_scores`` (a names
tuple cannot carry the callables). This module pins the remnant equal to
the SSoT so the two cannot drift, and pins the SSoT's value/derivations.

Modeled on ``test_engine_support_divergence.py`` (the ANA-02 guard).
"""

from __future__ import annotations

import numpy as np

from novetest.localization.derive import (
    DEFAULT_FORMULA,
    _compute_all_formula_scores,
)
from novetest.models.localization_finding import FORMULA_NAMES, FORMULAS


def test_formula_names_pinned_value_and_order() -> None:
    """The canonical tuple: exact members, exact order (task-brief pin).

    Order is load-bearing for serialized-dict key order in
    ``alternate_scores`` — keep it stable.
    """
    assert FORMULA_NAMES == ("ochiai", "op2", "dstar2", "tarantula")


def test_formulas_frozenset_is_derived_from_formula_names() -> None:
    """``FORMULAS`` (the membership-validation view) must equal the
    frozenset of the canonical tuple — a member added to one but not the
    other fails here."""
    assert FORMULAS == frozenset(FORMULA_NAMES)
    assert len(FORMULA_NAMES) == len(FORMULAS)  # no duplicate names


def test_dispatch_dict_keys_equal_formula_names() -> None:
    """The ONE deliberate replica: ``_compute_all_formula_scores``'s
    name→callable dispatch dict. Its key set AND order must match
    ``FORMULA_NAMES`` — a fifth formula added to the SSoT without a
    dispatch branch (or vice versa) fails here, which is exactly the
    ANA-19 silent-inconsistency scenario."""
    ef = np.array([1, 0], dtype=np.int64)
    ep = np.array([0, 1], dtype=np.int64)
    nf = np.array([0, 1], dtype=np.int64)
    np_ = np.array([1, 0], dtype=np.int64)
    scores = _compute_all_formula_scores((ef, ep, nf, np_))
    assert tuple(scores.keys()) == FORMULA_NAMES


def test_sbfl_package_reexports_the_ssot_object() -> None:
    """``localization.sbfl`` re-exports the SSoT — the very same object,
    not a re-declared copy that could drift."""
    from novetest.localization.sbfl import FORMULA_NAMES as SBFL_FORMULA_NAMES

    assert SBFL_FORMULA_NAMES is FORMULA_NAMES


def test_default_formula_is_a_member() -> None:
    """``DEFAULT_FORMULA`` stays a separate constant (presentation
    default), but it must name a real formula."""
    assert DEFAULT_FORMULA == "ochiai"
    assert DEFAULT_FORMULA in FORMULA_NAMES
