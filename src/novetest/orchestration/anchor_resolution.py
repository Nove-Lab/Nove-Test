"""Workspace anchor resolution for the anchored-pin model (D2 / D3 / D6).

Implements the orchestration-side mechanics of
``agent-comms/decisions/2026-07-03-engine-selection-policy.md``:

- **D2** — every verb resolves its workspace by walking *upward* from cwd
  to the nearest ``.novetest/`` (``resolve_workspace``, wrapping Memory's
  ``locate_project_store`` / ``find_nearest_store``). No verb ever scans
  downward; no verb ever guesses an engine.
- **D6** — a pre-pin (legacy) store is migrated lazily on first contact:
  one unambiguous engine choice at the anchor backfills the pin silently;
  an ambiguous anchor raises ``EngineAmbiguousError`` instructing an
  explicit ``novetest init --engine <name>`` re-pin.
- **D3** — explicit target expressions are normalized to anchor-relative
  canonical POSIX form (``normalize_target_expression``) so the same ask
  from any cwd, in any spelling, lands in one baseline series.

``choose_workspace_engine`` is the ONE engine-choice rule shared by
``init`` (D1) and the D6 migration, so the two flows cannot diverge:

- no marker candidates            → ``None``
- exactly one marker candidate    → chosen (readiness informational,
  NFR-RUN-004: a misconfigured engine never blocks the pin)
- ≥2 candidates, exactly 1 READY  → the ready one is chosen
- ≥2 candidates, ≥2 READY         → ambiguous (the ready ones listed)
- ≥2 candidates, 0 READY          → ambiguous (all marker candidates
  listed — novetest cannot pick for the user when readiness breaks no tie)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from novetest.memory import ProjectStore, locate_project_store
from novetest.memory.project_store import PinnedEngine, set_pinned_engine
from novetest.run import (
    EngineCandidate,
    EngineNotReadyError,
    EngineReadinessResult,
    detect_engine_candidates,
    probe_engine,
)
from novetest.utils import to_workspace_relative_posix


@dataclass(slots=True, frozen=True)
class ChosenEngine:
    """A single unambiguous engine choice for a workspace."""

    ecosystem: str
    engine_name: str
    readiness: EngineReadinessResult


@dataclass(slots=True, frozen=True)
class AmbiguousEngines:
    """Multiple viable engines; the user must pick via ``init --engine``."""

    candidates: tuple[EngineCandidate, ...]


class EngineAmbiguousError(RuntimeError):
    """Raised when D6 migration meets an anchor with no single engine choice.

    Carries the viable ``candidates`` so the CLI can surface them on
    ``data.candidates`` (D7 error code ``engine-ambiguous``). Only the
    migration path raises; ``init`` returns its ambiguity as a value
    (``workflows/init.py``) because for init the ambiguity is an expected
    outcome, not an exceptional one.
    """

    def __init__(self, candidates: tuple[EngineCandidate, ...]) -> None:
        names = ", ".join(c.engine_name for c in candidates)
        super().__init__(
            "This Project Store has no pinned engine and the workspace "
            f"matches multiple engines ({names}). Run "
            "`novetest init --engine <name>` at the workspace root to pin one "
            "(re-pins in place; run history is retained)."
        )
        self.candidates = candidates


async def choose_workspace_engine(
    workspace: Path,
) -> ChosenEngine | AmbiguousEngines | None:
    """Apply the D1 single-choice rule to ``workspace`` (see module docstring).

    ``None`` means "no marker candidates at all" — the caller decides how to
    surface that (``init`` runs the D4 discovery scan; migration proceeds
    unpinned so read-only verbs still work).
    """

    candidates = detect_engine_candidates(workspace)
    if not candidates:
        return None
    if len(candidates) == 1:
        only = candidates[0]
        readiness = await probe_engine(workspace, only.ecosystem, only.engine_name)
        return ChosenEngine(
            ecosystem=only.ecosystem,
            engine_name=only.engine_name,
            readiness=readiness,
        )
    probed = [
        (c, await probe_engine(workspace, c.ecosystem, c.engine_name))
        for c in candidates
    ]
    ready = [(c, r) for c, r in probed if r.state == "ready"]
    if len(ready) == 1:
        chosen, readiness = ready[0]
        return ChosenEngine(
            ecosystem=chosen.ecosystem,
            engine_name=chosen.engine_name,
            readiness=readiness,
        )
    if len(ready) >= 2:
        return AmbiguousEngines(candidates=tuple(c for c, _ in ready))
    return AmbiguousEngines(candidates=candidates)


async def resolve_workspace(cwd: Path) -> ProjectStore | None:
    """Resolve the governing Project Store for a verb invoked at ``cwd`` (D2).

    Walks upward via Memory's ``locate_project_store`` (which also honors
    the ``NOVETEST_HOME`` short-circuit used by hermetic tests). Returns
    ``None`` when no store exists on the walk — the CLI surfaces the
    existing ``uninitialized`` error. Propagates
    ``ProjectStoreCorruptError`` unchanged (a broken store must error
    loudly, never be silently shadowed).

    D6 migration: when the resolved store has no engine pin (created before
    the 2026-07-03 anchored-pin decision), engine detection re-runs at the
    anchor directory — a single choice backfills the pin silently via
    ``set_pinned_engine``; an ambiguous anchor raises
    ``EngineAmbiguousError``; a markerless anchor returns the store
    unpinned (read-only verbs proceed; execution verbs surface
    engine-missing when they find no pin to dispatch on).

    The returned handle always reflects the post-migration pin state, so
    callers may trust ``store.pinned_engine`` without re-reading disk.
    """

    store = locate_project_store(cwd)
    if store is None:
        return None
    if store.pinned_engine is not None:
        return store
    anchor = store.path.parent
    choice = await choose_workspace_engine(anchor)
    if choice is None:
        return store
    if isinstance(choice, AmbiguousEngines):
        raise EngineAmbiguousError(choice.candidates)
    set_pinned_engine(store, choice.ecosystem, choice.engine_name)
    return replace(
        store,
        pinned_engine=PinnedEngine(
            ecosystem=choice.ecosystem, engine_name=choice.engine_name
        ),
    )


async def resolve_execution_engine(
    store: ProjectStore, override: tuple[str, str] | None
) -> tuple[str, str]:
    """Pick the ``(ecosystem, engine_name)`` pair an execution verb dispatches on (D3).

    A transient ``--engine`` override wins WITHOUT re-pinning; otherwise the
    store pin governs. A pin-less handle (a legacy store reached WITHOUT the
    CLI's ``resolve_workspace`` seam — direct workflow-API callers) gets the
    same D6 migration the CLI seam applies: one unambiguous choice backfills
    the pin and proceeds; ambiguity raises ``EngineAmbiguousError``. Both
    layers call the same ``choose_workspace_engine`` rule, so they cannot
    diverge — on the CLI path the store always arrives pinned and this
    fallback is a no-op.

    A store with no pin AND no engine choice (markerless anchor) cannot
    execute anything: raise ``EngineNotReadyError`` with a synthetic
    ``engine-missing`` readiness so the CLI surfaces the same exit-4
    ``engine-engine-missing`` envelope the pre-pin no-engine path produced.
    """

    if override is not None:
        return override
    pin = store.pinned_engine
    if pin is not None:
        return (pin.ecosystem, pin.engine_name)
    choice = await choose_workspace_engine(store.path.parent)
    if isinstance(choice, ChosenEngine):
        set_pinned_engine(store, choice.ecosystem, choice.engine_name)
        return (choice.ecosystem, choice.engine_name)
    if isinstance(choice, AmbiguousEngines):
        raise EngineAmbiguousError(choice.candidates)
    raise EngineNotReadyError(
        EngineReadinessResult(
            state="engine-missing",
            engine_context=None,
            evidence=(),
            issues=(
                "no engine is pinned for this Project Store and no engine "
                "marker was found at the workspace root; run `novetest init` "
                "there (or `novetest init --engine <name>`) to pin one",
            ),
        )
    )


def normalize_target_expression(target_expression: str, anchor: Path) -> str:
    """Normalize an explicit target to anchor-relative canonical POSIX form (D3).

    Canonicalization rules:

    - empty / whitespace → ``""`` (workspace scope at the anchor — bare
      invocations are total regardless of the invoking subdirectory);
    - an absolute path → relativized against the anchor
      (``to_workspace_relative_posix``, never-absolute on every platform);
    - a relative path that exists under the anchor → its canonical POSIX
      subpath (strips ``./`` prefixes, trailing slashes, and platform
      separators, so ``./tests/test_x.py`` ≡ ``tests/test_x.py`` — one
      baseline series per ask);
    - anything else → verbatim. Engine-native patterns (go's ``./...``)
      and not-yet-existing paths pass through untouched — we do not
      pre-validate, keeping parity with the native engine's own resolution
      rules (same philosophy as ``run/resolve_test_target``).

    ``::``-suffixed node ids (``tests/test_x.py::test_a``) normalize their
    path half and reattach the node half unchanged.
    """

    expression = target_expression.strip()
    if not expression:
        return ""
    path_part, sep, node_part = expression.partition("::")
    if not path_part:
        # Degenerate ``::test_a`` shape: no path half to normalize, and
        # ``Path("")`` collapses to ``"."`` which would mangle it — verbatim.
        return expression
    candidate = Path(path_part)
    if candidate.is_absolute():
        normalized = to_workspace_relative_posix(candidate, anchor)
    elif (anchor / candidate).exists():
        normalized = to_workspace_relative_posix(anchor / candidate, anchor)
    else:
        normalized = path_part
    return f"{normalized}{sep}{node_part}" if sep else normalized
