"""Unit tests for `novetest.coverage.lcov_parser`.

Exercises the LCOV -> `CoverageFactSet` parser against inline LCOV
strings (no cargo subprocess needed). The sample shape mirrors what
``cargo llvm-cov nextest --lcov`` produces in aggregate mode:
``SF:<abs_path>`` ... ``end_of_record`` stanzas with ``DA:<line>,<hits>``
records, optional ``BRDA``/``LF``/``LH``/``BRF``/``BRH`` summaries, and
ignored ``TN``/``FN``/``FNDA``/``FNF``/``FNH`` lines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.lcov_parser import parse_lcov
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.coverage_fact_set import CoverageFactSet
from novetest.models.run_reference import RunReference


_WORKSPACE = Path("/ws/cargo-project")


def _ref() -> RunReference:
    return RunReference(run_id="01LCOV0000000000000000FACT", created_at=1_700_000_000_000)


def _write_lcov(tmp_path: Path, body: str, *, name: str = "coverage.lcov") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _parse(
    tmp_path: Path,
    body: str,
    *,
    workspace_root: Path = _WORKSPACE,
    name: str = "coverage.lcov",
) -> CoverageFactSet:
    lcov_path = _write_lcov(tmp_path, body, name=name)
    return parse_lcov(
        lcov_path,
        run_reference=_ref(),
        engine_name="cargo-test",
        ecosystem="rust",
        workspace_root=workspace_root,
        derived_at=1_700_000_001_000,
    )


# --- §5 case 1: happy path / file count / line counts ------------------------


_THREE_FILE_LCOV = """\
TN:
SF:/ws/cargo-project/src/lib.rs
DA:1,5
DA:2,5
DA:3,0
LF:3
LH:2
end_of_record
SF:/ws/cargo-project/src/arithmetic.rs
DA:4,1
DA:5,1
LF:2
LH:2
end_of_record
SF:/ws/cargo-project/src/classifier.rs
DA:6,3
DA:7,3
DA:8,3
DA:9,0
LF:4
LH:3
end_of_record
"""


def test_happy_path_three_files_with_mixed_coverage(tmp_path: Path) -> None:
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    # File count + per-file line counters.
    assert len(fact_set.files) == 3
    by_path = {f.file_path: f for f in fact_set.files}
    lib = by_path["src/lib.rs"]
    arith = by_path["src/arithmetic.rs"]
    classifier = by_path["src/classifier.rs"]
    assert lib.executed_lines == (1, 2)
    assert lib.missing_lines == (3,)
    assert arith.executed_lines == (4, 5)
    assert arith.missing_lines == ()
    assert classifier.executed_lines == (6, 7, 8)
    assert classifier.missing_lines == (9,)
    # Per-file statement summary counters.
    assert lib.summary.num_statements == 3
    assert lib.summary.covered_statements == 2
    assert classifier.summary.percent_covered == pytest.approx(75.0)
    # Aggregate summary sums per-file totals.
    assert fact_set.summary.num_statements == 9
    assert fact_set.summary.covered_statements == 7
    assert fact_set.summary.missing_statements == 2
    # FactSet provenance fields.
    assert fact_set.engine_name == "cargo-test"
    assert fact_set.ecosystem == "rust"
    assert fact_set.mapping_granularity == "aggregate"
    assert fact_set.derived_at == 1_700_000_001_000
    # cargo-llvm-cov aggregate mode has no per-test attribution.
    for fc in fact_set.files:
        assert fc.line_contexts == {}
        assert fc.excluded_lines == ()


# --- §5 case 2: LF / LH cross-check ------------------------------------------


def test_lf_lh_mismatch_raises(tmp_path: Path) -> None:
    """LF/LH must match the per-file DA-record tallies (safety guard).

    A producer that truncates output mid-block would emit summary
    counters that disagree with DA reality; the parser raises rather
    than silently degrade.
    """
    body = """\
SF:/ws/cargo-project/src/lib.rs
DA:1,1
DA:2,0
LF:7
LH:1
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"LF:7"):
        _parse(tmp_path, body)


def test_lh_mismatch_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/lib.rs
DA:1,1
DA:2,0
LF:2
LH:99
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"LH:99"):
        _parse(tmp_path, body)


# --- §5 case 3: empty file → parse error -------------------------------------


