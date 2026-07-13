"""Vocabulary guards for the coverage unavailable-reason tokens (W2/S35, ANA-17).

``KNOWN_REASONS`` once carried ``incomparable-granularity`` — defined,
registered, promised to agents in the docs, and NEVER emitted by any code
path. These guards keep that class of dead token from silently
re-accumulating:

1. An exact-set pin, so the reason vocabulary only changes as a conscious,
   reviewable edit (the agent docs' reason lists ride on this set).
2. A dead-token scan: every ``REASON_*`` constant registered in
   ``KNOWN_REASONS`` must have at least one emit site
   (``reason=REASON_<NAME>``) in a coverage-engine module other than
   ``results.py`` — or be explicitly allowlisted in
   ``_RESERVED_REASON_NAMES`` below. The allowlist is EMPTY today; adding a
   name to it (with a pointer to the decision that reserves the token) is
   the deliberate act this guard forces.

Grep-style source scan over the coverage package — same guard family as
``test_summary_guard.py``'s source-level supplement (W2/S33).
"""

from __future__ import annotations

import re
from pathlib import Path

from novetest.coverage import results

_COVERAGE_SRC_DIR = Path(results.__file__).parent

# KNOWN_REASONS members allowed to have no emit site. Keep empty unless a
# decision explicitly reserves a token for a pinned future slice — document
# the pointer next to the entry.
_RESERVED_REASON_NAMES: frozenset[str] = frozenset()


def _reason_constants() -> dict[str, str]:
    """All ``REASON_*`` string constants defined on ``coverage.results``."""
    constants: dict[str, str] = {}
    for name in dir(results):
        if name.startswith("REASON_"):
            value = getattr(results, name)
            assert isinstance(value, str)
            constants[name] = value
    return constants


def _engine_sources() -> list[Path]:
    """Coverage-engine modules that could emit a reason (all but results.py)."""
    return sorted(
        p for p in _COVERAGE_SRC_DIR.glob("*.py") if p.name != "results.py"
    )


def test_known_reasons_exact_set() -> None:
    """The wire vocabulary is exactly these five tokens — change consciously.

    ``incomparable-granularity`` was removed in W2/S35 (ANA-17, Gate-1 Q3
    Option A): it was never emitted, and the docs promised a refusal that
    could not occur. Growing this set requires a real emit site (next test)
    and matching agent-docs updates.
    """
    assert results.KNOWN_REASONS == frozenset(
        {
            "run-not-found",
            "missing-native-payload",
            "missing-derived-facts",
            "native-payload-corrupt",
            "engine-mismatch",
        }
    )


def test_every_reason_constant_is_registered() -> None:
    """No orphan ``REASON_*`` constants and no raw-string-only members."""
    constant_values = set(_reason_constants().values())
    assert constant_values == set(results.KNOWN_REASONS)


def test_every_known_reason_has_an_emit_site() -> None:
    """Every registered reason is genuinely emitted somewhere in the engine.

    Emit site = ``reason=REASON_<NAME>`` in a coverage module other than
    ``results.py`` (the definition/registration site does not count). A
    token with zero emit sites is dead vocabulary — exactly what ANA-17
    found — unless it is deliberately reserved via
    ``_RESERVED_REASON_NAMES``.
    """
    assert _RESERVED_REASON_NAMES <= set(_reason_constants())

    sources = {path: path.read_text(encoding="utf-8") for path in _engine_sources()}
    assert sources, "coverage package sources not found"

    dead: list[str] = []
    for name, value in _reason_constants().items():
        if name in _RESERVED_REASON_NAMES:
            continue
        pattern = re.compile(rf"reason={name}\b")
        if not any(pattern.search(text) for text in sources.values()):
            dead.append(f"{name} ({value!r})")

    assert not dead, (
        "KNOWN_REASONS member(s) with no emit site in the coverage engine: "
        f"{', '.join(dead)} — either emit the token on a real code path, "
        "remove it (constant + KNOWN_REASONS entry + docs rows), or reserve "
        "it explicitly in _RESERVED_REASON_NAMES with a decision pointer "
        "(W2/S35 dead-token guard, ANA-17)"
    )
