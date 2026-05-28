"""Op2 SBFL formula (Naish, Lee & Ramamohanarao, TOSEM 2011).

``ef - ep / (ep + np_ + 1)``

Provably maximal under the single-bug assumption. Unbounded; min-max
normalization at the engine level brings it into [0, 1] for output.

The ``+ 1`` in the denominator is the published Op2 form (avoids
division-by-zero when a location is touched by zero tests).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def op2(
    ef: NDArray[np.int64],
    ep: NDArray[np.int64],
    nf: NDArray[np.int64],
    np_: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Op2 suspicion score per location."""
    # ``nf`` is unused — kept for uniform formula signatures.
    del nf

    ef_f = ef.astype(np.float64)
    ep_f = ep.astype(np.float64)
    np_f = np_.astype(np.float64)
    return ef_f - ep_f / (ep_f + np_f + 1.0)
