"""Workspace anchor resolution for the anchored-pin model (D2 / D3 / D6).

Implements the orchestration-side mechanics of
``agent-comms/decisions/2026-07-03-engine-selection-policy.md``:

- **D2** — every verb resolves its workspace by walking *upward* from cwd
  to the nearest ``.novetest/`` (``resolve_workspace``, wrapping Memory's
  ``locate_project_store`` / ``find_nearest_store``). No verb ever scans
  downward; no verb ever guesses an engine.
- **D6** — a pre-pin (legacy) store is migrated lazily, but ONLY on an
  *execution* verb (``run`` / ``test``), which is the sole context that
  needs an engine to dispatch on. The migration lives entirely in
  ``resolve_execution_engine``: one unambiguous engine choice at the anchor
  backfills the pin silently; an ambiguous anchor raises
  ``EngineAmbiguousError`` instructing an explicit
  ``novetest init --engine <name>`` re-pin. ``resolve_workspace`` — the seam
  every verb (read AND execution) routes through — deliberately does NOT
  migrate: read-only verbs proceed engine-less over a legacy store with
  ZERO writes and never hard-fail on ambiguity (S19 seam split; Gate-1
  D1=A / D2=A, 2026-07-20). Legacy stores get pinned on their next
  execution verb, not on a read.
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

from dataclasses import dataclass
from pathlib import Path

from novetest.memory import ProjectStore, locate_project_store
from novetest.memory.project_store import set_pinned_engine
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


class WorkspaceEngineUndetectedError(EngineNotReadyError):
    """Markerless anchor on an execution verb: nothing to dispatch on.

    Raised ONLY by ``resolve_execution_engine`` when a pin-less (legacy)
    store's anchor directory has no engine marker at all — the one place
    on the run/test path that can honestly distinguish "no marker at all"
    from the run engine's per-engine readiness verdicts ("marker/pin
    present, engine not operable" → ``engine-missing`` /
    ``engine-misconfigured``). The CLI maps this subclass to the D7
    standard error code ``no-engine-detected`` (exit 4), matching what
    ``init`` and ``reset`` already emit for a markerless directory
    (W1/S8, ORC-23).

    Subclasses ``EngineNotReadyError`` so direct workflow-API callers that
    only know the run engine's exception surface keep working unchanged.
    The carried readiness stays within the run contract's three-state
    vocabulary (``state="engine-missing"``) — the D7 code is a CLI-layer
    classification, not a fourth readiness state.
    """


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
    the ``NOVETEST_HOME`` short-circuit used by hermetic tests) and returns
    the located store as-is. Returns ``None`` when no store exists on the
    walk — the CLI surfaces the existing ``uninitialized`` error. Propagates
    ``ProjectStoreCorruptError`` unchanged (a broken store must error
    loudly, never be silently shadowed).

    This is a PURE resolution seam: it performs NO engine detection, NO pin
    backfill, and raises NO ``EngineAmbiguousError`` (S19 seam split; Gate-1
    D1=A / D2=A, 2026-07-20). A legacy pre-pin store therefore flows back to
    the caller with ``pinned_engine is None``, and read-only verbs answer
    from it engine-less and side-effect-free — a legacy store is never
    written to on a read. The D6 migration (silent single-choice backfill
    or the ambiguous-anchor ``EngineAmbiguousError``) is deferred to
    ``resolve_execution_engine``, which the execution verbs (``run`` /
    ``test``) call — the only context that actually needs an engine to
    dispatch on, and so the only context that pins a legacy store.

    Kept ``async`` (though it now awaits nothing) so its signature is stable
    for the many callers that ``await`` it and for any future resolution
    work that legitimately needs I/O.
    """

    return locate_project_store(cwd)