def test_empty_file_raises(tmp_path: Path) -> None:
    with pytest.raises(CoverageJsonParseError, match="empty"):
        _parse(tmp_path, "")


def test_whitespace_only_file_raises(tmp_path: Path) -> None:
    """An LCOV file with only blank lines is not a zero-file report — it
    is a producer that wrote nothing useful. Reject."""
    with pytest.raises(CoverageJsonParseError, match="empty"):
        _parse(tmp_path, "\n\n   \n\n")


# --- §5 case 4: DA without preceding SF → parse error ------------------------


def test_da_without_sf_raises(tmp_path: Path) -> None:
    body = """\
DA:1,5
DA:2,3
"""
    with pytest.raises(CoverageJsonParseError, match=r"'DA:' record outside"):
        _parse(tmp_path, body)


def test_end_of_record_without_sf_raises(tmp_path: Path) -> None:
    body = "end_of_record\n"
    with pytest.raises(CoverageJsonParseError, match=r"'end_of_record' without"):
        _parse(tmp_path, body)


def test_nested_sf_without_end_of_record_raises(tmp_path: Path) -> None:
    """A producer that opens a new SF: before closing the previous one
    is structurally invalid LCOV."""
    body = """\
SF:/ws/cargo-project/src/a.rs
DA:1,1
SF:/ws/cargo-project/src/b.rs
DA:1,1
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"opens before previous"):
        _parse(tmp_path, body)


def test_trailing_sf_block_not_closed_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/a.rs
DA:1,1
"""
    with pytest.raises(CoverageJsonParseError, match=r"not closed"):
        _parse(tmp_path, body)


# --- §5 case 5: absolute → workspace-relative path normalization -------------


def test_absolute_paths_relativized_against_workspace_root(tmp_path: Path) -> None:
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    paths = [f.file_path for f in fact_set.files]
    # All paths are POSIX-style, relative, NOT prefixed with `..` or `/`.
    for p in paths:
        assert not p.startswith("/")
        assert not p.startswith("../")
    assert set(paths) == {"src/lib.rs", "src/arithmetic.rs", "src/classifier.rs"}


# --- §5 case 6: outside-workspace path normalized to ../-prefixed relpath ----


def test_path_outside_workspace_root_normalized_to_relpath_with_forensic_warning(
    tmp_path: Path,
) -> None:
    """Per the 2026-06-08 amendment to decision 2026-05-15
    (outside-workspace path harmonization, scenario A): paths NOT under
    workspace_root are normalized to a ``../``-prefixed POSIX relpath via
    ``os.path.relpath`` — matching the istanbul / cobertura parsers so
    cross-ecosystem consumers see one uniform shape. The original
    absolute ``SF:`` value is preserved in ``metadata['lcov_warnings']``
    for forensic continuity (debuggers can still recover the native
    cargo-llvm-cov string without re-reading the LCOV file). Absolute
    paths in ``file_path`` are a contract violation even for
    outside-workspace cases (decision §6 amend).
    """
    body = """\
SF:/elsewhere/cargo-build-script/generated.rs
DA:1,1
DA:2,0
end_of_record
SF:/ws/cargo-project/src/lib.rs
DA:1,1
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    by_path = {f.file_path: f for f in fact_set.files}
    # The outside path is normalized to a ../-prefixed relpath.
    # Workspace is /ws/cargo-project, outside file is /elsewhere/...
    # os.path.relpath yields ../../elsewhere/cargo-build-script/generated.rs.
    outside_paths = [p for p in by_path if p.startswith("..")]
    assert len(outside_paths) == 1, (
        f"expected exactly one ../-prefixed outside path, got {list(by_path)!r}"
    )
    outside_rel = outside_paths[0]
    assert outside_rel.endswith("elsewhere/cargo-build-script/generated.rs"), (
        f"expected outside path to end with elsewhere/...generated.rs, "
        f"got {outside_rel!r}"
    )
    # No file path is absolute (contract violation under decision §6 amend).
    for p in by_path:
        assert not Path(p).is_absolute(), (
            f"outside-workspace harmonization: no file_path may be "
            f"absolute, got {p!r}"
        )
    # Line counts survive normalization unchanged.
    assert by_path[outside_rel].executed_lines == (1,)
    # The inside path is workspace-relative as usual.
    assert "src/lib.rs" in by_path
    # The warning surfaces in fact-set metadata (forensic continuity)
    # and carries BOTH the original absolute path and the normalized
    # relpath so an operator debugging "why is ../../elsewhere/foo here?"
    # sees the native cargo-llvm-cov string alongside it.
    warnings = fact_set.metadata.get("lcov_warnings")
    assert isinstance(warnings, list)
    assert len(warnings) == 1
    assert "/elsewhere/cargo-build-script/generated.rs" in warnings[0]
    assert outside_rel in warnings[0]
    assert "/ws/cargo-project" in warnings[0]


def test_inside_only_paths_omit_lcov_warnings_metadata(tmp_path: Path) -> None:
    """When no path is outside the workspace, the warnings key is absent
    (do not emit an empty `lcov_warnings: []` — keeps the on-disk
    payload minimal and signals "nothing unusual" by key presence)."""
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    assert "lcov_warnings" not in fact_set.metadata


# --- §5 case 7: BRDA records present → parsed into branch fields -------------


def test_brda_records_present_populate_branch_fields(tmp_path: Path) -> None:
    """When BRDA records are present, executed/missing branches and the
    branch summary counters are populated. The pair surfaced is
    ``(line, branch_index)`` per the module docstring; the
    ``(from_line, to_line)`` semantic from coverage.py does not apply.
    """
    body = """\
