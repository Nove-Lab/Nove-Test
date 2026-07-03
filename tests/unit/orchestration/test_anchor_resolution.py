"""Unit tests for ``orchestration/anchor_resolution`` (anchored-pin D2/D3/D6).

Pins the three mechanics of ``decisions/2026-07-03-engine-selection-policy.md``
this module owns:

- ``choose_workspace_engine`` — the ONE engine-choice rule shared by ``init``
  (D1) and the D6 migration;
- ``resolve_workspace`` — the verb-level upward walk + lazy pin migration;
- ``resolve_execution_engine`` — D3 pin-by-default / transient-override
  dispatch selection (with the same D6 fallback for direct API callers);
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
# resolve_workspace — D2 walk-up + D6 migration
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


async def test_resolve_backfills_pin_on_legacy_store(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D6: one unambiguous choice → silent backfill, on disk and on handle."""

    _mark_python(workspace)
    create_project_store(workspace)  # legacy: no pin
    _patch_probe(monkeypatch, ready_engines={"pytest"})

    resolved = await resolve_workspace(workspace)
    assert resolved is not None
    assert resolved.pinned_engine is not None
    assert resolved.pinned_engine.to_dict() == {
        "ecosystem": "python",
        "engine_name": "pytest",
    }
    on_disk = get_project_store_state(workspace / ".novetest")
    assert on_disk.pinned_engine is not None
    assert on_disk.pinned_engine.engine_name == "pytest"


async def test_resolve_raises_engine_ambiguous_on_legacy_store(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_python(workspace)
    _mark_go(workspace)
    create_project_store(workspace)
    _patch_probe(monkeypatch, ready_engines={"pytest", "go-test"})

    with pytest.raises(EngineAmbiguousError) as exc_info:
        await resolve_workspace(workspace)
    assert [c.engine_name for c in exc_info.value.candidates] == [
        "pytest",
        "go-test",
    ]
    assert "novetest init --engine" in str(exc_info.value)
    # No pin was written on the ambiguous path.
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


def test_normalize_all_dots_component_never_probes_filesystem(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verbatim decision for all-dots components is purely lexical.

    Win32 strips trailing dots from path components, so an ``exists()``
    probe on ``anchor / '...'`` answers for the anchor itself and rerouted
    go's ``./...`` into the existing-subpath branch (``'...'`` — the
    2026-07-04 windows-latest CI red). A recording spy makes that Windows
    failure shape observable on POSIX: if the fix regresses to consulting
    the filesystem, ``probed`` is non-empty on every platform (a raising
    bomb instead of a spy would INTERNALERROR pytest's own report
    machinery, which also calls ``Path.exists``).
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
    assert probed == []  # never consulted — the decision is lexical


def test_normalize_parent_component_still_probes(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``..`` is parent navigation, not pattern syntax — the all-dots
    lexical guard must not swallow it; the exists-probe path is unchanged."""

    probed: list[Path] = []
    real_exists = Path.exists

    def spy(self: Path) -> bool:
        probed.append(self)
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", spy)
    assert normalize_target_expression("../ghost.py", workspace) == "../ghost.py"
    assert probed  # the probe ran; the path does not exist → verbatim


def test_normalize_nonexistent_path_passes_through(workspace: Path) -> None:
    """No pre-validation: parity with the native engine's own resolution."""

    assert (
        normalize_target_expression("tests/test_ghost.py", workspace)
        == "tests/test_ghost.py"
    )


def test_normalize_empty_path_half_nodeid_passes_through(workspace: Path) -> None:
    """Degenerate ``::test_a`` (no path half) must not collapse to ``.::test_a``."""

    assert normalize_target_expression("::test_a", workspace) == "::test_a"
