"""Unit tests for `discover_candidates_below` (D4 bounded downward scan).

Covers: marker detection per ecosystem, the depth-2 bound, the skip list,
early-stop-on-hit, multi-marker ordering, refusal at filesystem root /
home, symlink avoidance, deterministic sorted-by-name traversal, and
POSIX-form path rendering — see
`agent-comms/decisions/2026-07-03-engine-selection-policy.md` D4 and
`src/novetest/orchestration/workflows/discovery.py` for the rules under
test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.orchestration.workflows.discovery import (
    DiscoveredCandidate,
    discover_candidates_below,
)


def _write_marker(directory: Path, filename: str) -> None:
    """Create ``directory`` (with parents) and drop an empty marker file in it."""

    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text("")


@pytest.mark.parametrize(
    ("marker_filename", "ecosystem", "engine_name"),
    [
        ("pyproject.toml", "python", "pytest"),
        ("go.mod", "go", "go-test"),
        ("package.json", "javascript-typescript", "jest"),
        ("Cargo.toml", "rust", "cargo-test"),
    ],
)
def test_direct_child_marker_detected(
    tmp_path: Path, marker_filename: str, ecosystem: str, engine_name: str
) -> None:
    child = tmp_path / "child"
    _write_marker(child, marker_filename)

    result = discover_candidates_below(tmp_path)

    assert result == (DiscoveredCandidate(path="child", ecosystem=ecosystem, engine_name=engine_name),)


def test_grandchild_at_depth_two_is_found(tmp_path: Path) -> None:
    grandchild = tmp_path / "level1" / "level2"
    _write_marker(grandchild, "go.mod")

    result = discover_candidates_below(tmp_path)

    assert result == (DiscoveredCandidate(path="level1/level2", ecosystem="go", engine_name="go-test"),)


def test_great_grandchild_at_depth_three_is_not_found(tmp_path: Path) -> None:
    # level1 and level2 carry no markers of their own, so a genuine
    # depth-bound (not the early-stop rule) is what must suppress level3.
    great_grandchild = tmp_path / "level1" / "level2" / "level3"
    _write_marker(great_grandchild, "go.mod")

    result = discover_candidates_below(tmp_path)

    assert result == ()


def test_skip_list_directories_are_not_scanned(tmp_path: Path) -> None:
    _write_marker(tmp_path / "node_modules", "package.json")
    _write_marker(tmp_path / ".venv", "pyproject.toml")

    result = discover_candidates_below(tmp_path)

    assert result == ()


def test_found_project_root_stops_descent(tmp_path: Path) -> None:
    child = tmp_path / "app"
    _write_marker(child, "pyproject.toml")
    _write_marker(child / "vendor", "go.mod")

    result = discover_candidates_below(tmp_path)

    assert result == (DiscoveredCandidate(path="app", ecosystem="python", engine_name="pytest"),)


def test_two_markers_in_one_directory_yield_two_candidates_in_canonical_order(
    tmp_path: Path,
) -> None:
    child = tmp_path / "polyglot"
    _write_marker(child, "pyproject.toml")
    _write_marker(child, "package.json")

    result = discover_candidates_below(tmp_path)

    assert result == (
        DiscoveredCandidate(path="polyglot", ecosystem="python", engine_name="pytest"),
        DiscoveredCandidate(path="polyglot", ecosystem="javascript-typescript", engine_name="jest"),
    )


def test_empty_tree_returns_empty_tuple_not_none(tmp_path: Path) -> None:
    assert discover_candidates_below(tmp_path) == ()


def test_refusal_at_home_directory_skips_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    # A discoverable marker under the fake home proves refusal happened
    # *before* traversal (a real scan would have found this).
    _write_marker(fake_home / "child", "pyproject.toml")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    result = discover_candidates_below(fake_home)

    assert result is None


def test_refusal_at_filesystem_root_skips_traversal(tmp_path: Path) -> None:
    # The refusal check runs before any traversal, so invoking it on the
    # real filesystem root is safe (no scan is ever performed).
    result = discover_candidates_below(Path(tmp_path.anchor))

    assert result is None


def test_symlinked_directory_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside_target = tmp_path / "outside_target"
    _write_marker(outside_target, "pyproject.toml")

    link = root / "linked"
    try:
        link.symlink_to(outside_target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not supported in this environment")

    result = discover_candidates_below(root)

    assert result == ()


def test_children_are_visited_in_deterministic_sorted_order(tmp_path: Path) -> None:
    _write_marker(tmp_path / "b", "go.mod")
    _write_marker(tmp_path / "a", "pyproject.toml")

    result = discover_candidates_below(tmp_path)

    assert result is not None
    assert [candidate.path for candidate in result] == ["a", "b"]


def test_depth_two_hit_uses_posix_path_form(tmp_path: Path) -> None:
    nested = tmp_path / "services" / "api"
    _write_marker(nested, "go.mod")

    result = discover_candidates_below(tmp_path)

    assert result == (DiscoveredCandidate(path="services/api", ecosystem="go", engine_name="go-test"),)


def test_discovered_candidate_to_dict() -> None:
    candidate = DiscoveredCandidate(path="services/api", ecosystem="go", engine_name="go-test")

    assert candidate.to_dict() == {
        "path": "services/api",
        "ecosystem": "go",
        "engine_name": "go-test",
    }
