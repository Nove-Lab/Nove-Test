"""Parser for JaCoCo XML coverage reports (``jacoco.xml`` /
``jacocoTestReport.xml``).

Internal to the Coverage engine. Consumes the JaCoCo XML file the junit
adapter registers under ``RunRecord.artifact_paths["coverage_xml"]``
and emits a structured ``CoverageFactSet``. This is the junit
counterpart to ``parser.py`` (coverage.py JSON), ``istanbul_parser.py``
(jest's ``coverage-final.json``), and ``lcov_parser.py``
(cargo-llvm-cov LCOV). ``derive.py`` dispatches on ``engine_name``.

JaCoCo XML primer
-----------------

JaCoCo's XML output (DOCTYPE ``-//JACOCO//DTD Report 1.1//EN``) groups
coverage by **package** → **sourcefile** → **line**:

    <report name="...">
      <sessioninfo .../>
      <package name="com/example">
        <class name="com/example/Foo" sourcefilename="Foo.java">
          <method name="bar" desc="..." line="12">
            <counter type="INSTRUCTION" missed="0" covered="5"/>
            <counter type="LINE" missed="0" covered="1"/>
          </method>
          <counter type="LINE" missed="0" covered="3"/>
        </class>
        <sourcefile name="Foo.java">
          <line nr="12" mi="0" ci="5" mb="0" cb="0"/>
          <line nr="13" mi="3" ci="0" mb="0" cb="0"/>
          <line nr="20" mi="0" ci="2" mb="0" cb="2"/>
          <counter type="LINE" missed="1" covered="2"/>
        </sourcefile>
      </package>
      <counter type="LINE" missed="X" covered="Y"/>
    </report>

The ``<sourcefile>`` element is the load-bearing one for our model:
its ``<line>`` children carry per-line execution data (``ci`` =
covered instructions, ``mi`` = missed instructions, ``cb`` = covered
branches, ``mb`` = missed branches). The ``<class>`` element is
informational; we parse only ``<sourcefile>`` and the ``<report>``
roll-up ``<counter>`` elements.

Line is **executed** when ``ci > 0``. Line is **missing** when
``ci == 0`` and ``mi > 0``. The line is omitted from both sets when
both are zero (rare; lines outside any class body, e.g. import-only
spans).

Mapping decisions (junit → frozen-schema)
-----------------------------------------

- ``mapping_granularity = "aggregate"``. JaCoCo with default
  ``forkMode=once`` (Surefire) gives aggregate coverage only — no
  per-test attribution. The brief §6 D1 ratifies aggregate as the v1
  default; ``--per-test-class`` (Surefire ``forkMode=perTestClass``) is
  an opt-in slow mode deferred to a future hardening cycle.

- ``file_path`` is workspace-relative POSIX. The source root convention
  is Maven/Gradle ``src/main/java/<package>/<sourcefile>``; we prepend
  that prefix. For multi-module Maven projects (D2), the parser globs
  every per-module ``target/site/jacoco/jacoco.xml`` under the
  workspace root and prefixes each file's path with its module name
  (e.g. ``moduleA/src/main/java/com/example/Foo.java``).

- ``line_contexts = {}`` always — aggregate granularity has no
  per-test attribution. The Localization engine handles this with the
  ``sbfl_aggregate`` mode degradation.

- ``excluded_lines = ()``. JaCoCo's ``coverage.exclude`` config trims
  source files from the report entirely; there is no per-line
  exclusion concept in the XML output.

- Branches: JaCoCo's per-line ``mb`` / ``cb`` are *counts*, not
  individual branch indices. We synthesize indices ``(nr, i)`` for the
  ``cb`` covered branches and ``(nr, cb + i)`` for the ``mb`` missed
  branches so the surfaced pairs are stable and disjoint. The
  semantic is pinned in
  ``metadata["branch_arc_semantics"] = "jacoco-line-counter-index"``
  so downstream debuggers can disambiguate from LCOV's
  ``"lcov-line-index"`` and coverage.py's ``"(from_line, to_line)"``.

Validation
----------

The parser is strict about XML well-formedness (raises
``CoverageJsonParseError`` from ``parser.py`` so ``derive`` surfaces it
uniformly as ``native-payload-corrupt``) but tolerant about missing
optional attributes (e.g. ``<line>`` with no ``cb``/``mb`` are treated
as zero-branch lines).

- File missing on disk → handled in ``derive``, not here.
- Empty file → raise.
- Malformed XML → raise.
- Unknown root tag → raise.
- Missing ``nr`` / ``ci`` / ``mi`` on ``<line>`` → skip that line
  (defensive — JaCoCo has always emitted these, but new line variants
  in a future schema bump should not abort the whole parse).
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from novetest.coverage import _summary
from novetest.coverage.parser import CoverageJsonParseError
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


# JaCoCo with default Surefire forkMode merges per-test execution data;
# the resulting XML carries no per-test attribution. v1 ships
# ``aggregate``; the ``per-test-class`` opt-in is deferred (brief §6 D1).
_JACOCO_MAPPING_GRANULARITY = "aggregate"


def parse_jacoco_xml(
    xml_paths: Iterable[Path],
    *,
    run_reference: RunReference,
    engine_name: str,
    ecosystem: str,
    workspace_root: Path,
    module_prefix_for: dict[str, str] | None = None,
    derived_at: int | None = None,
) -> CoverageFactSet:
    """Build a ``CoverageFactSet`` from one or more JaCoCo XML files.

    Multi-module Maven workspaces pass multiple paths; each is parsed
    and the resulting ``FileCoverage`` entries are aggregated into a
    single ``CoverageFactSet``. Each ``FileCoverage.file_path`` is
    workspace-relative.

    ``module_prefix_for`` (optional) maps an XML file path string to
    the module name that should prefix every FileCoverage's
    ``file_path``. Used by ``derive._derive_junit_jacoco`` for
    multi-module Maven where each per-module XML's sources live under
    ``<module>/src/main/java/`` rather than the workspace's
    ``src/main/java/``.

    Raises ``CoverageJsonParseError`` on any structural XML problem
    (matching the LCOV / coverage.py parsers' contract so
    ``derive_coverage_facts`` surfaces all engine variants uniformly as
    ``native-payload-corrupt``).
    """

    files: list[FileCoverage] = []
    seen_paths: set[str] = set()
    xml_paths_list = list(xml_paths)
    if not xml_paths_list:
        raise CoverageJsonParseError(
            "parse_jacoco_xml requires at least one JaCoCo XML path"
        )

    for xml_path in xml_paths_list:
        try:
            text = xml_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - derive's path-exists guard catches this first
            raise CoverageJsonParseError(
                f"Could not read JaCoCo XML file {xml_path}: {exc}"
            ) from exc
        if not text.strip():
            raise CoverageJsonParseError(
                f"JaCoCo XML file {xml_path} is empty"
            )

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise CoverageJsonParseError(
                f"Malformed JaCoCo XML in {xml_path}: {exc}"
            ) from exc

        if root.tag != "report":
            raise CoverageJsonParseError(
                f"JaCoCo XML root tag is {root.tag!r}, expected 'report' "
                f"(in {xml_path})"
            )

        prefix = (
            (module_prefix_for or {}).get(str(xml_path))
            if module_prefix_for
            else None
        )

        for package_el in root.findall("package"):
            package_name = package_el.get("name", "")
            for sourcefile_el in package_el.findall("sourcefile"):
                sourcefile_name = sourcefile_el.get("name", "")
                if not sourcefile_name:
                    continue
                rel_path = _build_workspace_relative_path(
                    package_name=package_name,
                    sourcefile_name=sourcefile_name,
                    module_prefix=prefix,
                )
                # If the same file appears under two XMLs (rare; merged
                # multi-module reports), merge by taking the union of
                # executed lines + missing lines. Right now we skip the
                # duplicate to keep the first encountered authoritative
                # — same posture as LCOV's "first SF wins" — and surface
                # the duplicate in metadata if desired by a later
                # consumer.
                if rel_path in seen_paths:
                    continue
                seen_paths.add(rel_path)

                file_coverage = _build_file_coverage(
                    sourcefile_el, file_path=rel_path
                )
                files.append(file_coverage)

    # Deterministic on-disk output (matches LCOV's sort).
    files.sort(key=lambda f: f.file_path)
    summary = _summary.aggregate_summary(files)

    metadata: dict[str, Any] = {
        "coverage_format": "jacoco-xml",
        "branch_arc_semantics": "jacoco-line-counter-index",
        "jacoco_xml_paths": [str(p) for p in xml_paths_list],
    }

    return CoverageFactSet(
        run_reference=run_reference,
        engine_name=engine_name,
        ecosystem=ecosystem,
        mapping_granularity=_JACOCO_MAPPING_GRANULARITY,
        summary=summary,
        files=tuple(files),
        derived_at=(
            derived_at if derived_at is not None else int(time.time() * 1000)
        ),
        metadata=metadata,
    )


# --- internals ---------------------------------------------------------------


def _build_workspace_relative_path(
    *,
    package_name: str,
    sourcefile_name: str,
    module_prefix: str | None,
) -> str:
    """Build the workspace-relative POSIX path for a sourcefile.

    JaCoCo's ``<package name="com/example">`` already uses forward
    slashes; we concatenate with the sourcefile name and prepend the
    Maven/Gradle source-set convention. Multi-module Maven prepends the
    module name.
    """

    body = (
        f"{package_name}/{sourcefile_name}" if package_name else sourcefile_name
    )
    relative = f"src/main/java/{body}"
    if module_prefix:
        return f"{module_prefix}/{relative}"
    return relative


def _build_file_coverage(
    sourcefile_el: ET.Element, *, file_path: str
) -> FileCoverage:
    """Parse one ``<sourcefile>`` element into a ``FileCoverage``."""

    executed_lines: list[int] = []
    missing_lines: list[int] = []
    executed_branches: list[tuple[int, int]] = []
    missing_branches: list[tuple[int, int]] = []

    for line_el in sourcefile_el.findall("line"):
        nr_str = line_el.get("nr")
        ci_str = line_el.get("ci", "0")
        mi_str = line_el.get("mi", "0")
        cb_str = line_el.get("cb", "0")
        mb_str = line_el.get("mb", "0")
        if nr_str is None:
            continue
        try:
            nr = int(nr_str)
            ci = int(ci_str)
            mi = int(mi_str)
            cb = int(cb_str)
            mb = int(mb_str)
        except (TypeError, ValueError):
            # Defensive: skip the bad line rather than abort the whole
            # parse (mirrors the LCOV parser's permissive posture on
            # individual records, strict posture on container structure).
            continue

        if ci > 0:
            executed_lines.append(nr)
        elif mi > 0:
            missing_lines.append(nr)
        # Lines with ci=0 AND mi=0 are non-executable spans (e.g.
        # blank lines, comments) that JaCoCo lists for completeness —
        # excluded from both sets.

        for branch_index in range(cb):
            executed_branches.append((nr, branch_index))
        for branch_index in range(mb):
            missing_branches.append((nr, cb + branch_index))

    summary = _summary.summary_from_counts(
        num_statements=len(executed_lines) + len(missing_lines),
        covered_statements=len(executed_lines),
        num_branches=len(executed_branches) + len(missing_branches),
        covered_branches=len(executed_branches),
    )

    return FileCoverage(
        file_path=file_path,
        executed_lines=tuple(sorted(set(executed_lines))),
        missing_lines=tuple(sorted(set(missing_lines))),
        excluded_lines=(),
        executed_branches=tuple(executed_branches),
        missing_branches=tuple(missing_branches),
        summary=summary,
        line_contexts={},
    )


__all__ = ["parse_jacoco_xml"]
