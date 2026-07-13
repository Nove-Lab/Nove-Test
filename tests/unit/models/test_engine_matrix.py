"""Pins for the ``SUPPORTED_ENGINE_PAIRS`` shared domain constant (XCT-13 / S43).

The supported (ecosystem, engine) matrix was promoted from
``run/engine_selector.py`` to ``models/engine_matrix.py`` so Memory's pin
validation no longer imports upward into ``run``. ``run`` still derives its
own equal copy from ``_ENGINE_MARKER_TABLE`` — collapsing that duplication is
routed to the next run-team slice (S11–S14 family); until it lands, the
divergence guard below pins the two tuples EXACTLY equal (order-sensitive:
row order is the REQ-RUN-006 detection priority). Once ``run`` consumes the
models constant directly, the guard naturally degenerates into an identity
check and can be simplified.

Pattern per ``tests/unit/models/test_fail_like_outcomes_ssot.py`` (S25): pin
the canonical value, assert every consumer references the SSoT object.
Tests may import ``run`` freely — the production layering pin lives in
``tests/unit/memory/test_public_surface.py``.
"""

from __future__ import annotations

from novetest.memory import project_store
from novetest.models import SUPPORTED_ENGINE_PAIRS
from novetest.models import engine_matrix
from novetest.run import list_supported_engine_pairs


def test_supported_engine_pairs_value_is_pinned_verbatim() -> None:
    # Order-sensitive verbatim pin (marker-table / REQ-RUN-006 priority
    # order). Extending the matrix is a deliberate, loud edit here + in
    # run's `_ENGINE_MARKER_TABLE` + per the supported-engine-matrix
    # decision's maintenance discipline (PM extends the decision doc).
    assert SUPPORTED_ENGINE_PAIRS == (
        ("python", "pytest"),
        ("javascript-typescript", "jest"),
        ("java", "junit"),
        ("go", "go-test"),
        ("rust", "cargo-test"),
        ("dotnet", "xunit"),
    )


def test_models_constant_matches_run_derived_copy_exactly() -> None:
    # Divergence guard: run/engine_selector.py still derives its own copy
    # from `_ENGINE_MARKER_TABLE`. Exact tuple equality, order-sensitive —
    # marker-table order is meaningful (earlier row wins on a polyglot
    # workspace). Routed residue: the run-side literal collapse belongs to
    # the next run-team slice; this guard pins them equal until then.
    assert SUPPORTED_ENGINE_PAIRS == list_supported_engine_pairs()


def test_public_reexport_is_the_same_object() -> None:
    assert SUPPORTED_ENGINE_PAIRS is engine_matrix.SUPPORTED_ENGINE_PAIRS


def test_memory_pin_validation_consumes_the_ssot_object() -> None:
    # `set_pinned_engine` validates against the module-level import of the
    # models constant (NOT a re-declared local literal, NOT run's copy) —
    # a re-fork breaks this identity assertion loudly.
    assert project_store.SUPPORTED_ENGINE_PAIRS is engine_matrix.SUPPORTED_ENGINE_PAIRS
