"""Unit tests for ``orchestration/anchor_resolution`` (anchored-pin D2/D3/D6).

Pins the three mechanics of ``decisions/2026-07-03-engine-selection-policy.md``
this module owns:

- ``choose_workspace_engine`` — the ONE engine-choice rule shared by ``init``
  (D1) and the D6 migration;
- ``resolve_workspace`` — the verb-level upward walk. Since the S19 seam split
  (D1=A / D2=A) it is PURE resolution: NO pin backfill, NO
  ``EngineAmbiguousError`` — a legacy store flows back unpinned so read verbs
  proceed engine-less and side-effect-free;
- ``resolve_execution_engine`` — D3 pin-by-default / transient-override
  dispatch selection, and now the SOLE D6 migration site (backfill /
  ambiguous-refusal), reached by the execution verbs (``run`` / ``test``);
- ``normalize_target_expression`` — D3 anchor-relative canonical form.

Engine *detection* runs for real against fabricated marker files (it is
filesystem-only); readiness *probes* are monkeypatched in this module's
namespace so no subprocess ever spawns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import novetest.orchestration.anchor_resolution as anchor_module
from novetest.memory import create_project_store, get_project_store_state
from novetest.memory.project_store import set_pinned_engine
from novetest.orchestration.anchor_resolution import (
    AmbiguousEngines,
    ChosenEngine,
    EngineAmbiguousError,
    WorkspaceEngineUndetectedError,
    choose_workspace_engine,
    normalize_target_expression,
    resolve_execution_engine,
    resolve_workspace,
)
from novetest.run import (
    EngineNotReadyError,
    EngineReadinessResult,
    NativeEngineContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _readiness(state: str, ecosystem: str, engine_name: str) -> EngineReadinessResult:
    return EngineReadinessResult(
        state=state,
        engine_context=(
            NativeEngineContext(ecosystem=ecosystem, engine_name=engine_name)
            if state != "engine-missing"
            else None
        ),
        evidence=(),
        issues=() if state == "ready" else ("stubbed issue",),
    )


def _patch_probe(
    monkeypatch: pytest.MonkeyPatch, ready_engines: set[str]
) -> list[str]:
    """Fake ``probe_engine``: ``ready`` iff the engine name is in the set."""

    probed: list[str] = []

    async def fake_probe(
        _workspace: Path, ecosystem: str, engine_name: str
    ) -> EngineReadinessResult:
        probed.append(engine_name)
        state = "ready" if engine_name in ready_engines else "engine-misconfigured"
        return _readiness(state, ecosystem, engine_name)

    monkeypatch.setattr(anchor_module, "probe_engine", fake_probe)
    return probed


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the walk-up hermetic: no ambient NOVETEST_HOME leaks in."""

    monkeypatch.delenv("NOVETEST_HOME", raising=False)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _mark_python(ws: Path) -> None:
    (ws / "pyproject.toml").write_text("[project]\n", encoding="utf-8")


