"""Unit tests for `novetest.coverage.cobertura_parser`.

The parser converts Coverlet's Cobertura XML report
(``coverage.cobertura.xml``) into a structured ``CoverageFactSet``.
Aggregate-mode only per the amended Coverlet decision §3 (XPlat data
collector path is aggregate-effective-default on Coverlet 6.0.x).
Branch coverage is deferred to a future slice per task brief §2.3.

Two fixture XMLs live at ``tests/fixtures/coverage/cobertura/``:
- ``coverlet_basic.xml`` — single class, 100% covered (the canonical
  ``MathLib.MathOps`` shape from ``dotnet-test-basic-coverage``).
- ``coverlet_partial_coverage.xml`` — multi-class + multi-package,
  with intentionally-uncovered branches that the v1 parser silently
  ignores per §2.3.

Inline XML strings cover the structural error cases (mirroring
``test_jacoco_parser.py``'s ``TestParseJacocoXmlErrors`` posture).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from novetest.coverage.cobertura_parser import parse_cobertura_xml
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.run_reference import RunReference


_RUN_REF = RunReference(run_id="r1", created_at=1)

# Source-of-truth for the fixture XMLs.
_FIXTURES_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "coverage"
    / "cobertura"
)


# --- helpers -----------------------------------------------------------------


def _write_xml(tmp_path: Path, body: str, name: str = "coverage.cobertura.xml") -> Path:
    xml_path = tmp_path / name
    xml_path.write_text(body, encoding="utf-8")
    return xml_path


# Canonical Coverlet shape with parameterized ``<source>`` so tests can
# point the source dir at ``tmp_path`` for in-workspace resolution.
def _coverlet_one_class(source_dir: str, filename: str = "MathLib/MathOps.cs") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="1" branch-rate="1" lines-covered="2" lines-valid="2"
          timestamp="0" version="6.0.2" complexity="0">
  <sources>
    <source>{source_dir}</source>
  </sources>
  <packages>
    <package name="MathLib" line-rate="1" branch-rate="1" complexity="0">
      <classes>
        <class name="MathLib.MathOps" filename="{filename}"
               line-rate="1" branch-rate="1" complexity="0">
          <lines>
            <line number="14" hits="1" branch="false"/>
            <line number="15" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


# --- happy-path parses -------------------------------------------------------


class TestParseCoberturaXmlBasic:
    def test_fixture_coverlet_basic_yields_one_file_fully_covered(
        self, tmp_path: Path
    ) -> None:
        """The committed fixture XML parses to the expected MathOps.cs shape.

        ``<source>`` in the fixture is ``/abs/path/to/workspace`` — NOT
        under ``tmp_path``, so the path-resolution fallback (step 2) fires
        and produces a relpath. The assertion checks the file's basename
        survives the fallback.
        """
        xml_path = _FIXTURES_DIR / "coverlet_basic.xml"
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert fact_set.engine_name == "xunit"
        assert fact_set.ecosystem == "dotnet"
        assert fact_set.mapping_granularity == "aggregate"
        assert len(fact_set.files) == 1
        fc = fact_set.files[0]
        assert fc.file_path.endswith("MathLib/MathOps.cs")
        assert fc.executed_lines == (14, 15)
        assert fc.missing_lines == ()
        assert fc.summary.num_statements == 2
        assert fc.summary.covered_statements == 2
        # Branches deferred per §2.3 — must be empty even when the XML
        # would carry them.
        assert fc.executed_branches == ()
        assert fc.missing_branches == ()
        assert fc.summary.num_branches == 0

    def test_workspace_relative_resolution_via_first_source_dir(
        self, tmp_path: Path
    ) -> None:
        """When ``<source>`` is UNDER workspace_root, the resolved path is
        clean relative POSIX (no ``..`` segments)."""
        # source = tmp_path (the workspace); filename joins under it.
        xml_path = _write_xml(tmp_path, _coverlet_one_class(str(tmp_path)))
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert [f.file_path for f in fact_set.files] == ["MathLib/MathOps.cs"]
        # Forward slashes always, even on Windows.
        assert ".." not in fact_set.files[0].file_path

    def test_outside_workspace_falls_back_to_relpath(self, tmp_path: Path) -> None:
        """When ``<source>`` is OUTSIDE workspace_root, the parser falls
        back to os.path.relpath (mirrors Istanbul parser policy)."""
        outside = tmp_path.parent / "outside-workspace"
        xml_path = _write_xml(
            tmp_path, _coverlet_one_class(str(outside)), name="cov.xml"
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        # relpath form starts with ``..`` to traverse out of tmp_path.
        rel = fact_set.files[0].file_path
        assert rel.startswith("../"), f"expected relpath fallback, got {rel!r}"

    def test_no_sources_block_treats_filename_as_workspace_relative(
        self, tmp_path: Path
    ) -> None:
        """Forward-compat: Cobertura producers that omit ``<sources>``
        get their ``filename`` taken as-is (POSIX-normalized)."""
        xml_path = _write_xml(
            tmp_path,
            """<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="1" lines-covered="1" lines-valid="1">
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="src/calc.py" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert [f.file_path for f in fact_set.files] == ["src/calc.py"]

    def test_no_sources_block_with_backslash_filename_normalizes_to_posix(
        self, tmp_path: Path
    ) -> None:
        """Defensive: a Cobertura producer on Windows might emit
        backslashes in ``filename``; we normalize to POSIX."""
        xml_path = _write_xml(
            tmp_path,
            r"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="1">
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="src\App\Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="3" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert [f.file_path for f in fact_set.files] == ["src/App/Calc.cs"]


class TestParseCoberturaXmlMultiClass:
    def test_fixture_partial_coverage_yields_two_files(self, tmp_path: Path) -> None:
        """The partial-coverage fixture parses to two files (sorted by
        ``file_path``) with the expected line distribution."""
        xml_path = _FIXTURES_DIR / "coverlet_partial_coverage.xml"
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        # Two classes (one per package, both named "MathLib" but distinct
        # classes); sorted by file_path.
        paths = [f.file_path for f in fact_set.files]
        # Both paths end with the expected basenames (the prefix is the
        # relpath fallback since /abs/path/to/workspace is outside tmp_path).
        assert len(paths) == 2
        assert any(p.endswith("MathLib/Classifier.cs") for p in paths)
        assert any(p.endswith("MathLib/MathOps.cs") for p in paths)

        # Classifier: lines 5,9 executed; 8,12 missing.
        classifier = next(f for f in fact_set.files if f.file_path.endswith("Classifier.cs"))
        assert classifier.executed_lines == (5, 9)
        assert classifier.missing_lines == (8, 12)
        assert classifier.summary.num_statements == 4
        assert classifier.summary.covered_statements == 2
        # Branch attrs IGNORED for v1 per §2.3.
        assert classifier.executed_branches == ()
        assert classifier.missing_branches == ()
        assert classifier.summary.num_branches == 0

        # Aggregate: 6 statements, 4 covered, 2 missing.
        assert fact_set.summary.num_statements == 6
        assert fact_set.summary.covered_statements == 4
        assert fact_set.summary.missing_statements == 2
        assert fact_set.summary.percent_covered == pytest.approx(66.67, abs=0.01)

    def test_multi_source_dirs_first_under_workspace_wins(
        self, tmp_path: Path
    ) -> None:
        """When multiple ``<source>`` dirs are declared, the parser picks
        the FIRST one whose joined path falls under workspace_root."""
        # Two sources: one outside tmp_path, one under it. The latter
        # should be preferred even though it's second.
        outside = tmp_path.parent / "outside"
        inside = tmp_path / "src"
        body = f"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="1">
  <sources>
    <source>{outside}</source>
    <source>{inside}</source>
  </sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="App/Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""
        xml_path = _write_xml(tmp_path, body)
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        # The first match-under-workspace wins; the inside source ->
        # src/App/Calc.cs relative.
        assert [f.file_path for f in fact_set.files] == ["src/App/Calc.cs"]


class TestParseCoberturaXmlMetadata:
    def test_metadata_pins_coverage_format_and_branch_arc_semantics(
        self, tmp_path: Path
    ) -> None:
        """The metadata block discriminates Cobertura from other parsers
        AND pins the v1 ``branches-omitted`` semantic per §2.3."""
        xml_path = _write_xml(tmp_path, _coverlet_one_class(str(tmp_path)))
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert fact_set.metadata["coverage_format"] == "cobertura-xml"
        assert fact_set.metadata["branch_arc_semantics"] == "branches-omitted"
        assert fact_set.metadata["cobertura_xml_paths"] == [str(xml_path)]


class TestParseCoberturaXmlEdgeCases:
    def test_class_with_empty_lines_element_yields_empty_file_coverage(
        self, tmp_path: Path
    ) -> None:
        """A class element with ``<lines/>`` (no children) yields a
        FileCoverage with zero lines — valid, not an error."""
        xml_path = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="0" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="Empty">
      <classes>
        <class name="Empty.Class" filename="Empty/Class.cs" line-rate="0" branch-rate="0">
          <lines/>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert len(fact_set.files) == 1
        fc = fact_set.files[0]
        assert fc.executed_lines == ()
        assert fc.missing_lines == ()

    def test_class_missing_filename_is_skipped(self, tmp_path: Path) -> None:
        """A ``<class>`` lacking the ``filename`` attribute is skipped
        rather than aborting the whole parse (defensive — Coverlet
        always emits it but other Cobertura producers may not for
        synthetic classes)."""
        xml_path = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="0.5" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Synthetic" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
          </lines>
        </class>
        <class name="App.Real" filename="App/Real.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="5" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert [f.file_path for f in fact_set.files] == ["App/Real.cs"]

    def test_line_with_non_integer_hits_is_skipped(self, tmp_path: Path) -> None:
        """A malformed ``<line hits="...">`` value skips that line (defensive)."""
        xml_path = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="App/Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
            <line number="2" hits="not-a-number" branch="false"/>
            <line number="3" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        fc = fact_set.files[0]
        # Line 2 silently dropped; 1 and 3 survive.
        assert fc.executed_lines == (1,)
        assert fc.missing_lines == (3,)

    def test_line_with_missing_number_attribute_is_skipped(
        self, tmp_path: Path
    ) -> None:
        xml_path = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="App/Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line hits="1" branch="false"/>
            <line number="5" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
        )
        fact_set = parse_cobertura_xml(
            [xml_path],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        assert fact_set.files[0].executed_lines == (5,)


class TestParseCoberturaXmlErrors:
    def test_no_paths_raises(self) -> None:
        with pytest.raises(CoverageJsonParseError, match="at least one"):
            parse_cobertura_xml(
                [],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=Path("/tmp"),
            )

    def test_empty_xml_raises(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, "")
        with pytest.raises(CoverageJsonParseError, match="empty"):
            parse_cobertura_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=tmp_path,
            )

    def test_whitespace_only_xml_raises(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, "   \n\t\n   ")
        with pytest.raises(CoverageJsonParseError, match="empty"):
            parse_cobertura_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=tmp_path,
            )

    def test_malformed_xml_raises(self, tmp_path: Path) -> None:
        xml_path = _write_xml(tmp_path, "<coverage><packages><package>")
        with pytest.raises(CoverageJsonParseError, match="Malformed"):
            parse_cobertura_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=tmp_path,
            )

    def test_wrong_root_tag_raises(self, tmp_path: Path) -> None:
        # JaCoCo uses <report>; Cobertura must use <coverage>.
        xml_path = _write_xml(
            tmp_path, '<?xml version="1.0"?><report name="not-cobertura"/>'
        )
        with pytest.raises(CoverageJsonParseError, match="root tag"):
            parse_cobertura_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=tmp_path,
            )

    def test_missing_packages_element_raises(self, tmp_path: Path) -> None:
        # <coverage> with only <sources> — no <packages>.
        xml_path = _write_xml(
            tmp_path,
            '<?xml version="1.0"?><coverage><sources/></coverage>',
        )
        with pytest.raises(CoverageJsonParseError, match="<packages>"):
            parse_cobertura_xml(
                [xml_path],
                run_reference=_RUN_REF,
                engine_name="xunit",
                ecosystem="dotnet",
                workspace_root=tmp_path,
            )


