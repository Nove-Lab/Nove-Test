"""Spectrum-Based Fault Localization (SBFL) primitives.

Public surface for ``localization/sbfl/``:

- ``Spectra`` / ``build_spectra`` — assemble the (tests × statements)
  spectra matrix from a per-test ``CoverageFactSet``.
- ``ochiai`` / ``op2`` / ``dstar2`` / ``tarantula`` — the four pure-math
  formulas. Each takes the four count vectors ``(ef, ep, nf, np_)`` over
  the spectra and returns a ``float64`` array of per-location suspicion
  scores. Design-of-record §1 mandates all four are computed in parallel
  and persisted; the formula choice for ranking is a presentation
  decision (default: Ochiai).

The count-vector computation (``ef`` / ``ep`` / ``nf`` / ``np_`` from
spectra + test outcomes) lives in ``localization.derive``; each formula
module is pure math, free of engine glue.
"""

from novetest.localization.sbfl.dstar import dstar2
from novetest.localization.sbfl.ochiai import ochiai
from novetest.localization.sbfl.op2 import op2
from novetest.localization.sbfl.spectra import (
    Spectra,
    SpectraBuildError,
    build_spectra,
)
from novetest.localization.sbfl.tarantula import tarantula


__all__ = [
    "Spectra",
    "SpectraBuildError",
    "build_spectra",
    "dstar2",
    "ochiai",
    "op2",
    "tarantula",
]
