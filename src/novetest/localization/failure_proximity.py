"""``failure_proximity`` mode — rank files by failure-trace mentions.

Last-resort Localization mode for runs that have failed tests but no
coverage data at all (``CoverageFactSet`` unavailable). Algorithm
(strategy doc §2 "failure_proximity" + §"Most defensible fallback
hierarchy" item 3):

1. For each failing ``TestResult``, parse its ``failure_reference``
   into a sequence of ``(file, line)`` tuples using an engine-specific
   regex set.
2. Aggregate per-file occurrence counts across all failing tests.
3. If a ``RegressionFactSet`` is provided AND has changed files,
   multiply the per-file score by ``(1 + α)`` where ``α = 0.5`` —
   FLUCCS-style prior (Sohn & Yoo, ISSTA 2017).
4. Rank files by aggregated score, min-max normalize within the full
   ranking, dense-rank with ties, truncate to ``top_n``.
5. Produce a ``LocalizationFinding`` with ``mode = "failure_proximity"``,
   ``confidence = "low"``, file-level ``CodeLocation`` kind, and the
   v1 freeze-pinned envelope-shape deviation (per the task brief §7):

   - ``alternate_scores_available = ()`` (empty tuple) — no SBFL formulas
     were computed.
   - ``entries[*].alternate_scores = {}`` (empty dict) — same reason.

The ``formula`` field on both the finding and per-entry is set to
``"ochiai"`` as a placeholder so the closed-enum ``__post_init__``
validation passes; downstream consumers MUST gate on
``finding.mode == "failure_proximity"`` rather than ``formula`` to know
that no SBFL scores are present.

**Why this is NOT under ``sbfl/``**: failure_proximity is a different
ranking technique (heuristic frequency count + regression prior), not
SBFL. Keeping the module a sibling of ``sbfl/`` rather than a child
keeps the package taxonomy honest: ``sbfl/`` is reserved for the four
formula implementations + spectra builders that share an ``(ef, ep,
nf, np)`` interface.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Final

from novetest.memory.project_store import ProjectStore
from novetest.models.localization_finding import (
    CodeLocation,
    EvidenceCitation,
    LocalizationEntry,
    LocalizationFinding,
)
from novetest.models.regression_fact_set import RegressionFactSet
from novetest.models.run_record import RunRecord
from novetest.utils.path_utils import to_workspace_relative_posix


# FLUCCS-style regression-reweighting boost factor (Sohn & Yoo, ISSTA 2017).
# Multiplicative: ``score *= (1 + ALPHA)`` for files in the regression
# change set. ``0.5`` is the published tuned value in the FLUCCS paper.
_REGRESSION_BOOST_ALPHA: Final[float] = 0.5

# Evidence-line cap per file entry — mirrors derive.py's ``_EVIDENCE_LINE_CAP``
# so the LocalizationFinding's per-entry payload stays bounded.
_EVIDENCE_LINE_CAP: Final[int] = 10

# Outcome bucket — failed-like outcomes are the ones whose failure trace
# we care about. Mirrors ``derive.py::_FAILED_OUTCOMES``.
_FAILED_OUTCOMES: Final[frozenset[str]] = frozenset({"failed", "errored"})

# Placeholder formula string used on the LocalizationFinding so the
# closed-enum validation passes; failure_proximity does not compute any
# SBFL formula. Consumers MUST gate on ``finding.mode`` not ``formula``.
_PLACEHOLDER_FORMULA: Final[str] = "ochiai"


# ---------------------------------------------------------------------------
# Per-engine failure-log regex sets
# ---------------------------------------------------------------------------
#
# Each regex MUST capture (file_path, line_number) as groups 1 and 2.
# Best-effort posture: a regex that matches yields a tuple; no match
# yields nothing — we never raise on a malformed log. Multiple regexes
# per engine cover format variance within the same engine.

# Path chars: starts with an alpha/underscore/dot/slash (allow absolute and
# relative forms), then alphanumerics + path separators + dashes/dots.
# ``./`` and ``../`` opening segments are common in jest/cargo absolute frames.
#
# Windows safety (2026-06-09, defect surfaced by CI matrix run 27176933845):
# the optional ``(?:[A-Za-z]:[\\/])?`` prefix captures the Windows drive
# segment (e.g. ``C:\`` or ``C:/``) which would otherwise be lost. The
# character class ``:`` is NOT a word-class character, so without this
# leading optional group the regex engine starts the path capture AFTER
# the drive colon, producing a malformed drive-less Windows path. The
# pattern composes safely on POSIX: the optional group matches empty,
# and the original first-char class ``[A-Za-z_./]`` is augmented with
# ``\\`` so the engine can begin a capture at the path-separator that
# follows the drive (e.g. position 2 in ``C:\Users\...`` lands on ``\``).
# Pre-fix, the regex captured ``Users\runneradmin\...\foo.py``; post-fix
# it captures ``C:\Users\runneradmin\...\foo.py`` — letting the absolute-
# path check + workspace-relative normalization downstream do their job.
_FILE_PATH_CHARS = r"(?:[A-Za-z]:[\\/])?[A-Za-z_./\\][\w\-./\\]*"
_PYTHON_FILE_CHARS = _FILE_PATH_CHARS

_PYTEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # Format A (preferred — set by ``pytest_adapter`` when ``crash`` block
    # is present): ``<path>:<lineno>: <message>``. Anchored at line start
    # or end of "File "<path>", line N" form is the secondary pattern.
    re.compile(rf"({_PYTHON_FILE_CHARS}\.py):(\d+):"),
    # Traceback file frame: ``File "<path>", line N, in <name>``.
    re.compile(rf'File "({_PYTHON_FILE_CHARS}\.py)", line (\d+)'),
)

_JS_FILE_EXT = r"(?:js|jsx|ts|tsx|mjs|cjs)"

_JEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # ``at <name> (<path>:<line>:<col>)`` — Node.js stack frame, the
    # common form in jest's ``failureMessages``.
    re.compile(rf"\(({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+\)"),
    # Bare ``at <path>:<line>:<col>`` — when no enclosing function name.
    re.compile(rf"\s+at\s+({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+"),
    # Jest's ``at Object.<anonymous> (<path>:<line>:<col>)`` — covered by
    # the first regex (parens form) but also handle the ``> N | ...``
    # diagnostic context line that jest prints alongside the trace
    # (the standalone ``<path>:<line>:<col>`` form before the stack).
    re.compile(rf"^\s*({_PYTHON_FILE_CHARS}\.{_JS_FILE_EXT}):(\d+):\d+", re.MULTILINE),
)

_CARGO_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # Standard libtest panic: ``thread '...' panicked at <path>:<line>:<col>``.
    re.compile(rf"panicked at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # ``assertion `...` failed at <path>:<line>:<col>`` — newer rustc forms.
    re.compile(rf"failed at ({_PYTHON_FILE_CHARS}\.rs):(\d+):\d+"),
    # NOTE: a third "defensive catch-all" regex (`\b(...)\.rs:(\d+):\d+`)
    # used to live here. It was DROPPED at 2026-05-31 (Defect 3 fix,
    # CEO-implied Option D) because cargo nextest's default stack
    # backtrace (no `RUST_BACKTRACE=1` needed) contains every frame's
    # path including Rust stdlib files like
    # ``/rustc/<hash>/library/core/src/panicking.rs:N:M``. The catch-all
    # would slurp those stdlib paths and tie them with the real bug
    # file at e_f=1; lexicographic tie-break (the algorithm sorts ties
    # by file path ascending) pushed `src/arithmetic.rs` to rank #4
    # behind three `/rustc/...` paths. Now only the two anchored
    # patterns above match — the panic-at frame is the load-bearing
    # extraction surface. Algorithm-side filter in ``_derive_aggregate``
    # (intersection with covered files) is the defense-in-depth layer
    # that catches any remaining stdlib-path leakage from future
    # adapter / rustc backtrace shape changes.
    #
    # Source: questions/main-branch-team-2026-05-31-localization-aggregate-e2e-defect3-parser-stdlib-pollution.md
)

_GOTEST_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # ``--- FAIL: TestX`` is followed by frames like ``  add_test.go:14: ...``.
    re.compile(rf"^\s+({_PYTHON_FILE_CHARS}\.go):(\d+):", re.MULTILINE),
    # Go panic-style stack frames: ``\t<path>:<line> +<offset>``.
    re.compile(rf"^\s+({_PYTHON_FILE_CHARS}\.go):(\d+)\s", re.MULTILINE),
)

# JDK 9+ stack frames may carry a classloader/module prefix between
# ``at `` and the fully-qualified class name. Verified empirically
# (2026-07-07, W1/S7) on the adapter-written failure logs:
# - Maven Surefire 3.2.5: NO prefix (``at com.example.CalculatorTest...``).
# - Gradle 8.14.5: ``app//`` on user/framework frames and versioned
#   module prefixes on JDK frames (``java.base@17.0.19/java.lang...``).
# The frozen wave-1 §S7 regex prescription (``at pkg.Cls.m(File.java:NN)``
# with no prefix allowance) would MISS every user frame under Gradle.
_JVM_FRAME_MODULE_PREFIX = r"(?:[\w.$@]+/+)*"

# JUnit stack frames carry only the file BASENAME (``CalculatorTest.java``),
# so the pattern captures the fully-qualified class name too (named group
# ``fqcn``) and ``_extract_location`` reconstructs a package-relative path
# (``com/example/CalculatorTest.java``) from it. A bare basename would
# pass through ``_normalize_to_workspace_relative`` unchanged (it is
# already relative) and collide across packages; the package-relative
# form is deterministic and disambiguates. It is still NOT the on-disk
# source-root path (``src/test/java/com/example/...``) — file-level
# best-effort per the mode's ``confidence: "low"`` contract.
_JUNIT_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    # ``at [prefix/]<pkg>.<Cls>.<method>(<File>.java:<line>)``. The method
    # atom allows ``<init>``/``<clinit>`` constructor frames; the file
    # extension set covers the JVM source languages Surefire/Gradle emit.
    re.compile(
        rf"\bat {_JVM_FRAME_MODULE_PREFIX}"
        r"(?P<fqcn>[A-Za-z_$][\w$.]*)\.[\w$<>]+"
        r"\((?P<file>[\w$\-]+\.(?:java|kt|kts|groovy|scala)):(?P<line>\d+)\)"
    ),
)

# JUnit failure logs are UNTRIMMED (verified 2026-07-07 on Surefire 3.2.5
# AND Gradle 8.14.5): every assertion failure carries ~6 framework frames
# (``org.junit.jupiter.api.Assert*``, ``org.opentest4j.*``) plus JDK
# reflection frames around the single user frame. Framework frames appear
# in EVERY failing test's log, so without filtering they would out-score
# the real file (score = number of failing tests = the maximum). Same
# defect shape as cargo's Defect 3 (2026-05-31, stdlib-path pollution);
# same remedy posture: keep the PARSER's output set tight rather than
# relying on downstream cleanup (failure_proximity has no covered-files
# intersection filter). Frames whose FQCN opens with one of these
# test-infra / JDK / build-tool package roots are dropped. A user who
# names their own package ``org.junit.*`` loses those frames — an
# acceptable trade for a best-effort ``confidence: "low"`` mode.
_JVM_INFRA_PACKAGE_PREFIXES: Final[tuple[str, ...]] = (
    "java.",
    "javax.",
    "jdk.",
    "sun.",
    "com.sun.",
    "org.junit.",
    "junit.",
    "org.opentest4j.",
    "org.apiguardian.",
    "org.gradle.",
    "worker.org.gradle.",
    "org.apache.maven.",
)

# xUnit / VSTest stack frames: ``at Ns.Cls.Method() in <path>:line <N>``.
# Verified empirically (2026-07-07, dotnet SDK 8.0 + xunit 2.6): the
# `` in <path>:line <N>`` clause comes from PDB symbols, so it appears
# ONLY on frames with debug info — i.e. user code. Framework frames
# (``at System.RuntimeMethodHandle.InvokeMethod(...)``) carry no ``in``
# clause and are structurally excluded; no blocklist needed. The path is
# absolute (as recorded by the compiler), so downstream
# ``_normalize_to_workspace_relative`` produces the workspace-relative
# envelope form. Locale caveat: non-English .NET runtimes localize the
# `` in ``/``:line `` tokens; those logs degrade to no-match (best-effort).
_XUNIT_REGEXES: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(rf"\bin ({_FILE_PATH_CHARS}\.(?:cs|fs|vb)):line (\d+)"),
)

# Engine-name keyed regex table. Unknown engines fall back to pytest's
# pattern (the most permissive — file-path-colon-lineno is a near-universal
# convention). This is "best-effort" per the task brief: a parser that
# finds nothing is acceptable; one that crashes is not.
#
# Every canonical engine name from ``run.list_supported_engine_pairs()``
# MUST have a key here — pinned by
# ``tests/unit/localization/test_engine_support_divergence.py`` so a
# future 7th engine fails tests instead of silently degrading (ANA-02).
# ``"gotest"`` is a legacy alias kept on top of the canonical six.
_ENGINE_REGEX_TABLE: Final[dict[str, tuple[re.Pattern[str], ...]]] = {
    "pytest": _PYTEST_REGEXES,
    "jest": _JEST_REGEXES,
    "cargo-test": _CARGO_REGEXES,
    "gotest": _GOTEST_REGEXES,
    "go-test": _GOTEST_REGEXES,
    "junit": _JUNIT_REGEXES,
    "xunit": _XUNIT_REGEXES,
}


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def parse_failure_log(
    engine_name: str,
    failure_text: str,
) -> tuple[tuple[str, int], ...]:
    """Extract canonical ``(file, line)`` tuples from a failure-log string.

    Engine-keyed regex dispatch picks the right pattern set; unknown
    engines fall back to the pytest regexes (most permissive). The
    output preserves first-seen order and drops duplicates so a file
    mentioned at the same line in multiple stack frames counts once
    per failing test (the aggregation in ``derive_failure_proximity``
    deduplicates across tests separately).

    Returns an empty tuple when nothing matches — the caller decides
    whether to record a parse warning (the brief mandates a metadata
    ``parse_warnings`` entry on each test whose log was un-parseable).
    """
    if not failure_text:
        return ()
    regexes = _ENGINE_REGEX_TABLE.get(engine_name, _PYTEST_REGEXES)
    seen: set[tuple[str, int]] = set()
    results: list[tuple[str, int]] = []
    for pattern in regexes:
        for match in pattern.finditer(failure_text):
            key = _extract_location(match)
            if key is None or key in seen:
                continue
            seen.add(key)
            results.append(key)
    return tuple(results)


def _extract_location(match: re.Match[str]) -> tuple[str, int] | None:
    """Turn one regex match into a canonical ``(file, line)`` tuple.

    Two match shapes exist:

    - Positional (every engine except junit): groups 1 and 2 are
      ``(file_path, line)`` verbatim — the pre-S7 contract, unchanged.
    - Named (junit): groups ``fqcn`` / ``file`` / ``line``. The JVM
      stack frame carries only the file basename, so the package half
      of ``fqcn`` is folded into a package-relative path
      (``com.example.CalculatorTest`` + ``CalculatorTest.java`` →
      ``com/example/CalculatorTest.java``). Frames whose FQCN opens
      with a known test-infra / JDK / build-tool package root return
      ``None`` (dropped) — see ``_JVM_INFRA_PACKAGE_PREFIXES``.
    """
    groups = match.groupdict()
    if "fqcn" in groups:
        fqcn = groups["fqcn"]
        if any(fqcn.startswith(prefix) for prefix in _JVM_INFRA_PACKAGE_PREFIXES):
            return None
        package, _, _cls = fqcn.rpartition(".")
        file_name = groups["file"]
        file_path = (
            f"{package.replace('.', '/')}/{file_name}" if package else file_name
        )
        return (file_path, int(groups["line"]))
    file_path = match.group(1)
    try:
        line = int(match.group(2))
    except (ValueError, IndexError):
        return None
    return (file_path, line)


# ``resolve_failure_text`` routing sets. Module-level (not inline tuples)
# so the divergence guard in
# ``tests/unit/localization/test_engine_support_divergence.py`` can pin
# that their union covers every canonical engine name from
# ``run.list_supported_engine_pairs()`` — the ANA-02 silent breakage was
# exactly junit/xunit missing from the (then-inline) tuples.
#
# - Inline: ``failure_reference`` IS the failure text (pytest ``crash``
#   block; jest ``failureMessages``).
# - Logfile: ``failure_reference`` is an artifact-dir-relative path to a
#   per-test log; a missing file resolves to ``""``.
# - Hybrid (junit/xunit): the normalizer fills ``failure_reference`` with
#   a log path when the adapter wrote one, or an inline ``"type: message"``
#   join when it did not (e.g. empty TRX ``<ErrorInfo>``). Log-path
#   resolution first, inline fallback second.
_INLINE_REFERENCE_ENGINES: Final[frozenset[str]] = frozenset({"pytest", "jest"})
_LOGFILE_REFERENCE_ENGINES: Final[frozenset[str]] = frozenset(
    {"cargo-test", "gotest", "go-test"}
)
_HYBRID_REFERENCE_ENGINES: Final[frozenset[str]] = frozenset({"junit", "xunit"})


def resolve_failure_text(
    store: ProjectStore,
    run_id: str,
    engine_name: str,
    failure_reference: str | None,
) -> str:
    """Resolve a ``TestResult.failure_reference`` into the raw failure-log text.

    Engine-dispatched: pytest and jest store the full failure text
    inline (the adapter normalizer concatenates ``crash.message`` or
    ``failureMessages``); cargo-test and gotest store a project-store-
    relative path to a per-test log file under
    ``<artifact_dir>/native/failures/<name>.log``; junit and xunit are
    hybrid — the same path shape when the adapter wrote a per-test log,
    an inline ``"type: message"`` string otherwise (W1/S7, ANA-02).

    Returns the empty string when:
    - ``failure_reference`` is ``None`` or empty.
    - The engine is unrecognized (defensive — we'd rather return empty
      than misroute a path-string into the regex).
    - The expected log file does not exist on disk (artifact pruned or
      adapter quirk) — logfile engines only. Hybrid engines fall back
      to treating the reference as inline failure text instead: a
      reference that does not name an existing file under the run's
      artifact dir IS the inline fill, even when it superficially looks
      path-like (an exception message quoting a path, say).

    Disk IO is best-effort: a permission error or invalid encoding
    returns the empty string rather than propagating. The downstream
    parser handles empty input by returning no matches.
    """
    if not failure_reference:
        return ""
    if engine_name in _INLINE_REFERENCE_ENGINES:
        return failure_reference
    if engine_name in _LOGFILE_REFERENCE_ENGINES:
        log_text = _resolve_log_reference(store, run_id, failure_reference)
        return log_text if log_text is not None else ""
    if engine_name in _HYBRID_REFERENCE_ENGINES:
        log_text = _resolve_log_reference(store, run_id, failure_reference)
        return log_text if log_text is not None else failure_reference
    # Unknown engine — defensively return empty rather than guess.
    return ""


def _resolve_log_reference(
    store: ProjectStore, run_id: str, failure_reference: str
) -> str | None:
    """Read ``failure_reference`` as an artifact-dir-relative log path.

    Returns the log text when the reference names an existing file under
    ``<store>/run/artifacts/run_<run_id>/``; ``None`` when it does not
    (callers decide the fallback: ``""`` for logfile engines, the inline
    reference itself for hybrid engines). An existing-but-unreadable
    file returns ``""`` (NOT ``None``) — the reference was genuinely a
    path, so falling back to inline text would feed a path string to the
    parser.

    The ``(OSError, ValueError)`` guard around the existence probe covers
    inline junit/xunit references whose text embeds characters ``Path``
    refuses (e.g. NUL) — best-effort contract: never crash on adapter-
    shaped data.
    """
    artifact_dir = store.path / "run" / "artifacts" / f"run_{run_id}"
    try:
        log_path = artifact_dir / failure_reference
        if not log_path.is_file():
            return None
    except (OSError, ValueError):
        return None
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def derive_failure_proximity(
    *,
    store: ProjectStore,
    record: RunRecord,
    failed_test_ids: frozenset[str],
    regression_facts: RegressionFactSet | None,
    top_n: int,
) -> LocalizationFinding:
    """Build the ``failure_proximity`` LocalizationFinding for this run.

    Preconditions (validated by the caller in ``derive.py``):

    - ``failed_test_ids`` is non-empty (otherwise the strategy doc §5
      says to return ``LocalizationUnavailable(REASON_NO_FAILED_TESTS)``).

    Empty findings are returned when every failing test's failure log
    is empty or un-parseable; ``finding.metadata["parse_warnings"]``
    enumerates the unfortunate test ids so consumers can investigate.
    """
    parse_warnings: list[str] = []
    file_to_failed_tests: dict[str, set[str]] = defaultdict(set)
    file_to_evidence_lines: dict[str, set[int]] = defaultdict(set)

    # Workspace root for path normalization (B2-2 UX normalization,
    # 2026-06-08). ``store.path`` is ``<workspace>/.novetest/``; the
    # workspace root sits one level up. Same pattern as
    # ``derive.py::_resolve_repo_path`` but the OPPOSITE direction
    # (abs → rel here; rel → abs there). Hoisted out of the loop so the
    # one-level-up resolution runs once per derivation, not once per
    # parsed tuple.
    workspace_root = store.path.parent

    for tr in record.test_results:
        if tr.outcome not in _FAILED_OUTCOMES:
            continue
        if tr.node_id not in failed_test_ids:
            # Defensive: ``failed_test_ids`` is the authoritative set
            # the caller computed; honor it even if the underlying
            # outcome filter would have picked up additional tests
            # (e.g. an "errored" outcome the caller chose to exclude).
            continue
        # Warning wording split (W1/S7): the pre-fix single message
        # ("failure_reference empty or unresolvable") conflated three
        # causes — and for junit/xunit the REAL cause was "engine not
        # routed by resolve_failure_text", which the message hid. Now
        # that all six engines are routed, the two remaining causes are
        # distinguished honestly. Format stays ``"<node_id>: <reason>"``
        # per the localization interface contract.
        if not tr.failure_reference:
            parse_warnings.append(f"{tr.node_id}: failure_reference is empty")
            continue
        failure_text = resolve_failure_text(
            store, record.run_reference.run_id, record.engine_name, tr.failure_reference
        )
        if not failure_text:
            parse_warnings.append(
                f"{tr.node_id}: failure_reference did not resolve to failure"
                " text (log file missing or unreadable, or engine not"
                " supported)"
            )
            continue
        tuples = parse_failure_log(record.engine_name, failure_text)
        if not tuples:
            parse_warnings.append(
                f"{tr.node_id}: no parseable file:line references in failure log"
            )
            continue
        for file_path, line in tuples:
            # B2-2: normalize the parser's emitted file path to
            # workspace-relative form. Most failure-log parsers (pytest's
            # ``crash.path``, cargo nextest's panic frame, etc.) carry
            # absolute paths verbatim; the other Localization modes
            # source from CoverageFactSet whose adapter contract yields
            # repo-relative paths. Normalize here so all three modes
            # emit a single mode-invariant ``code_location.file`` shape.
            relative_file = _normalize_to_workspace_relative(
                file_path, workspace_root
            )
            file_to_failed_tests[relative_file].add(tr.node_id)
            file_to_evidence_lines[relative_file].add(line)

    changed_files = _changed_files_from_regression(regression_facts)
    regression_reweighted = bool(changed_files) and bool(file_to_failed_tests)

    # Build per-file candidates with raw scores. The raw score is the
    # number of distinct failing tests whose failure trace mentions the
    # file (capped at total_failing for sanity). The regression prior
    # multiplies the score; the absolute scale is preserved so
    # ``score_raw`` stays explainable as "this many failing tests
    # mentioned this file" (boosted by 1.5x for changed-set hits).
    candidates: list[tuple[str, float, set[str], set[int]]] = []
    for file_path, tests in file_to_failed_tests.items():
        base_score = float(len(tests))
        if file_path in changed_files:
            base_score *= 1.0 + _REGRESSION_BOOST_ALPHA
        candidates.append(
            (file_path, base_score, tests, file_to_evidence_lines[file_path])
        )

    # Sort by score desc; tiebreak by file path ascending so two runs
    # with identical inputs produce identical rankings.
    candidates.sort(key=lambda c: (-c[1], c[0]))

    raw_scores = [c[1] for c in candidates]
    normalized = _min_max_normalize(raw_scores)
    ranks = _dense_ranks(raw_scores)

    truncated = candidates[:top_n]
    truncated_norm = normalized[:top_n]
    truncated_ranks = ranks[:top_n]

    by_rank: dict[int, list[int]] = defaultdict(list)
    for idx, rank in enumerate(truncated_ranks):
        by_rank[rank].append(idx)

    entries: list[LocalizationEntry] = []
    for idx, ((file_path, raw_score, failed_tests, evidence_lines), norm_score, rank) in enumerate(
        zip(truncated, truncated_norm, truncated_ranks, strict=True)
    ):
        peers = tuple(
            f"entry_index_{p}" for p in by_rank[rank] if p != idx
        )
        sorted_lines = tuple(sorted(evidence_lines))[:_EVIDENCE_LINE_CAP]
        # ``primary_line`` is required-int on the model. When evidence
        # lines exist (always true here — files only land in candidates
        # via the parser, which always produces a line number), use the
        # first one; otherwise sentinel 0 ("unknown line").
        primary_line = sorted_lines[0] if sorted_lines else 0

        related = tuple(sorted(failed_tests))
        citations: list[EvidenceCitation] = []
        for nodeid in related:
            citations.append(
                EvidenceCitation(
                    kind="test_result",
                    run_reference=record.run_reference,
                    selector={"test_id": nodeid, "outcome": "failed"},
                )
            )

        entries.append(
            LocalizationEntry(
                rank=rank,
                tied_with=peers,
                code_location=CodeLocation(
                    kind="file",
                    file=file_path,
                    symbol=None,
                    line_range=None,
                    primary_line=primary_line,
                    evidence_lines=sorted_lines,
                ),
                score_raw=raw_score,
                score_normalized=norm_score,
                formula=_PLACEHOLDER_FORMULA,
                # Brief §7 deviation: failure_proximity is NOT SBFL, so
                # alternate_scores is the empty dict.
                alternate_scores={},
                related_failed_tests=related,
                evidence_citations=tuple(citations),
            )
        )

    metadata: dict[str, Any] = {
        "regression_reweighted": regression_reweighted,
        "changed_files_count": len(changed_files),
    }
    if parse_warnings:
        metadata["parse_warnings"] = parse_warnings

    return LocalizationFinding(
        run_reference=record.run_reference,
        engine_name=record.engine_name,
        ecosystem=record.ecosystem,
        mode="failure_proximity",
        confidence="low",
        formula=_PLACEHOLDER_FORMULA,
        # Brief §7 deviation: empty tuple because no alternate SBFL formulas
        # were computed for this mode.
        alternate_scores_available=(),
        top_n=top_n,
        entries=tuple(entries),
        derived_at=int(time.time() * 1000),
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _changed_files_from_regression(
    regression_facts: RegressionFactSet | None,
) -> frozenset[str]:
    """Extract the FLUCCS-style "changed files" set from a RegressionFactSet.

    Defined as the union of:
    - ``coverage_change.files_added`` (covered in target but not baseline)
    - ``coverage_change.files_removed`` (covered in baseline but not target)
    - ``coverage_change.file_deltas[*].file_path`` (covered in both but
      with newly-covered or newly-uncovered lines)

    Returns the empty frozenset when ``regression_facts`` is ``None`` or
    when its ``coverage_change`` block is absent — the regression boost
    is then a no-op. This matches the brief's "best-effort" stance:
    absence of Regression Facts is normal and does not affect the
    aggregate ranking apart from removing the prior.

    The ``RegressionFactSet.coverage_change`` field is a raw dict (per
    decision §C.6) embedded verbatim from ``CoverageDelta.to_dict()``;
    we read it defensively as ``Mapping``-shaped data without re-parsing
    into the typed model.
    """
    if regression_facts is None:
        return frozenset()
    cc = regression_facts.coverage_change
    if not isinstance(cc, dict):
        return frozenset()
    files: set[str] = set()
    for key in ("files_added", "files_removed"):
        raw = cc.get(key)
        if isinstance(raw, list):
            files.update(str(p) for p in raw if isinstance(p, str))
    deltas_raw = cc.get("file_deltas")
    if isinstance(deltas_raw, list):
        for delta in deltas_raw:
            if isinstance(delta, dict):
                fp = delta.get("file_path")
                if isinstance(fp, str):
                    files.add(fp)
    return frozenset(files)


def _min_max_normalize(scores: list[float]) -> list[float]:
    """Min-max normalize into ``[0, 1]`` with all-zero on zero spread.

    Mirrors ``derive.py::_min_max_normalize`` so cross-mode ranking
    output stays consistent. Duplicated rather than imported to keep
    the failure_proximity module standalone; ``derive.py`` owns the
    canonical helper for SBFL paths.
    """
    if not scores:
        return []
    lo = min(scores)
    hi = max(scores)
    if hi == lo:
        return [0.0 for _ in scores]
    span = hi - lo
    return [(s - lo) / span for s in scores]


def _dense_ranks(sorted_scores: list[float]) -> list[int]:
    """Return 1-based dense ranks for a DESC-sorted list of scores.

    Mirrors ``derive.py::_dense_ranks`` — same dense-rank convention so
    the ``rank`` field has identical semantics across all three modes.
    """
    ranks: list[int] = []
    current_rank = 0
    previous_score: float | None = None
    for score in sorted_scores:
        if previous_score is None or score != previous_score:
            current_rank += 1
            previous_score = score
        ranks.append(current_rank)
    return ranks


def _is_outside_workspace(file_path: Path, workspace_root: Path) -> bool:
    """Cross-drive-safe inside/outside-workspace classifier.

    Returns ``True`` iff ``file_path`` cannot be expressed as a path
    under ``workspace_root``. Mechanism: ``Path.relative_to`` raises
    ``ValueError`` for any non-prefix relationship — same surface used
    on Windows for **cross-drive** comparison (``D:\\workspace`` vs
    ``C:\\Users\\...``) AND on POSIX for plain non-prefix paths
    (``/workspace`` vs ``/elsewhere``). The platform's ``ValueError``
    text differs (Windows: "path is on mount 'C:', start on mount 'D:'";
    POSIX: "'/elsewhere/file.py' is not in the subpath of '/workspace'"
    or similar) but the binary classification outcome is identical.

    Carried as a separate helper (rather than inlined as a ``try`` block
    in ``_normalize_to_workspace_relative``) so the audit recommendation
    in ``tasks/localization-team-2026-06-09-windows-path-normalization-
    fix.md`` §"outside-workspace 판정 자체도 cross-drive 안전 필요" is
    visible at the call site: the helper IS the cross-drive safety net,
    and its naming makes the intent explicit. The brief notes:

      "cross-drive 도 outside로 분류 — workspace_root와 무관 ...
      failure_proximity의 'not your code' semantic과 자연 정렬 (다른
      drive면 사용자 코드 아닐 가능성 큼)"

    Pinned by ``test_is_outside_workspace_classifies_disjoint_paths_as_outside``.
    """
    try:
        file_path.relative_to(workspace_root)
    except ValueError:
        return True
    return False


def _normalize_to_workspace_relative(
    file_path: str, workspace_root: Path
) -> str:
    """Normalize a parsed failure-log file path to workspace-relative POSIX form.

    Returns the workspace-relative form (POSIX separators) when the
    input is absolute AND lies under ``workspace_root``; otherwise
    returns ``file_path`` unchanged. Idempotent on already-relative
    inputs (the common case for the existing fixture tests), with
    backslash-to-forward-slash normalization applied via ``as_posix``
    so a Windows ``WindowsPath`` constructed from a forward-slash
    spelling round-trips back to forward slashes (NOT
    ``WindowsPath.__str__``'s backslash form).

    Brief (B2-2 UX normalization, 2026-06-08): failure_proximity emits
    absolute paths in production because pytest's ``crash.path``, cargo
    nextest's panic frame, jest stack traces, etc. carry absolute paths
    verbatim. Other Localization modes (sbfl_per_test, sbfl_aggregate)
    are sourced from CoverageFactSet whose adapter contract yields
    repo-relative paths. This helper aligns failure_proximity with the
    envelope-wide convention. Spec pinned in
    ``design/interace-contract/localization.md`` §"Result shape —
    mode-invariant".

    Windows fix (2026-06-09, defect surfaced by CI run 27176933845):
    pre-fix the helper used bare ``str(rel)`` which on Windows emits the
    ``WindowsPath`` backslash form (``'src\\foo.py'``) — incompatible
    with the POSIX envelope shape the other Localization modes produce.
    Post-fix the inside-branch delegates to the shared
    :func:`novetest.utils.path_utils.to_workspace_relative_posix`, which
    encapsulates the three-step ``relative_to → os.path.relpath →
    drive-stripped POSIX`` resolution. The shared utility's step 2/3
    fallback chain absorbs the ``Path.relative_to`` cross-drive
    ValueError that the inline implementation handled via
    ``os.path.relpath`` defensively (the ``_is_outside_workspace`` gate
    catches the same case upstream; the fallback remains as
    defense-in-depth against future ``pathlib`` semantics drift).

    Paths OUTSIDE the workspace (e.g. ``/usr/lib/python/.../stdlib.py``
    in pytest tracebacks, ``/rustc/<hash>/.../panicking.rs`` frames in
    cargo, or cross-drive Windows paths like ``C:\\Users\\...\\foo.py``
    against a ``D:\\workspace``) are left absolute — they cannot be
    made workspace-relative meaningfully and surface as an obvious "not
    your code" cue to consumers. This is the Defect-3 defensive posture
    from 2026-05-31, preserved unchanged; the
    failure_proximity mode does NOT have an analogous covered-files
    intersection filter (which aggregate mode uses), so the absolute
    form is the next-best disambiguation signal. This "outside paths
    stay absolute" rule is a Localization-specific POLICY layered on
    TOP of the shared path utility — the shared utility itself always
    returns a relative form; the policy lives here (the
    :func:`_is_outside_workspace` gate) because it expresses Localization's
    semantic preference, not a path-utility behavior.

    Note: this helper does NOT call ``Path.resolve()`` on either side.
    Symlinks / case-insensitive filesystems / NFS mounts may cause a
    workspace path to look like ``/A/ws/file.py`` while the failure log
    emits ``/B/ws/file.py`` (same underlying inode via symlink). Such
    paths fall through to the "kept absolute" branch — same posture as
    paths genuinely outside the workspace. A future cycle can add a
    symlink-resolving variant if the corner case surfaces in Manual
    Test; for v1 the conservative non-resolving form is sufficient.
    """
    candidate = Path(file_path)
    if not candidate.is_absolute():
        # Already-relative input: normalize separators to POSIX form so
        # any Windows-spelled relative path (``src\\foo.py``) lands in
        # the envelope as ``src/foo.py``. No-op on POSIX where backslash
        # is a literal filename character with no separator semantics.
        return candidate.as_posix()
    if _is_outside_workspace(candidate, workspace_root):
        # Outside workspace OR cross-drive (Windows). Kept verbatim as
        # the "not your code" semantic cue per the Defect-3 posture.
        # The input ``file_path`` is preserved (NOT ``candidate.as_posix()``)
        # because operators benefit from seeing the OS-native form when
        # diagnosing stdlib / cross-drive provenance — a Windows operator
        # reading ``C:\Users\runneradmin\AppData\...`` recognizes that
        # immediately; ``C:/Users/runneradmin/AppData/...`` requires an
        # extra cognitive step.
        return file_path
    # Inside workspace: delegate to the shared utility. The three-step
    # ``relative_to → os.path.relpath → drive-stripped POSIX`` resolution
    # is byte-equivalent to the prior inline implementation for every
    # inside-workspace input, with the same defense-in-depth fallback if
    # ``_is_outside_workspace`` and ``relative_to`` disagree.
    return to_workspace_relative_posix(candidate, workspace_root)