class TestParseCoberturaXmlMultiFile:
    def test_multi_file_input_overwrites_same_file_path_last_wins(
        self, tmp_path: Path
    ) -> None:
        """Multi-file inputs (forward-compat per-test mode) where two
        XMLs reference the SAME source file collapse to one
        FileCoverage entry — second XML's entry overwrites the first.

        v1 contract per parser docstring (matches JaCoCo's "first wins"
        posture; the two parsers diverge on tie-break but the practical
        effect for aggregate-only XPlat output is moot — there are no
        duplicates in normal operation)."""
        # Two XMLs both describing App/Calc.cs with different line sets.
        xml_a = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="App/Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="1" hits="1" branch="false"/>
            <line number="2" hits="0" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
            name="a.cobertura.xml",
        )
        xml_b = _write_xml(
            tmp_path,
            f"""<?xml version="1.0"?>
<coverage line-rate="1" branch-rate="0">
  <sources><source>{tmp_path}</source></sources>
  <packages>
    <package name="App">
      <classes>
        <class name="App.Calc" filename="App/Calc.cs" line-rate="1" branch-rate="1">
          <lines>
            <line number="3" hits="1" branch="false"/>
            <line number="4" hits="1" branch="false"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
""",
            name="b.cobertura.xml",
        )

        fact_set = parse_cobertura_xml(
            [xml_a, xml_b],
            run_reference=_RUN_REF,
            engine_name="xunit",
            ecosystem="dotnet",
            workspace_root=tmp_path,
        )
        # b overwrote a; final state shows b's lines.
        assert len(fact_set.files) == 1
        fc = fact_set.files[0]
        assert fc.executed_lines == (3, 4)
        assert fc.missing_lines == ()
