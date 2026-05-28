"""DStar SBFL formula (Wong et al. TSE 2014).

``ef^2 / (ep + nf)``  (with the canonical ``*=2`` exponent)

Empirically strongest with many failing tests. Unbounded; min-max
normalization at the engine level brings it into [0, 1] for output.
Returns ``0.0`` when the denominator is zero (no passing test executed
the location AND no failing test missed it — the same dead-code edge
case Ochiai's denominator guard catches).
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
    return result
