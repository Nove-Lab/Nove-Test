"""Divergence guard for the ``FAIL_LIKE_OUTCOMES`` single source of truth.

XCT-05 (M) was a slow-motion breakage: the predicate "is this outcome a
fail-like outcome?" was defined independently at 8 sites, and 3 of them had
already drifted apart — ``fact_bundle._is_fail_outcome`` accepted a singular
``"error"``, and the two CLI renderers accepted ``"error"`` / ``"fail"`` that
no other site did. S25 (correction C6) collapses the definition to a single
frozenset in ``novetest.models`` and points every consumer at it.

The drift is UNREACHABLE for real data today (the normalizer never emits
singular ``"error"`` or ``"fail"`` — dotnet normalizes ``error -> errored``),
so this is a prevention-only cleanup: these guards make a future re-fork a
LOUD, deliberate test edit rather than a silent divergence.

Pattern replicated from
``tests/unit/localization/test_engine_support_divergence.py`` (pin a canonical
set, assert every consumer references it, fail loudly on re-fork) and
``tests/unit/run/test_engine_selector.py`` (the two-priority-lists bug guard).
"""

from __future__ import annotations

from novetest.cli.renderers import _format
from novetest.cli.renderers import run as run_renderer
from novetest.cli.renderers._format import GLYPH_FAIL, GLYPH_UNAVAILABLE, run_status_glyph
from novetest.localization import derive, failure_proximity, retrieval
from novetest.models import FAIL_LIKE_OUTCOMES
from novetest.orchestration.recommendation import fact_bundle
from novetest.regression import compare
from novetest.replay import classifier


# The documented ``TestResult.outcome`` vocabulary (test_result.py docstring
# ~line 24). Intentionally NOT enum-locked in production, so it is pinned here
# to keep the SSoT alignment check honest. Note: NO singular "error", NO "fail".
_CANONICAL_OUTCOME_VOCABULARY: frozenset[str] = frozenset(
    {"passed", "failed", "skipped", "xfailed", "xpassed", "errored"}
)

# Every module that consumes the fail-like set, keyed to the module-level
# attribute that MUST resolve to the SSoT object. A contributor who re-declares
# ``frozenset({"failed", ...})`` locally (re-forking the definition) breaks the
# identity assertion below.
_CONSUMERS: tuple[tuple[str, object, str], ...] = (
    ("novetest.regression.compare", compare, "_FAIL_LIKE"),
    ("novetest.replay.classifier", classifier, "_FAILED_TEST_OUTCOMES"),
    ("novetest.localization.retrieval", retrieval, "_FAILED_OUTCOMES"),
    ("novetest.localization.derive", derive, "_FAILED_OUTCOMES"),
    ("novetest.localization.failure_proximity", failure_proximity, "_FAILED_OUTCOMES"),
    ("novetest.orchestration.recommendation.fact_bundle", fact_bundle, "FAIL_LIKE_OUTCOMES"),
    ("novetest.cli.renderers._format", _format, "_FAIL_STATUSES"),
    ("novetest.cli.renderers.run", run_renderer, "_FAILED_OUTCOMES"),
)


def test_ssot_value_is_pinned() -> None:
    """The vocabulary is exactly ``{"failed", "errored"}``.

    A future vocabulary change is then a loud, deliberate edit to THIS line —
    which forces a contributor to re-read the C6 membership decision.
    """
    assert FAIL_LIKE_OUTCOMES == frozenset({"failed", "errored"})


def test_ssot_aligns_with_canonical_outcome_vocabulary() -> None:
    """The fail-like set is a subset of the documented outcome vocabulary and
    excludes the drifted spellings ``"error"`` / ``"fail"`` (correction C6).

    Singular ``"error"`` and ``"fail"`` are DELIBERATELY excluded: the
    normalizer never emits them (dotnet maps ``error -> errored``), so
    including them only invited the XCT-05 drift.
    """
    assert FAIL_LIKE_OUTCOMES <= _CANONICAL_OUTCOME_VOCABULARY, (
        "FAIL_LIKE_OUTCOMES must be a subset of the documented TestResult "
        "outcome vocabulary (models/test_result.py) — a member outside it is "
        "an outcome no engine emits"
    )
    assert "error" not in FAIL_LIKE_OUTCOMES, (
        "singular 'error' must stay excluded (correction C6): the normalizer "
        "maps error -> errored, so 'error' is the XCT-05 drift spelling"
    )
    assert "fail" not in FAIL_LIKE_OUTCOMES, (
        "singular 'fail' must stay excluded (correction C6): no adapter emits "
        "it; it was a CLI-renderer drift spelling"
    )


def test_every_consumer_resolves_the_ssot_object() -> None:
    """Each consumer module binds the SSoT OBJECT (identity), not a re-declared
    literal — so a re-fork of ``frozenset({"failed", ...})`` FAILS this test.
    """
    for module_path, module, attr in _CONSUMERS:
        resolved = getattr(module, attr, None)
        assert resolved is FAIL_LIKE_OUTCOMES, (
            f"{module_path}.{attr} does not resolve the fail-like SSoT object — "
            f"import FAIL_LIKE_OUTCOMES from novetest.models; do not redeclare "
            f"(got {resolved!r})"
        )


def test_fact_bundle_predicate_rejects_the_xct05_drift() -> None:
    """``_is_fail_outcome`` (site 6, the resolved XCT-05 drift) accepts the
    canonical vocabulary and REJECTS singular ``"error"`` / ``"fail"``.

    Pre-fix the inline literal was ``{"failed", "error", "errored"}`` — this
    behavioral pin is the A/B proof the drift is closed. Real data (``failed``
    / ``errored``) still fires the fail-like path, so no recommendation output
    changes for any run an adapter can actually produce.
    """
    assert fact_bundle._is_fail_outcome("failed") is True
    assert fact_bundle._is_fail_outcome("errored") is True
    assert fact_bundle._is_fail_outcome("FAILED") is True  # case-normalized
    assert fact_bundle._is_fail_outcome("error") is False  # the dropped drift
    assert fact_bundle._is_fail_outcome("fail") is False
    assert fact_bundle._is_fail_outcome("passed") is False


def test_run_status_glyph_rejects_the_drifted_spellings() -> None:
    """``run_status_glyph`` (site 7) maps the canonical statuses to ✗ and the
    dropped ``"error"`` / ``"fail"`` spellings to the neutral — glyph.

    No run record status is ever singular ``"error"`` / ``"fail"`` (the
    normalizer never emits them), so this narrowing changes no real glyph.
    """
    assert run_status_glyph("failed") == GLYPH_FAIL
    assert run_status_glyph("errored") == GLYPH_FAIL
    assert run_status_glyph("error") == GLYPH_UNAVAILABLE  # dropped drift
    assert run_status_glyph("fail") == GLYPH_UNAVAILABLE  # dropped drift
