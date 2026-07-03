"""Unit tests for `novetest.run.engine_selector`.

Since the 2026-07-03 pin-driven-dispatch slice this module is the single
source of truth for marker detection and disambiguation order — the
detection tests (formerly in ``test_readiness.py``) and the divergence
guards live here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.run import readiness as readiness_module
from novetest.run.engine_selector import (
    detect_engine_candidates,
    list_supported_engine_pairs,
    select_native_engine,
)
from novetest.run.errors import EngineNotSupportedError
from novetest.run.types import TestTarget


def test_supported_pairs_cover_six_ecosystems() -> None:
    pairs = list_supported_engine_pairs()
    assert ("python", "pytest") in pairs
    assert ("javascript-typescript", "jest") in pairs
    assert ("java", "junit") in pairs
    assert ("go", "go-test") in pairs
    assert ("rust", "cargo-test") in pairs
    assert ("dotnet", "xunit") in pairs
    assert len(pairs) == 6


def test_python_workspace_selects_pytest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "python"
    assert context.engine_name == "pytest"


def test_unknown_workspace_raises(tmp_path: Path) -> None:
    target = TestTarget("", "workspace", tmp_path)
    with pytest.raises(EngineNotSupportedError):
        select_native_engine(target)


def test_js_workspace_selects_jest(tmp_path: Path) -> None:
    """Phase 2.5: jest is now an implemented adapter, so `package.json`
    workspaces resolve to the jest engine context rather than raising.
    """

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "javascript-typescript"
    assert context.engine_name == "jest"


def test_dotnet_workspace_selects_xunit(tmp_path: Path) -> None:
    """Phase 2.5 sixth-and-last slice: xunit is now an implemented adapter,
    so ``*.csproj`` workspaces resolve to the xunit engine context rather
    than raising. The glob-based detection branch (vs marker-file detection
    used by python/javascript/java/go/rust) is exercised here so the
    selector's two detection paths both have regression coverage.
    """

    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "dotnet"
    assert context.engine_name == "xunit"


def test_go_workspace_selects_gotest(tmp_path: Path) -> None:
    """Phase 3: go-test is now an implemented adapter, so `go.mod`
    workspaces resolve to the go-test engine context rather than raising.
    """

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "go"
    assert context.engine_name == "go-test"


def test_rust_workspace_selects_cargo_test(tmp_path: Path) -> None:
    """Phase 3 (adapter backlog #2): cargo-test is now an implemented
    adapter, so `Cargo.toml` workspaces resolve to the cargo-test engine
    context rather than raising.
    """

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    target = TestTarget("", "workspace", tmp_path)
    context = select_native_engine(target)
    assert context.ecosystem == "rust"
    assert context.engine_name == "cargo-test"


# ---------------------------------------------------------------------------
# detect_engine_candidates — the init-time detection API
# (moved here from test_readiness.py by the 2026-07-03 pin-driven-dispatch
# slice; detection now lives in engine_selector)
# ---------------------------------------------------------------------------


def test_detect_python_candidate_from_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("python", "pytest") in pairs


def test_detect_js_candidate_from_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("javascript-typescript", "jest") in pairs


def test_detect_dotnet_via_csproj_glob(tmp_path: Path) -> None:
    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("dotnet", "xunit") in pairs


def test_detect_dotnet_one_level_csproj_evidence_is_root_relative(
    tmp_path: Path,
) -> None:
    """The canonical library + test split is matched one level deep, with
    root-relative evidence strings so same-basename csprojs at different
    depths stay identifiable downstream."""

    (tmp_path / "MyLib").mkdir()
    (tmp_path / "MyLib" / "MyLib.csproj").write_text("<Project/>", encoding="utf-8")
    (tmp_path / "MyLib.Tests").mkdir()
    (tmp_path / "MyLib.Tests" / "MyLib.Tests.csproj").write_text(
        "<Project/>", encoding="utf-8"
    )
    candidates = detect_engine_candidates(tmp_path)
    assert len(candidates) == 1
    assert candidates[0].evidence == (
        "MyLib.Tests/MyLib.Tests.csproj",
        "MyLib/MyLib.csproj",
    )


def test_detect_empty_workspace_returns_empty(tmp_path: Path) -> None:
    assert detect_engine_candidates(tmp_path) == ()


def test_detect_dual_marker_workspace_returns_both_in_canonical_order(
    tmp_path: Path,
) -> None:
    """A dual-marker workspace yields BOTH candidates, canonical order.

    This is the shape `novetest init` consumes for its D1 ambiguity gate
    (decision 2026-07-03-engine-selection-policy): every matched pair is
    reported; ordering follows the single priority table.
    """

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    assert [(c.ecosystem, c.engine_name) for c in candidates] == [
        ("python", "pytest"),
        ("go", "go-test"),
    ]


def test_detect_all_six_markers_matches_supported_pairs_order(
    tmp_path: Path,
) -> None:
    """A workspace carrying every marker yields all six candidates in
    exactly `list_supported_engine_pairs()` order — detection, selection,
    and the supported list all derive from the one table."""

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    assert tuple((c.ecosystem, c.engine_name) for c in candidates) == (
        list_supported_engine_pairs()
    )


# ---------------------------------------------------------------------------
# Divergence guards — the two-priority-lists bug (question 2026-07-02 §4.1)
# must never come back
# ---------------------------------------------------------------------------


def test_readiness_probe_registry_matches_supported_pairs() -> None:
    """Readiness derives from, not parallels, the selector table.

    The probe registry is an UNORDERED dict keyed by pair; disambiguation
    order exists only in `engine_selector._ENGINE_MARKER_TABLE`. If a pair
    is added to the table without a probe (or vice versa) this guard
    fails before the mismatch can ship.
    """

    assert set(readiness_module._READINESS_PROBES.keys()) == set(
        list_supported_engine_pairs()
    )


def test_java_outranks_go_in_selection(tmp_path: Path) -> None:
    """The exact §4.1 mismatch workspace: `pom.xml` + `go.mod`.

    Pre-fix, `select_native_engine` ranked java 3rd while readiness
    probed go (junit ranked 5th in its hand-ordered chain), so Go could
    be readiness-verified while JUnit was dispatched. Selection must pick
    java here; `test_readiness.py::
    test_assess_and_select_agree_on_pom_plus_gomod_workspace` pins the
    readiness side of the same workspace.
    """

    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    context = select_native_engine(TestTarget("", "workspace", tmp_path))
    assert (context.ecosystem, context.engine_name) == ("java", "junit")