SF:/ws/cargo-project/src/branchy.rs
DA:1,5
DA:2,3
DA:3,2
BRDA:2,0,0,3
BRDA:2,0,1,0
BRDA:3,0,0,2
BRDA:3,0,1,-
BRF:4
BRH:2
LF:3
LH:3
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    fc = fact_set.files[0]
    # Branches taken at least once → executed.
    assert fc.executed_branches == ((2, 0), (3, 0))
    # Branches with hits == 0 or hits == "-" → missing.
    assert fc.missing_branches == ((2, 1), (3, 1))
    # File summary branch counters.
    assert fc.summary.num_branches == 4
    assert fc.summary.covered_branches == 2
    assert fc.summary.missing_branches == 2
    # Aggregate summary sums file branch counters.
    assert fact_set.summary.num_branches == 4
    assert fact_set.summary.covered_branches == 2
    # Metadata pins the LCOV-specific branch-arc semantics so downstream
    # consumers don't misinterpret the second integer as a destination line.
    assert fact_set.metadata["branch_arc_semantics"] == "lcov-line-index"


def test_brda_duplicate_triples_aggregate_hits(tmp_path: Path) -> None:
    """Multiple BRDA entries for the same (line, block, branch) sum hits.

    cargo-llvm-cov has been observed to emit per-instantiation
    duplicates for generic functions; once the sum is >0 the branch
    is executed, not missing.
    """
    body = """\
SF:/ws/cargo-project/src/dup.rs
DA:1,1
BRDA:1,0,0,0
BRDA:1,0,0,1
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    fc = fact_set.files[0]
    # Two BRDA rows collapse into one (line, branch_index) pair, in the
    # executed bucket because their hits sum to 1.
    assert fc.executed_branches == ((1, 0),)
    assert fc.missing_branches == ()
    assert fc.summary.num_branches == 1
    assert fc.summary.covered_branches == 1


def test_brf_mismatch_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/branchy.rs
DA:1,1
BRDA:1,0,0,1
BRDA:1,0,1,0
BRF:9
BRH:1
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"BRF:9"):
        _parse(tmp_path, body)


def test_brh_mismatch_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/branchy.rs
DA:1,1
BRDA:1,0,0,1
BRDA:1,0,1,0
BRF:2
BRH:9
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"BRH:9"):
        _parse(tmp_path, body)


# --- §5 case 8: BRDA records absent → branch fields empty (no error) ---------


def test_brda_absent_leaves_branch_fields_empty(tmp_path: Path) -> None:
    """cargo-llvm-cov default output omits BRDA — branches must surface
    as empty tuples and zero summary counts, not raise.

    Cross-references Manual Test's 2026-05-31 sweep (cited in the task
    brief §1) which observed cargo-llvm-cov emitting only ``SF/DA/LF/LH``
    by default.
    """
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    for fc in fact_set.files:
        assert fc.executed_branches == ()
        assert fc.missing_branches == ()
        assert fc.summary.num_branches == 0
        assert fc.summary.covered_branches == 0
        assert fc.summary.missing_branches == 0
    assert fact_set.summary.num_branches == 0


# --- §5 case 9: ignored records pass through silently ------------------------


def test_function_and_test_name_records_are_ignored(tmp_path: Path) -> None:
    """TN / FN / FNDA / FNF / FNH records are LCOV-valid but FileCoverage
    has no per-function slot; the parser tolerates them silently."""
    body = """\