async def resolve_execution_engine(
    store: ProjectStore, override: tuple[str, str] | None
) -> tuple[str, str]:
    """Pick the ``(ecosystem, engine_name)`` pair an execution verb dispatches on (D3).

    A transient ``--engine`` override wins WITHOUT re-pinning; otherwise the
    store pin governs. This is THE (and only) D6 migration site since the
    S19 seam split (D1=A / D2=A): ``resolve_workspace`` no longer migrates,
    so a legacy pin-less store now reaches this helper unpinned on every
    execution verb (not just direct workflow-API callers). When there is no
    pin, engine detection runs at the anchor — one unambiguous choice
    backfills the pin via ``set_pinned_engine`` and proceeds; ambiguity
    raises ``EngineAmbiguousError`` (the CLI maps it to ``engine-ambiguous``
    at exit 2). So a legacy store gets pinned on its next ``run`` / ``test``,
    never on a read. ``run`` / ``test`` call this before any subprocess
    spawns, so the ambiguity surfaces without executing anything.

    A store with no pin AND no engine choice (markerless anchor) cannot
    execute anything: raise ``WorkspaceEngineUndetectedError`` (an
    ``EngineNotReadyError`` subclass) with a synthetic ``engine-missing``
    readiness — the CLI maps the subclass to the D7 ``no-engine-detected``
    envelope at exit 4 (W1/S8, ORC-23).
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
    raise WorkspaceEngineUndetectedError(
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


def _has_all_dots_component(candidate: Path) -> bool:
    """True when any component of ``candidate`` consists solely of dots.

    ``...`` (go's package wildcard) and longer dot runs are engine-native
    pattern syntax, never filesystem names novetest should resolve. ``.``
    never survives ``Path`` parsing and ``..`` is genuine parent
    navigation, so neither triggers.
    """

    return any(part != ".." and set(part) == {"."} for part in candidate.parts)


def _lexical_relative_key(path_part: str, candidate: Path) -> str:
    """Filesystem-independent canonical key for a relative, non-all-dots target (D3, S20).

    Segment-wise lexical canonicalization: ``Path`` parsing already drops
    ``.`` segments and trailing slashes and normalizes separators, so this
    only has to collapse ``<seg>/..`` pairs. The result is the SAME key the
    former existing-subpath branch produced when the path existed — but with
    no ``exists()`` probe, so on-disk existence and spelling
    (``a/../b`` vs ``b``, ``./sub`` vs ``sub``) no longer fracture a target's
    baseline series (ORC-10).

    Only exact ``.`` / ``..`` path SEGMENTS are special: an embedded-dot
    token like ``foo..bar`` (a jest-style pattern) is one segment and passes
    through untouched. A path that collapses to the anchor itself (a bare
    ``.`` or ``a/..``) keys as ``"."`` — the canonical current-directory form
    the pre-S20 branch produced for a literal ``.`` target. When the collapse
    still leaves a leading ``..`` the expression escapes the anchor and
    cannot be a workspace-relative key — return ``path_part`` verbatim,
    matching the pre-S20 pass-through for such inputs.
    """

    segments: list[str] = []
    for part in candidate.parts:
        if part == ".." and segments and segments[-1] != "..":
            segments.pop()
        else:
            segments.append(part)
    if not segments:
        return "."
    if segments[0] == "..":
        return path_part
    return "/".join(segments)


def normalize_target_expression(target_expression: str, anchor: Path) -> str:
    """Normalize an explicit target to anchor-relative canonical POSIX form (D3).

    Canonicalization rules:

    - empty / whitespace → ``""`` (workspace scope at the anchor — bare
      invocations are total regardless of the invoking subdirectory);
    - an absolute path → relativized against the anchor
      (``to_workspace_relative_posix``, never-absolute on every platform);
    - a relative path with an all-dots component (go's ``./...`` wildcard
      family) → verbatim, decided lexically and NEVER probed: stripping the
      ``./`` prefix would rewrite go's current-dir-recursive ``./...`` into
      all-packages-recursive ``...``, and Win32 strips trailing dots from
      path components — so the all-dots family is settled here, ahead of the
      lexical canonicalizer, and the filesystem is never consulted (the
      2026-07-04 windows-latest CI red stays fixed);
    - any other relative path → its filesystem-INDEPENDENT lexical canonical
      key (``_lexical_relative_key``): drop ``.`` segments, strip ``./``
      prefixes and trailing slashes, normalize separators to POSIX, and
      collapse ``<seg>/..`` pairs, so ``./tests/test_x.py`` ≡
      ``tests/test_x.py`` and ``a/../b`` ≡ ``b`` — one baseline series per
      ask regardless of on-disk existence (ORC-10). Engine-native patterns
      still pass through structurally (only exact ``.`` / ``..`` segments are
      touched); a path whose collapse escapes the anchor (leading ``..``)
      is returned verbatim.

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
    elif _has_all_dots_component(candidate):
        normalized = path_part
    else:
        normalized = _lexical_relative_key(path_part, candidate)
    return f"{normalized}{sep}{node_part}" if sep else normalized
