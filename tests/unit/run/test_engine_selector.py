"""Unit tests for `novetest.run.engine_selector`.

Since the 2026-07-03 pin-driven-dispatch slice this module is the single
source of truth for marker detection and disambiguation order — the
detection tests (formerly in ``test_readiness.py``) and the divergence
guards live here. Since W2/S16 dispatch itself is pin-driven through
``engine.py``'s ``_ADAPTER_ENTRY_POINTS`` dict (its own divergence guard
lives in ``test_engine.py``); detection order decides only what a pin
CAN name, pinned by first-candidate assertions here.
"""

from __future__ import annotations

from pathlib import Path

from novetest.models import SUPPORTED_ENGINE_PAIRS
from novetest.run import readiness as readiness_module
from novetest.run.engine_selector import (
    _ENGINE_MARKER_TABLE,
    detect_engine_candidates,
    list_supported_engine_pairs,
)


def test_supported_pairs_cover_six_ecosystems() -> None:
    pairs = list_supported_engine_pairs()
    assert ("python", "pytest") in pairs
    assert ("javascript-typescript", "jest") in pairs
    assert ("java", "junit") in pairs
    assert ("go", "go-test") in pairs
    assert ("rust", "cargo-test") in pairs
    assert ("dotnet", "xunit") in pairs
    assert len(pairs) == 6


def test_supported_pairs_are_the_models_ssot_object() -> None:
    """S11 collapse (S43 routing (e)): run no longer derives its own pair
    tuple — `list_supported_engine_pairs()` RETURNS the
    `models.SUPPORTED_ENGINE_PAIRS` domain constant. Identity, not mere
    equality, per the S25/S43 SSoT-consumer pattern: a re-forked local
    copy breaks this loudly."""

    assert list_supported_engine_pairs() is SUPPORTED_ENGINE_PAIRS


def test_marker_table_derived_pairs_equal_models_ssot() -> None:
    """`_ENGINE_MARKER_TABLE` stays the DETECTION source of truth
    (markers + priority). Its (ecosystem, engine) projection must stay
    exactly equal — order-sensitive, row order is the REQ-RUN-006
    priority — to the models pair matrix, or detection and the supported
    list drift apart. Run-side twin of the memory-owned guard in
    `tests/unit/models/test_engine_matrix.py`."""

    derived = tuple(
        (ecosystem, engine_name)
        for ecosystem, engine_name, _ in _ENGINE_MARKER_TABLE
    )
    assert derived == SUPPORTED_ENGINE_PAIRS


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
    """The glob-based detection branch (vs literal marker-file detection
    used by python/javascript/java/go/rust) keeps regression coverage."""

    (tmp_path / "Foo.csproj").write_text("<Project/>", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    pairs = {(c.ecosystem, c.engine_name) for c in candidates}
    assert ("dotnet", "xunit") in pairs


def test_detect_go_candidate_from_gomod(tmp_path: Path) -> None:
    """Ported from the deleted ``test_go_workspace_selects_gotest``:
    a ``go.mod``-only workspace yields go-test as the sole candidate."""

    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    candidates = detect_engine_candidates(tmp_path)
    assert [(c.ecosystem, c.engine_name) for c in candidates] == [("go", "go-test")]


def test_detect_rust_candidate_from_cargo_toml(tmp_path: Path) -> None:
    """Ported from the deleted ``test_rust_workspace_selects_cargo_test``:
    a ``Cargo.toml``-only workspace yields cargo-test as the sole
    candidate."""

    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    candidates = detect_engine_candidates(tmp_path)
    assert [(c.ecosystem, c.engine_name) for c in candidates] == [
        ("rust", "cargo-test")
    ]


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


def test_java_outranks_go_in_detection(tmp_path: Path) -> None:
    """The exact §4.1 mismatch workspace: `pom.xml` + `go.mod`.

    Pre-fix, selection ranked java 3rd while readiness probed go (junit
    ranked 5th in its hand-ordered chain), so Go could be
    readiness-verified while JUnit was dispatched. Detection must rank
    java FIRST here — the first candidate is what a pin created from
    detection dispatches; `test_readiness.py::
    test_assess_and_detection_agree_on_pom_plus_gomod_workspace` pins the
    readiness side of the same workspace. (Ported from the deleted
    ``test_java_outranks_go_in_selection`` at S16.)
    """

    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    first = detect_engine_candidates(tmp_path)[0]
    assert (first.ecosystem, first.engine_name) == ("java", "junit")
