"""DStar SBFL formula (Wong et al. TSE 2014).

``ef^2 / (ep + nf)``  (with the canonical ``*=2`` exponent)

Empirically strongest with many failing tests.

Scale (ANA-20 honesty): the raw D* score is unbounded above and is
serialized AS-IS into ``LocalizationEntry.score_raw`` /
``alternate_scores`` — it is NOT brought into [0, 1] on the wire. Only
the presentation formula's ``score_normalized`` is min-max normalized
at the engine level; alternates stay on this raw, formula-native scale.

Zero-denominator handling (ANA-10). ``denom == 0`` means ``ep == 0 AND
nf == 0`` and — unlike Ochiai, whose zero denominator FORCES ``ef == 0``
— is independent of ``ef``. Two distinct classes:

- ``ef == 0``: no failing test executed the location either (with
  ``nf == 0`` this only occurs when there are no failing tests at all)
  → suspicion ``0.0``.
- ``ef > 0``: NO passing test executed the location AND EVERY failing
  test did — the mathematical D* value is +infinity, i.e. MAXIMUM
  suspicion. Serialized values must stay finite JSON floats, so these
  slots are mapped to a deterministic finite ceiling:
  ``max(finite slot scores in the same call, 0.0) + ef^2``. Because
  ``ef >= 1`` there, every such slot scores STRICTLY ABOVE every
  finite-denominator slot in the same fact set, and slots within the
  infinite class keep their natural ``ef``-descending order.

The pre-2026-07-13 behavior filled these slots with ``0.0`` (minimum
suspicion), inverting the ranking for all-fail runs where the true bug
line is covered by every failing test.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def dstar2(
    ef: NDArray[np.int64],
    ep: NDArray[np.int64],
    nf: NDArray[np.int64],
    np_: NDArray[np.int64],
) -> NDArray[np.float64]:
    """DStar(*=2) suspicion score per location."""
    # ``np_`` is unused — kept for uniform formula signatures.
    del np_

    ef_f = ef.astype(np.float64)
    ep_f = ep.astype(np.float64)
    nf_f = nf.astype(np.float64)
    numer = ef_f * ef_f
    denom = ep_f + nf_f
    result: NDArray[np.float64] = np.divide(
        numer, denom, out=np.zeros_like(numer), where=denom > 0
    )
    # ANA-10: ``denom == 0 AND ef > 0`` is maximum suspicion (see module
    # docstring). Lift those slots to a finite ceiling strictly above
    # every finite-denominator slot in this call.
    max_suspicion = (denom == 0) & (ef_f > 0)
    if bool(max_suspicion.any()):
        ceiling = float(result.max()) if result.size else 0.0
        result[max_suspicion] = ceiling + numer[max_suspicion]
    return result
