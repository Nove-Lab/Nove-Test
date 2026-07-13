"""Op2 SBFL formula (Naish, Lee & Ramamohanarao, TOSEM 2011).

``ef - ep / (ep + np_ + 1)``

Provably maximal under the single-bug assumption.

Scale (ANA-20 honesty): the raw Op2 score is unbounded above (grows
with ``ef``) and can be NEGATIVE — ``ef == 0`` with ``ep > 0`` yields
``-ep / (ep + np_ + 1)`` in ``(-1, 0)``. The raw value is serialized
AS-IS into ``LocalizationEntry.score_raw`` / ``alternate_scores`` — it
is NOT brought into [0, 1] on the wire. Only the presentation formula's
``score_normalized`` is min-max normalized at the engine level;
alternates stay on this raw, formula-native scale.

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
