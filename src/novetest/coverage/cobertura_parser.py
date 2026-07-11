"""Parser for Coverlet Cobertura XML coverage reports (``coverage.cobertura.xml``).

Internal to the Coverage engine. Consumes the Cobertura XML file the
dotnet adapter registers under ``RunRecord.artifact_paths["coverage_xml"]``
and emits a structured ``CoverageFactSet``. This is the .NET counterpart
to ``parser.py`` (coverage.py JSON), ``istanbul_parser.py`` (jest's
``coverage-final.json``), ``lcov_parser.py`` (cargo-llvm-cov LCOV), and
``jacoco_parser.py`` (junit JaCoCo XML). ``derive.py`` dispatches on
``engine_name``.

Cobertura XML primer (Coverlet 6.0.x XPlat output)
--------------------------------------------------

Cobertura's XML output groups coverage by **package** → **class** →
**line** with the source roots advertised in a top-level ``<sources>``
block:

    <coverage line-rate="1" branch-rate="1" lines-covered="2" lines-valid="2"
              timestamp="..." version="..." complexity="...">
      <sources>
        <source>/abs/path/to/MathLib.Tests</source>
        <source>/abs/path/to/MathLib</source>
      </sources>
      <packages>
        <package name="MathLib" line-rate="1" branch-rate="1" complexity="...">
          <classes>
            <class name="MathLib.MathOps" filename="MathOps.cs"
                   line-rate="1" branch-rate="1" complexity="...">
              <methods>
                <method name="Add" signature="..." line-rate="1" ...>
                  <lines>
                    <line number="5" hits="1" branch="false"/>
                  </lines>
                </method>
              </methods>
              <lines>
                <line number="5" hits="1" branch="false"/>
                <line number="9" hits="1" branch="false"/>
              </lines>
            </class>
          </classes>
        </package>
      </packages>
    </coverage>

The ``<class>`` element is the load-bearing one for our model:
- ``filename`` attribute — path to the source file, **relative to one of
  the** ``<source>`` directories. Coverlet emits a single ``<source>``
  set to the common ancestor of all compiled sources; the parser still
  supports multi-``<source>`` lists for forward-compatibility with other
  Cobertura producers (Java's cobertura-coverage, Python's coverage.py
  ``--cov-report=xml``, etc.) that may emit one ``<source>`` per project.
- ``<lines>`` child carries ``<line number=N hits=H branch=B>`` entries.

A line is **executed** when ``hits > 0``. A line is **missing** when
``hits == 0``. Both sets are sorted deduplicated integer sequences.

Path resolution
---------------

For each ``<class>``:

1. Try joining each ``<source>`` directory with the class's ``filename``
   in declared order. Pick the **first** resolved path that lives UNDER
   ``workspace_root`` (``Path.is_relative_to`` succeeds).
2. Failing that, use the FIRST source dir as the best-effort root and
   compute ``os.path.relpath`` against ``workspace_root`` — mirrors the
   Istanbul parser's policy for absolute paths that fall outside the
   workspace. On Windows cross-drive setups ``os.path.relpath`` itself
   raises ``ValueError``; a third drive-stripped POSIX fallback (shared
   helper :func:`._paths.relpath_or_drive_stripped`) catches that case
   so the persisted ``file_path`` is never absolute on any platform.
3. If ``<sources>`` is empty or absent, treat ``filename`` as already
   workspace-relative (some Cobertura producers omit the block).

The resolved string is always **workspace-relative POSIX** (decision
2026-05-15 #6). The parser does NOT check filesystem existence; the
caller (``derive._derive_xunit_cobertura``) post-filters out files that
do not exist on disk per task brief §2.4. This split keeps the parser
pure (XML→model, deterministic, side-effect-free) and pushes IO concerns
to the derive layer where they belong.

Mapping decisions (dotnet → frozen-schema)
------------------------------------------

- ``mapping_granularity = "aggregate"``. Per amended decision
  ``2026-06-03-coverlet-pertestcoverage-key.md §3`` (2026-06-05),
  Coverlet's XPlat data collector path emits aggregate-only output on
  6.0.x — ``<PerTestCoverage>true</PerTestCoverage>`` is empirically
  inert. Aggregate is the v1 contract for the .NET path; per-test is
  deferred until either a Coverlet release fixes the XPlat pipe OR a
  user opts into ``coverlet.msbuild`` (which requires csproj
  modification and is out of scope).

- ``file_path`` is workspace-relative POSIX per the path-resolution
  algorithm above.

- ``line_contexts = {}`` always — aggregate granularity has no per-test
  attribution. Localization's three-mode design routes .NET projects
  to ``failure_proximity`` mode (file-edit-distance heuristic) per
  decision §R4; no per-test spectrum matrix is needed here.

- ``excluded_lines = ()``. Cobertura has no per-line exclusion concept;
  Coverlet honors ``[ExcludeFromCodeCoverage]`` attributes by omitting
  the whole class from the report rather than marking lines.

- ``executed_branches = ()`` / ``missing_branches = ()``. Per task
  brief §2.3, Cobertura branch coverage is **deferred to a future
  slice**. The XML carries ``branch="true"`` + ``condition-coverage``
  attributes on per-line entries; the parser ignores them in v1 to
  match the JaCoCo path's "lines only" v1 scope (which has been the
  shipping contract since 2026-05-31). The semantic absence is pinned
  in ``metadata["branch_arc_semantics"] = "branches-omitted"`` so
  downstream debuggers can disambiguate from JaCoCo's
  ``"jacoco-line-counter-index"``, LCOV's ``"lcov-line-index"``, and
  coverage.py's ``"(from_line, to_line)"``.

Validation
----------

Strict on well-formedness (raises ``CoverageJsonParseError`` so
``derive`` surfaces it uniformly as ``native-payload-corrupt``) but
tolerant of optional attributes:

- File missing on disk → handled in ``derive``, not here.
- Empty file → raise.
- Malformed XML → raise.
- Unknown root tag (not ``<coverage>``) → raise.
- Missing ``<packages>`` → raise.
- Class with missing ``filename`` attribute → skip that class
  (defensive — Coverlet always emits ``filename`` but a future Cobertura
  producer might omit it for top-level synthetic classes).
- ``<line>`` with missing or non-integer ``number`` / ``hits`` → skip
  that line (defensive; mirrors JaCoCo parser's per-line tolerance).
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

from novetest.coverage import _summary
from novetest.coverage.parser import CoverageJsonParseError
from novetest.utils.path_utils import relpath_or_drive_stripped
from novetest.models.coverage_fact_set import (
    CoverageFactSet,
    FileCoverage,
)
from novetest.models.run_reference import RunReference


# Coverlet's XPlat data collector path is aggregate-effective-default
# per amended decision 2026-06-03 §3 (verified 2026-06-05 on Coverlet
# 6.0.2 AND 6.0.4 / dotnet SDK 8.0 / xunit 2.6 / Linux). v1 ships
# aggregate; per-test is a future-slice consideration only.
_COBERTURA_MAPPING_GRANULARITY = "aggregate"

# Per task brief §2.3 (deferred for v1), the parser does not emit
# per-location branch facts. The marker below lets downstream consumers
# distinguish "branches absent because coverage tool reported zero" from
# "branches absent because v1 dropped them" without re-reading the
# original XML.
_BRANCH_ARC_SEMANTICS_V1 = "branches-omitted"


def parse_cobertura_xml(
    xml_paths: Iterable[Path],
    *,
    run_reference: RunReference,
    engine_name: str,
    ecosystem: str,
    workspace_root: Path,
    derived_at: int | None = None,
) -> CoverageFactSet:
    """Build a ``CoverageFactSet`` from one or more Cobertura XML files.

    WITHIN one XML document, multiple ``<class>`` elements that resolve
    to the same ``file_path`` MERGE: ``executed_lines`` union,
    ``missing_lines`` union, then executed-wins dedup (a line present in
    both sets is executed), with the per-file summary recomputed from
    the merged sets. This is the idiomatic C# shape — Coverlet emits one
    ``<class name="NS.Type" filename="Same.cs">`` per type, so a
    multi-type ``.cs`` file yields several sibling ``<class>`` elements
    sharing one ``filename`` (verified empirically against Coverlet
    6.0.2 output, 2026-07-07; pre-merge the last type silently erased
    every earlier type's lines — finding ANA-01).

    ACROSS multiple XML input files (e.g. a future Coverlet per-test
    mode emitting one Cobertura XML per test method), same-file entries
    from later XMLs OVERWRITE earlier ones in walk order rather than
    merging. This is the cleanest behavior for the v1 aggregate-only
    path where multi-file inputs are practically unreachable; per-test
    merging is a future-slice concern that gets its own design pass.

    ``workspace_root`` is the directory the Run executed in (the parent
    of ``store.path``). All emitted ``FileCoverage.file_path`` strings
    are workspace-relative POSIX.

    Raises ``CoverageJsonParseError`` on any structural XML problem.
    """

    xml_paths_list = list(xml_paths)
    if not xml_paths_list:
        raise CoverageJsonParseError(
            "parse_cobertura_xml requires at least one Cobertura XML path"
        )

    files_by_path: dict[str, FileCoverage] = {}
    for xml_path in xml_paths_list:
        try:
            text = xml_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - derive's path-exists guard catches this first
            raise CoverageJsonParseError(
                f"Could not read Cobertura XML file {xml_path}: {exc}"
            ) from exc
        if not text.strip():
            raise CoverageJsonParseError(
                f"Cobertura XML file {xml_path} is empty"
            )

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise CoverageJsonParseError(
                f"Malformed Cobertura XML in {xml_path}: {exc}"
            ) from exc

        if root.tag != "coverage":
            raise CoverageJsonParseError(
                f"Cobertura XML root tag is {root.tag!r}, expected 'coverage' "
                f"(in {xml_path})"
            )

        packages_el = root.find("packages")
        if packages_el is None:
            raise CoverageJsonParseError(
                f"Cobertura XML in {xml_path} missing required <packages> "
                f"element"
            )

        source_dirs = _read_source_dirs(root)

        # Per-DOCUMENT accumulator: same-file <class> elements within
        # this XML merge (multi-type C# files — ANA-01); folding the
        # finished document over ``files_by_path`` afterwards preserves
        # the cross-document last-wins contract untouched.
        document_files: dict[str, FileCoverage] = {}
        for package_el in packages_el.findall("package"):
            for class_el in package_el.findall("classes/class"):
                file_coverage = _build_class_file_coverage(
                    class_el,
                    source_dirs=source_dirs,
                    workspace_root=workspace_root,
                )
                if file_coverage is None:
                    continue
                existing = document_files.get(file_coverage.file_path)
                if existing is not None:
                    file_coverage = _merge_file_coverage(existing, file_coverage)
                document_files[file_coverage.file_path] = file_coverage
        files_by_path.update(document_files)

    files = sorted(files_by_path.values(), key=lambda f: f.file_path)
    summary = _summary.aggregate_summary(files)

    metadata: dict[str, Any] = {
        "coverage_format": "cobertura-xml",
        "branch_arc_semantics": _BRANCH_ARC_SEMANTICS_V1,
        "cobertura_xml_paths": [str(p) for p in xml_paths_list],
    }

    return CoverageFactSet(
        run_reference=run_reference,
        engine_name=engine_name,
        ecosystem=ecosystem,
        mapping_granularity=_COBERTURA_MAPPING_GRANULARITY,
        summary=summary,
        files=tuple(files),
        derived_at=(
            derived_at if derived_at is not None else int(time.time() * 1000)
        ),
        metadata=metadata,
    )


# --- internals ---------------------------------------------------------------


def _read_source_dirs(root: ET.Element) -> list[Path]:
    """Pluck the ``<sources>/<source>`` directory list from the root.

    Returns ``[]`` if the block is absent or empty. Each entry is a
    ``Path`` object (NOT existence-checked at parse time — that's the
    derive layer's concern per task brief §2.4).
    """

    sources_el = root.find("sources")
    if sources_el is None:
        return []
    dirs: list[Path] = []
    for source_el in sources_el.findall("source"):
        text = (source_el.text or "").strip()
        if text:
            dirs.append(Path(text))
    return dirs


def _build_class_file_coverage(
    class_el: ET.Element,
    *,
    source_dirs: list[Path],
    workspace_root: Path,
) -> FileCoverage | None:
    """Build a ``FileCoverage`` from one ``<class>`` element.

    Returns ``None`` when the class lacks a usable ``filename`` attribute
    (defensive — Coverlet always emits one, but other Cobertura producers
    might not for synthetic classes). Path resolution per the module
    docstring.
    """

    filename = class_el.get("filename")
    if not filename:
        return None

    rel_path = _resolve_workspace_relative(
        filename=filename,
        source_dirs=source_dirs,
        workspace_root=workspace_root,
    )

    lines_el = class_el.find("lines")
    executed_lines: list[int] = []
    missing_lines: list[int] = []
    if lines_el is not None:
        for line_el in lines_el.findall("line"):
            number_str = line_el.get("number")
            hits_str = line_el.get("hits", "0")
            if number_str is None:
                continue
            try:
                number = int(number_str)
                hits = int(hits_str)
            except (TypeError, ValueError):
                # Defensive: skip the bad line rather than abort the
                # whole parse (mirrors the JaCoCo / LCOV parsers'
                # permissive posture on individual records, strict
                # posture on container structure).
                continue
            if hits > 0:
                executed_lines.append(number)
            else:
                missing_lines.append(number)

    executed_sorted = tuple(sorted(set(executed_lines)))
    missing_sorted = tuple(sorted(set(missing_lines)))

    # Branches deferred per task brief §2.3 (v1 lines-only), so the
    # summary carries statement counters only (zero branches).
    summary = _summary.summary_from_counts(
        num_statements=len(executed_sorted) + len(missing_sorted),
        covered_statements=len(executed_sorted),
    )

    return FileCoverage(
        file_path=rel_path,
        executed_lines=executed_sorted,
        missing_lines=missing_sorted,
        excluded_lines=(),
        # Per task brief §2.3 branch coverage is deferred to a future
        # slice — drop ``branch="true"`` / ``condition-coverage``
        # signal for v1.
        executed_branches=(),
        missing_branches=(),
        summary=summary,
        line_contexts={},
    )


def _merge_file_coverage(
    existing: FileCoverage, new: FileCoverage
) -> FileCoverage:
    """Union-merge two same-file entries from ONE XML document (ANA-01).

    Executed-wins rule per wave-1 §S6: union ``executed_lines``, union
    ``missing_lines``, then remove any line from ``missing_lines`` that
    is in ``executed_lines``. The per-file summary is recomputed from
    the merged sets. The remaining fields carry this parser's v1
    constants (empty exclusions/branches/contexts — see the mapping
    decisions in the module docstring), so no field-wise merge is
    needed for them.
    """

    executed = set(existing.executed_lines) | set(new.executed_lines)
    missing = (set(existing.missing_lines) | set(new.missing_lines)) - executed
    executed_sorted = tuple(sorted(executed))
    missing_sorted = tuple(sorted(missing))
    return FileCoverage(
        file_path=existing.file_path,
        executed_lines=executed_sorted,
        missing_lines=missing_sorted,
        excluded_lines=(),
        executed_branches=(),
        missing_branches=(),
        summary=_summary.summary_from_counts(
            num_statements=len(executed_sorted) + len(missing_sorted),
            covered_statements=len(executed_sorted),
        ),
        line_contexts={},
    )


def _resolve_workspace_relative(
    *,
    filename: str,
    source_dirs: list[Path],
    workspace_root: Path,
) -> str:
    """Resolve a Cobertura class ``filename`` to a workspace-relative POSIX path.

    Algorithm (matches the module docstring):

    1. For each ``<source>`` dir in declared order: build
       ``<source>/<filename>``; if the result is under ``workspace_root``,
       relativize and return.
    2. Failing that, take the FIRST source dir, build the joined path,
       and compute ``os.path.relpath`` against ``workspace_root`` —
       mirrors the Istanbul parser's outside-workspace fallback. On
       Windows cross-drive inputs ``os.path.relpath`` itself raises;
       :func:`._paths.relpath_or_drive_stripped` appends a third
       drive-stripped POSIX step so the result is always relative.
    3. If ``source_dirs`` is empty, treat ``filename`` as already
       workspace-relative (forward-compat with Cobertura producers
       that omit ``<sources>``).

    Always returns a POSIX-flavored string (forward slashes), even on
    Windows. The string is never absolute and never empty.
    """

    if not source_dirs:
        # No <sources> block — trust filename as-is. Normalize separators
        # to POSIX so the persisted form is platform-stable.
        return PurePosixPath(filename.replace("\\", "/")).as_posix()

    # Step 1: prefer the first source-dir whose joined path is under workspace.
    for source_dir in source_dirs:
        joined = source_dir / filename
        try:
            relative = joined.relative_to(workspace_root)
        except ValueError:
            continue
        return relative.as_posix()

    # Step 2/3: fall back to relpath against the first source-dir's join.
    # The shared helper covers the Windows cross-drive case where
    # ``os.path.relpath`` itself raises ``ValueError`` (one path's drive
    # differs from the other) by appending a drive-stripped POSIX form
    # as a third step. Without this, the 2026-06-09 Windows-CI matrix
    # surfaces ``ValueError: path is on mount 'D:', start on mount 'C:'``
    # whenever the Cobertura ``<source>`` refers to a path the runner's
    # current cwd can't reach on the same drive.
    joined = source_dirs[0] / filename
    return relpath_or_drive_stripped(joined, workspace_root)


__all__ = ["parse_cobertura_xml"]