def _mark_go(ws: Path) -> None:
    (ws / "go.mod").write_text("module example.com/x\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# choose_workspace_engine — the shared D1 rule
# ---------------------------------------------------------------------------


async def test_choose_no_markers_returns_none(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probed = _patch_probe(monkeypatch, ready_engines=set())
    assert await choose_workspace_engine(workspace) is None
    assert probed == []  # nothing to probe


async def test_choose_single_marker_wins_even_when_not_ready(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness is informational for the single-marker case (NFR-RUN-004)."""

    _mark_python(workspace)
    _patch_probe(monkeypatch, ready_engines=set())
    choice = await choose_workspace_engine(workspace)
    assert isinstance(choice, ChosenEngine)
    assert (choice.ecosystem, choice.engine_name) == ("python", "pytest")
    assert choice.readiness.state == "engine-misconfigured"


async def test_choose_two_markers_both_ready_is_ambiguous_in_canonical_order(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})
    choice = await choose_workspace_engine(workspace)
    assert isinstance(choice, AmbiguousEngines)
    assert [(c.ecosystem, c.engine_name) for c in choice.candidates] == [
        ("python", "pytest"),
        ("go", "go-test"),
    ]


async def test_choose_two_markers_single_ready_wins(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness breaks the tie: the only READY candidate is chosen."""

    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines={"go-test"})
    choice = await choose_workspace_engine(workspace)
    assert isinstance(choice, ChosenEngine)
    assert (choice.ecosystem, choice.engine_name) == ("go", "go-test")
    assert choice.readiness.state == "ready"


async def test_choose_two_markers_zero_ready_is_ambiguous_with_all_candidates(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When readiness breaks no tie, novetest cannot pick for the user."""

    _mark_python(workspace)
    _mark_go(workspace)
    _patch_probe(monkeypatch, ready_engines=set())
    choice = await choose_workspace_engine(workspace)
    assert isinstance(choice, AmbiguousEngines)
    assert [c.engine_name for c in choice.candidates] == ["pytest", "go-test"]


# ---------------------------------------------------------------------------
# resolve_workspace — D2 walk-up (pure resolution; NO D6 migration post-S19)
# ---------------------------------------------------------------------------


async def test_resolve_returns_none_without_a_store(workspace: Path) -> None:
    assert await resolve_workspace(workspace) is None


async def test_resolve_pinned_store_skips_detection(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pinned store resolves without any detection or probe (D2: the pin
    governs; run-time detection no longer exists)."""

    _mark_python(workspace)
    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")

    async def must_not_choose(_ws: Path) -> None:
        raise AssertionError("detection ran despite an existing pin")

    monkeypatch.setattr(anchor_module, "choose_workspace_engine", must_not_choose)
    resolved = await resolve_workspace(workspace)
    assert resolved is not None
    assert resolved.pinned_engine is not None
    assert resolved.pinned_engine.engine_name == "pytest"


async def test_resolve_walks_up_from_nested_subdirectory(
    workspace: Path,
) -> None:
    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")
    nested = workspace / "src" / "pkg" / "deep"
    nested.mkdir(parents=True)

    resolved = await resolve_workspace(nested)
    assert resolved is not None
    assert resolved.path == workspace / ".novetest"


async def test_resolve_does_not_backfill_pin_on_legacy_single_marker_store(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S19 (D2=A): ``resolve_workspace`` NEVER backfills — even an unambiguous
    single-marker legacy store flows back unpinned, on disk and on the handle,
    so read verbs stay side-effect-free. The backfill happens later, on the
    next EXECUTION verb (``resolve_execution_engine``)."""

    _mark_python(workspace)
    create_project_store(workspace)  # legacy: no pin

    def must_not_choose(_ws: Path) -> None:
        raise AssertionError("resolve_workspace ran engine detection on a read")

    monkeypatch.setattr(anchor_module, "choose_workspace_engine", must_not_choose)
    resolved = await resolve_workspace(workspace)
    assert resolved is not None
    assert resolved.pinned_engine is None  # handle: still unpinned
    on_disk = get_project_store_state(workspace / ".novetest")
    assert on_disk.pinned_engine is None  # disk: not written


async def test_resolve_does_not_raise_on_legacy_ambiguous_store(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S19 (D1=A): ``resolve_workspace`` no longer raises
    ``EngineAmbiguousError`` on a legacy + ambiguous store — it returns the
    store unpinned so read verbs proceed engine-less (exit 0). The
    ambiguous-refusal moved to ``resolve_execution_engine`` (execution verbs
    only) — see ``test_execution_engine_raises_ambiguous_without_pin``."""

    _mark_python(workspace)
    _mark_go(workspace)
    create_project_store(workspace)

    def must_not_choose(_ws: Path) -> None:
        raise AssertionError("resolve_workspace ran engine detection on a read")

    monkeypatch.setattr(anchor_module, "choose_workspace_engine", must_not_choose)
    resolved = await resolve_workspace(workspace)
    assert resolved is not None
    assert resolved.pinned_engine is None
    # No pin was written — the read path touches nothing.
    assert get_project_store_state(workspace / ".novetest").pinned_engine is None


async def test_resolve_markerless_legacy_store_stays_unpinned(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read-only verbs on a legacy store with no markers still proceed."""

    create_project_store(workspace)
    _patch_probe(monkeypatch, ready_engines=set())
    resolved = await resolve_workspace(workspace)
    assert resolved is not None
    assert resolved.pinned_engine is None


async def test_resolve_honors_novetest_home_short_circuit(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")
    monkeypatch.setenv("NOVETEST_HOME", str(workspace / ".novetest"))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    resolved = await resolve_workspace(elsewhere)
    assert resolved is not None
    assert resolved.path == workspace / ".novetest"


# ---------------------------------------------------------------------------
# resolve_execution_engine — D3 dispatch selection
# ---------------------------------------------------------------------------


async def test_execution_engine_override_wins_without_repinning(
    workspace: Path,
) -> None:
    store = create_project_store(workspace)
    set_pinned_engine(store, "python", "pytest")
    pinned = get_project_store_state(workspace / ".novetest")

    pair = await resolve_execution_engine(pinned, ("go", "go-test"))
    assert pair == ("go", "go-test")
    refreshed = get_project_store_state(workspace / ".novetest")
    assert refreshed.pinned_engine is not None
    assert refreshed.pinned_engine.engine_name == "pytest"  # untouched


async def test_execution_engine_falls_back_to_pin(workspace: Path) -> None:
    store = create_project_store(workspace)
    set_pinned_engine(store, "rust", "cargo-test")
    pinned = get_project_store_state(workspace / ".novetest")
    assert await resolve_execution_engine(pinned, None) == ("rust", "cargo-test")


async def test_execution_engine_migrates_pinless_store_with_marker(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct workflow-API callers get the same D6 backfill the CLI seam does."""

    _mark_python(workspace)
    legacy = create_project_store(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest"})

    assert await resolve_execution_engine(legacy, None) == ("python", "pytest")
    on_disk = get_project_store_state(workspace / ".novetest")
    assert on_disk.pinned_engine is not None
    assert on_disk.pinned_engine.engine_name == "pytest"


async def test_execution_engine_raises_engine_missing_without_pin_or_marker(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = create_project_store(workspace)
    _patch_probe(monkeypatch, ready_engines=set())
    with pytest.raises(EngineNotReadyError) as exc_info:
        await resolve_execution_engine(legacy, None)
    # The markerless branch raises the dedicated subclass so the CLI can
    # emit the D7 `no-engine-detected` code (W1/S8, ORC-23) while the
    # carried readiness stays within run's three-state vocabulary.
    assert isinstance(exc_info.value, WorkspaceEngineUndetectedError)
    assert exc_info.value.readiness.state == "engine-missing"


async def test_execution_engine_raises_ambiguous_without_pin(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _mark_go(workspace)
    legacy = create_project_store(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})
    with pytest.raises(EngineAmbiguousError):
        await resolve_execution_engine(legacy, None)


# ---------------------------------------------------------------------------
# normalize_target_expression — D3 canonical form
# ---------------------------------------------------------------------------


def test_normalize_empty_and_whitespace_stay_workspace_scoped(
    workspace: Path,
) -> None:
    assert normalize_target_expression("", workspace) == ""
    assert normalize_target_expression("   ", workspace) == ""


def test_normalize_existing_relative_path_is_unchanged(workspace: Path) -> None:
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_x.py").write_text("", encoding="utf-8")
    assert (
        normalize_target_expression("tests/test_x.py", workspace)
        == "tests/test_x.py"
    )


def test_normalize_strips_dot_slash_prefix(workspace: Path) -> None:
    """``./tests/test_x.py`` and ``tests/test_x.py`` are ONE ask → one series."""

    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_x.py").write_text("", encoding="utf-8")
    assert (
        normalize_target_expression("./tests/test_x.py", workspace)
        == "tests/test_x.py"
    )


def test_normalize_trailing_slash_directory(workspace: Path) -> None:
    (workspace / "tests").mkdir()
    assert normalize_target_expression("tests/", workspace) == "tests"


def test_normalize_absolute_path_becomes_anchor_relative(workspace: Path) -> None:
    (workspace / "tests").mkdir()
    target = workspace / "tests" / "test_x.py"
    target.write_text("", encoding="utf-8")
    assert normalize_target_expression(str(target), workspace) == "tests/test_x.py"


def test_normalize_nodeid_keeps_node_half_verbatim(workspace: Path) -> None:
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_x.py").write_text("", encoding="utf-8")
    assert (
        normalize_target_expression("./tests/test_x.py::test_a[1-2]", workspace)
        == "tests/test_x.py::test_a[1-2]"
    )


def test_normalize_engine_native_pattern_passes_through(workspace: Path) -> None:
    """go's ``./...`` is not a filesystem path — verbatim, never mangled."""

    assert normalize_target_expression("./...", workspace) == "./..."


def test_normalize_never_probes_the_filesystem(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S20: normalization is purely lexical — it never consults the disk.

    Since ORC-10 the whole function is filesystem-independent (no
    ``exists()`` probe): the all-dots family (``./...``, ``...``,
    ``./sub/...``) is settled ahead of the lexical canonicalizer and the
    rest is collapsed segment-wise. A recording spy on ``Path.exists`` guards
    that invariant on every platform (a raising bomb instead of a spy would
    INTERNALERROR pytest's own report machinery, which also calls
    ``Path.exists``) — and it also pins the removal of the pre-S20 Win32
    hazard where an ``exists()`` probe on ``anchor / '...'`` answered for the
    anchor and rerouted go's ``./...`` into the subpath branch (the
    2026-07-04 windows-latest CI red).
    """

    probed: list[Path] = []
    real_exists = Path.exists

    def spy(self: Path) -> bool:
        probed.append(self)
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", spy)
    assert normalize_target_expression("./...", workspace) == "./..."
    assert normalize_target_expression("...", workspace) == "..."
    assert normalize_target_expression("./sub/...", workspace) == "./sub/..."
    assert normalize_target_expression("tests/test_ghost.py", workspace) == (
        "tests/test_ghost.py"
    )
    assert probed == []  # never consulted — every decision is lexical


def test_normalize_leading_parent_stays_verbatim(workspace: Path) -> None:
    """S20: a path whose collapse escapes the anchor (leading ``..``) is
    verbatim — it cannot be a stable workspace-relative key. Filesystem
    existence is irrelevant (ORC-10)."""

    assert normalize_target_expression("../ghost.py", workspace) == "../ghost.py"
    # Interior ``..`` that over-escapes collapses to a surviving leading
    # ``..`` → still verbatim (the original spelling, uncollapsed).
    assert (
        normalize_target_expression("a/../../b", workspace) == "a/../../b"
    )


def test_normalize_nonexistent_path_passes_through(workspace: Path) -> None:
    """No pre-validation: parity with the native engine's own resolution."""

    assert (
        normalize_target_expression("tests/test_ghost.py", workspace)
        == "tests/test_ghost.py"
    )


def test_normalize_empty_path_half_nodeid_passes_through(workspace: Path) -> None:
    """Degenerate ``::test_a`` (no path half) must not collapse to ``.::test_a``."""

    assert normalize_target_expression("::test_a", workspace) == "::test_a"


# ---------------------------------------------------------------------------
# normalize_target_expression — S20 (ORC-10) filesystem-independent key
# ---------------------------------------------------------------------------


def test_normalize_key_is_independent_of_filesystem_existence(
    workspace: Path,
) -> None:
    """ORC-10: the SAME logical target yields ONE key whether or not it is
    on disk — existence no longer fractures a baseline series.

    ``pkg/../tests/test_x.py`` collapses lexically to ``tests/test_x.py``;
    materializing the real ``pkg/`` and ``tests/test_x.py`` under the anchor
    must not change the key (the pre-S20 existing-subpath branch left the
    ``..`` uncollapsed only when the path happened to exist)."""

    spelled = "pkg/../tests/test_x.py"
    key_when_absent = normalize_target_expression(spelled, workspace)

    (workspace / "pkg").mkdir()
    (workspace / "tests").mkdir()
    (workspace / "tests" / "test_x.py").write_text("", encoding="utf-8")
    key_when_present = normalize_target_expression(spelled, workspace)

    assert key_when_absent == key_when_present == "tests/test_x.py"


def test_normalize_collapses_parent_segments_when_nonexistent(
    workspace: Path,
) -> None:
    """``a/../b`` ≡ ``b`` even when nothing exists — ``<seg>/..`` collapses."""

    assert normalize_target_expression("a/../b", workspace) == "b"
    assert normalize_target_expression("a/b/../c", workspace) == "a/c"


def test_normalize_strips_dot_slash_prefix_when_nonexistent(
    workspace: Path,
) -> None:
    """``./x`` ≡ ``x`` regardless of existence (the existing-path variant is
    pinned separately) — one series per ask."""

    assert normalize_target_expression("./x", workspace) == "x"
    assert normalize_target_expression("./deep/sub/", workspace) == "deep/sub"


def test_normalize_leaves_embedded_dot_tokens_untouched(workspace: Path) -> None:
    """Only exact ``.`` / ``..`` SEGMENTS are special — a jest-style
    ``foo..bar`` token (embedded dots, single segment) passes through."""

    assert normalize_target_expression("foo..bar", workspace) == "foo..bar"
    assert (
        normalize_target_expression("src/foo..bar/spec", workspace)
        == "src/foo..bar/spec"
    )


def test_normalize_anchor_collapse_keys_as_dot(workspace: Path) -> None:
    """A path that collapses to the anchor itself keys as ``"."`` — the
    canonical current-directory form the pre-S20 branch produced for a
    literal ``.`` target (run-engine contract: the verbatim ``.`` survives on
    the record). ``a/..`` collapses to the same anchor form."""

    assert normalize_target_expression(".", workspace) == "."
    assert normalize_target_expression("a/..", workspace) == "."


def test_normalize_nodeid_path_half_collapses_node_half_verbatim(
    workspace: Path,
) -> None:
    """S20 + node id: the path half is lexically canonicalized (even for a
    nonexistent ``..`` spelling); the ``::`` node half is reattached
    unchanged."""

    assert (
        normalize_target_expression("pkg/../tests/test_x.py::test_a[1-2]", workspace)
        == "tests/test_x.py::test_a[1-2]"
    )
