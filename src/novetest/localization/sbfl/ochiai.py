"""Ochiai SBFL formula.

``ef / sqrt((ef + nf) * (ef + ep))``

Bounded in [0, 1]. The default formula per design-of-record §1
(``design/implementation-plan/localization-strategy.md``) — robust across
single-bug and multi-bug cases; most-replicated baseline in the
literature.

Where for each statement / location, given the per-test spectra:
- ``ef`` = failing tests that executed it
- ``ep`` = passing tests that executed it
- ``nf`` = failing tests that did NOT execute it
- ``np_`` = passing tests that did NOT execute it
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def ochiai(
    ef: NDArray[np.int64],
    ep: NDArray[np.int64],
    nf: NDArray[np.int64],
    np_: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Ochiai suspicion score per location.

    Returns a ``float64`` array shaped like ``ef``. ``denom > 0`` guards
    the zero-denominator case (no failing test executed a location AND no
    passing/failing test executed it either — the location is dead code
    relative to this run); the score is ``0.0`` there.
    """
    # Unused but kept in the signature for uniformity across the four
    # formula modules — callers slot all four into the same dispatch.
    del np_

    ef_f = ef.astype(np.float64)
    denom = np.sqrt((ef_f + nf.astype(np.float64)) * (ef_f + ep.astype(np.float64)))
    # ``np.divide(out=, where=)`` avoids the runtime divide-by-zero warning
    # that ``np.where(cond, a/b, 0)`` triggers (the ``a/b`` is computed
    # unconditionally before ``where`` masks it).
    result: NDArray[np.float64] = np.divide(
        ef_f, denom, out=np.zeros_like(ef_f), where=denom > 0
    )
    return result
