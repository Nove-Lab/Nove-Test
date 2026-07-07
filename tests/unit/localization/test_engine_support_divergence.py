"""Engine-support divergence guards for the failure_proximity surface.

ANA-02 (H) was a SILENT breakage: junit and xunit shipped as the 5th and
6th engines, their normalizers filled ``failure_reference``, but
``resolve_failure_text`` routed neither and ``_ENGINE_REGEX_TABLE`` had
no keys for them — so the default no-coverage Localization path produced
zero findings for those engines with a misleading parse warning, and no
test failed. These guards pin both lists against
``run.list_supported_engine_pairs()`` (the canonical engine SSoT,
``run/engine_selector.py::_ENGINE_MARKER_TABLE``) so a future 7th engine
FAILS TESTS instead of silently degrading.

Pattern replicated from ``tests/unit/run/test_engine_selector.py::
test_readiness_probe_registry_matches_supported_pairs`` (the
two-priority-lists bug guard) with one deliberate relaxation: the
localization tables may be a SUPERSET of the canonical names because the
regex table and the logfile routing set carry the legacy ``"gotest"``
alias on top of canonical ``"go-test"``.
"""

from __future__ import annotations

from pathlib import Path

from novetest.localization import failure_proximity
from novetest.localization.failure_proximity import resolve_failure_text
from novetest.memory.project_store import (
    ProjectStore,
    create_project_store,
    get_project_store_state,
)
from novetest.run import list_supported_engine_pairs


def _canonical_engine_names() -> frozenset[str]:
    return frozenset(engine for _, engine in list_supported_engine_pairs())


def test_engine_regex_table_covers_supported_pairs() -> None:
    """Every canonical engine name has a ``_ENGINE_REGEX_TABLE`` key.

    Without a key the engine falls back to ``_PYTEST_REGEXES`` — a
    silent degradation to "extract anything .py-like", which for
    non-Python engines means near-guaranteed zero findings.
    """
    missing = _canonical_engine_names() - set(failure_proximity._ENGINE_REGEX_TABLE)
    assert missing == frozenset(), (
        f"engines missing from _ENGINE_REGEX_TABLE: {sorted(missing)} — "
        "add a per-engine regex set (see the W1/S7 junit/xunit entries "
        "for the empirical-verification workflow)"
    )


def test_resolve_failure_text_routing_covers_supported_pairs() -> None:
    """Every canonical engine name is routed by ``resolve_failure_text``.

    The three module-level routing sets (inline / logfile / hybrid) are
    the dispatch SSoT; an engine in none of them hits the defensive
    ``return ""`` tail — the exact ANA-02 breakage shape.
    """
    routed = (
        failure_proximity._INLINE_REFERENCE_ENGINES
        | failure_proximity._LOGFILE_REFERENCE_ENGINES
        | failure_proximity._HYBRID_REFERENCE_ENGINES
    )
    missing = _canonical_engine_names() - routed
    assert missing == frozenset(), (
        f"engines not routed by resolve_failure_text: {sorted(missing)} — "
        "add each to exactly one of _INLINE_REFERENCE_ENGINES / "
        "_LOGFILE_REFERENCE_ENGINES / _HYBRID_REFERENCE_ENGINES"
    )


def test_resolve_failure_text_routing_sets_are_disjoint() -> None:
    """An engine in two routing sets would be shadowed by branch order —
    keep the partition honest."""
    inline = failure_proximity._INLINE_REFERENCE_ENGINES
    logfile = failure_proximity._LOGFILE_REFERENCE_ENGINES
    hybrid = failure_proximity._HYBRID_REFERENCE_ENGINES
    assert not (inline & logfile)
    assert not (inline & hybrid)
    assert not (logfile & hybrid)


def _make_store(tmp_path: Path) -> ProjectStore:
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    create_project_store(workspace)
    return get_project_store_state(workspace / ".novetest")


def test_resolve_failure_text_behavioral_probe_every_engine_nonempty(
    tmp_path: Path,
) -> None:
    """Behavioral layer on top of the set-membership guards: with an
    EXISTING per-test log file whose artifact-relative path is the
    ``failure_reference``, every canonical engine resolves to non-empty
    failure text.

    - Inline engines return the reference string itself (non-empty).
    - Logfile engines read the file (non-empty content).
    - Hybrid engines read the file (log-path-first branch).
    - An UNROUTED engine returns ``""`` — which is what this probe
      catches if a 7th engine lands in the selector table without a
      resolve_failure_text branch, even if someone edits the routing
      sets and the dispatch out of sync.
    """
    store = _make_store(tmp_path)
    run_id = "01HFP000000000000000000001"
    relative = "native/failures/probe.log"
    log_path = store.path / "run" / "artifacts" / f"run_{run_id}" / relative
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("probe failure text", encoding="utf-8")

    for engine_name in sorted(_canonical_engine_names()):
        resolved = resolve_failure_text(store, run_id, engine_name, relative)
        assert resolved != "", (
            f"resolve_failure_text returned empty for supported engine "
            f"{engine_name!r} despite an existing log file — the engine "
            "is not routed (ANA-02 regression shape)"
        )
