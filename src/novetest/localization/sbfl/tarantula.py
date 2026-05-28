"""Tarantula SBFL formula (Jones & Harrold).

``(ef/(ef+nf)) / (ef/(ef+nf) + ep/(ep+np_))``

Bounded in [0, 1]. Provably non-optimal vs Ochiai (Xie et al. TOSEM
2013); included for parity with prior tooling.

Two zero-denominator edges are guarded:

1. ``ef + nf == 0`` — no failing tests at all → the failing ratio is
   undefined → suspicion 0.
2. ``ef + nf > 0`` but ``denom == 0`` — happens when both failing and
   passing ratios are zero (only possible if the location is touched by
   zero tests entirely) → suspicion 0.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def tarantula(
    ef: NDArray[np.int64],
    ep: NDArray[np.int64],
    nf: NDArray[np.int64],
    np_: NDArray[np.int64],
) -> NDArray[np.float64]:
    """Tarantula suspicion score per location."""
    ef_f = ef.astype(np.float64)
    ep_f = ep.astype(np.float64)
    nf_f = nf.astype(np.float64)
    np_f = np_.astype(np.float64)

    fail_total = ef_f + nf_f
    pass_total = ep_f + np_f

    # ``np.divide`` with ``where=`` keeps the zero-denominator slots at 0.
    fail_ratio = np.divide(
        ef_f, fail_total, out=np.zeros_like(ef_f), where=fail_total > 0
    )
    pass_ratio = np.divide(
        ep_f, pass_total, out=np.zeros_like(ep_f), where=pass_total > 0
    )

    denom = fail_ratio + pass_ratio
    result: NDArray[np.float64] = np.divide(
        fail_ratio, denom, out=np.zeros_like(fail_ratio), where=denom > 0
    )
    return result