TN:
SF:/ws/cargo-project/src/funcs.rs
FN:1,add
FN:5,subtract
FNDA:3,add
FNDA:2,subtract
FNF:2
FNH:2
DA:1,3
DA:2,3
DA:5,2
DA:6,2
LF:4
LH:4
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    fc = fact_set.files[0]
    assert fc.executed_lines == (1, 2, 5, 6)
    assert fc.missing_lines == ()
    # Function records leave NO trace on the on-disk fact set.
    serialized = fact_set.to_dict()
    assert "FN" not in str(serialized)
    assert "FNDA" not in str(serialized)


def test_unknown_records_skipped_silently(tmp_path: Path) -> None:
    """An unknown KEY:value record (LCOV is extensible) must not raise.

    Future producers may add their own keys; the parser is forward-
    compatible.
    """
    body = """\
SF:/ws/cargo-project/src/lib.rs
XX:future-extension-value
DA:1,1
DA:2,1
LF:2
LH:2
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    assert fact_set.files[0].executed_lines == (1, 2)


def test_blank_and_comment_lines_skipped(tmp_path: Path) -> None:
    """Blank lines and `# ...` comments are tolerated anywhere."""
    body = """\
# generated by cargo-llvm-cov

SF:/ws/cargo-project/src/lib.rs

DA:1,1
# uncovered branch:
DA:2,0
LF:2
LH:1
end_of_record

"""
    fact_set = _parse(tmp_path, body)
    fc = fact_set.files[0]
    assert fc.executed_lines == (1,)
    assert fc.missing_lines == (2,)


# --- §5 case 10: deterministic file ordering (sort by file_path) -------------


def test_files_sorted_by_workspace_relative_path(tmp_path: Path) -> None:
    """Sorted file order keeps `coverage_facts.json` byte-deterministic.

    The LCOV input here emits files in z->a order; the parser must
    re-sort.
    """
    body = """\
SF:/ws/cargo-project/src/zzz.rs
DA:1,1
end_of_record
SF:/ws/cargo-project/src/mmm.rs
DA:1,1
end_of_record
SF:/ws/cargo-project/src/aaa.rs
DA:1,1
end_of_record
"""
    fact_set = _parse(tmp_path, body)
    paths = [f.file_path for f in fact_set.files]
    assert paths == ["src/aaa.rs", "src/mmm.rs", "src/zzz.rs"]


# --- additional safety: malformed numeric fields -----------------------------


def test_da_non_integer_line_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/a.rs
DA:NaN,5
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"non-integer"):
        _parse(tmp_path, body)


def test_brda_non_integer_field_raises(tmp_path: Path) -> None:
    body = """\
SF:/ws/cargo-project/src/a.rs
BRDA:1,foo,0,1
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"non-integer"):
        _parse(tmp_path, body)


def test_brda_wrong_field_count_raises(tmp_path: Path) -> None:
    """BRDA needs exactly 4 comma-separated fields."""
    body = """\
SF:/ws/cargo-project/src/a.rs
BRDA:1,0,0
end_of_record
"""
    with pytest.raises(CoverageJsonParseError, match=r"exactly 4 fields"):
        _parse(tmp_path, body)


def test_round_trips_through_frozen_on_disk_schema(tmp_path: Path) -> None:
    """The fact set must survive `to_dict` -> `from_dict` (frozen schema)."""
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    restored = CoverageFactSet.from_dict(fact_set.to_dict())
    assert restored == fact_set


def test_metadata_carries_coverage_format_marker(tmp_path: Path) -> None:
    """Downstream tooling can identify the producer format from metadata."""
    fact_set = _parse(tmp_path, _THREE_FILE_LCOV)
    assert fact_set.metadata["coverage_format"] == "lcov"
