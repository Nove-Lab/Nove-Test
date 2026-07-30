"""Exclude the run's own test nodes from the SBFL candidate set.

## Why this exists

SBFL is *structurally* biased toward test code. A failing test's own body
is executed by exactly one failing test and by no passing test, so its
counts are always ``ef = 1, ep = 0`` — the shape every suspiciousness
formula is designed to reward. When the coverage tool measures the test
files too (the pytest adapter runs ``--cov=.``), those lines enter the
spectra as candidate locations and outscore the real defect, which is
typically executed by passing tests as well (``ep > 0``).

Measured on ``tests/fixtures/projects/localization-shared-defect`` (7
tests, 2 failing), reproducing the wave-1 persona-P1 ranking exactly:

| location                                | ef | ep | nf | np | Ochiai |
|-----------------------------------------|----|----|----|----|--------|
| a failing test's own body               |  1 |  0 |  1 |  5 | 0.7071 |
| the defect (``totals.py::invoice_total``)|  2 |  3 |  0 |  2 | 0.6325 |

``ep = 0`` beats ``ef = 2``. This does not depend on the project, the
language or the defect — it follows from the definition of a test.

## The rule

Drop every candidate location that **is** a test node discovered in this
run — matched by *file and symbol*, not by file alone. The node set comes
from the Run Record's own ``test_results`` node ids: ground truth, not a
name pattern. Deliberately NOT a ``test_*`` / ``*_test.go`` / ``tests/``
heuristic: with six ecosystems in the matrix a naming guess is wrong
somewhere, and the run already knows the answer.

Symbol granularity is what keeps a **co-located** file — production code
and collected tests in the same module (pytest ``python_files = ["*.py"]``,
the native Rust/Go layout) — rankable. The first cut of this filter was
file-granular and deleted such a file's production symbols along with its
tests, silently (L1 finding 2026-07-30, issue 2). A candidate in a
test-owning file is dropped only when it IS the test node: the same
symbol, a symbol nested inside it (``test_x.helper``), or an enclosing
scope of it (the ``TestKlass`` of ``TestKlass::test_m``).

Two deliberate over-approximations remain, both because they are the
honest answer when the evidence cannot distinguish:

- A candidate with **no symbol** in a test-owning file (module-level code,
  a file-level fallback after a resolver miss, and every ``sbfl_aggregate``
  candidate — that mode has no symbols at all) is dropped. At file
  granularity "is this the test or the product?" is unanswerable, and the
  pre-narrowing behaviour is the safe default.
- A test-owning file whose node ids yield no symbol half at all is
  excluded whole (see ``discovered_test_nodes``).

Files that hold no test node — ``conftest.py``, fixtures, test helpers —
are never excluded. A defect in shared test infrastructure stays rankable.

## Node id → (file, symbol)

Node ids that carry a file path spell it as the half before the first
``::`` (pytest ``tests/test_x.py::test_a``, ``tests/test_x.py::K::test_a``;
jest ``src/x.test.ts::suite::case``). The remainder is the symbol path:
``::`` becomes ``.`` (matching the resolver's qualnames) and a pytest
parametrization suffix (``test_a[1-2]``) is cut.

Ecosystems whose node ids carry no file path (go ``package::Test``, cargo
``crate::mod::test``, JUnit ``Class#method``, dotnet FQNs) still produce a
path half, but it can never equal a real covered-file path, so the filter
is a **no-op** there rather than a mis-exclusion. That is the whole safety
argument: the derived strings are only ever compared against paths the
coverage tool actually reported.

## Path bases: exact, then path-suffix

Node-id paths and Coverage Fact paths share a base only when the test
engine's rootdir is the novetest workspace. In a monorepo (a repo-level
``pytest.ini`` above a sub-project that has none) pytest emits
``svc/tests/test_x.py`` while coverage reports ``tests/test_x.py``, the
strict intersection is empty, and the whole filter silently no-ops (L1
finding, issue 1). When *no* node path matches a candidate path exactly,
the node paths are re-keyed onto candidate paths by unique path-suffix
match, indexed by basename. ``ExclusionResult.basis`` reports which of the
two matched, so ``excluded_count == 0`` is no longer ambiguous.

## What is reported back

- Nothing is silently deleted: every positively-scored candidate the
  filter removed is returned in ``suppressed`` (top ``SUPPRESSED_CAP`` by
  score) for the caller to surface. When the bug really is the test's
  expected value the exclusion removes the correct answer and the ranking
  leads with innocent product code (L1 finding, issue 3) — SBFL cannot
  tell that shape apart from the structural bias above (both are
  ``ef = 1, ep = 0`` on the test body), so the remedy is visibility, not a
  score threshold.
- If the exclusion would leave the ranking with no positively-scored
  candidate while the unfiltered ranking had one, it is **reverted** and
  ``reverted=True`` is reported. A user whose every suspect is a test node
  must not get silence.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from novetest.models.run_record import RunRecord


T = TypeVar("T")

#: How many suppressed suspects the caller is handed for its side channel.
#: The list exists so a consumer can see the top suspects the filter
#: removed, not to mirror the whole candidate set into ``metadata``.
SUPPRESSED_CAP: int = 3

#: ``ExclusionResult.basis`` values — how node-id paths met candidate paths.
BASIS_EXACT = "exact"
BASIS_PATH_SUFFIX = "path_suffix"
BASIS_NONE = "none"


def normalize_path(path: str) -> str:
    """Canonical comparison key for a workspace-relative path.

    Folds the two representational differences that can separate a node
    id's path half from a ``CoverageFactSet`` file path for the *same*
    file: Windows separators and a leading ``./``. Nothing else — this is
    a string key, never a filesystem probe (the file may not exist on the
    machine deriving the finding).
    """
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.rstrip("/")


def normalize_symbol(node_id_tail: str) -> str:
    """The symbol half of a node id as the symbol resolver would spell it.

    ``K::test_m`` → ``K.test_m`` (resolver qualnames are dot-joined);
    ``test_a[1-2]`` → ``test_a`` (a parametrized case is the same symbol).
    """
    symbol = node_id_tail.replace("::", ".")
    bracket = symbol.find("[")
    if bracket != -1:
        symbol = symbol[:bracket]
    return symbol.strip()


def discovered_test_nodes(record: RunRecord) -> dict[str, frozenset[str]]:
    """Map ``record``'s test nodes to ``{file: {symbol, ...}}``.

    Every discovered test node counts, not just the failing ones: a
    passing test's body is just as non-actionable a suspect, and the
    passing tests are what make the failing tests' bodies stand out in
    the first place.

    A file mapped to the EMPTY set owns a test node whose symbol half
    could not be derived (``tests/test_x.py::``, or an ecosystem whose
    node id has no ``::`` at all) — the caller excludes such a file whole,
    since narrowing needs a symbol to narrow to. In practice that only
    arises for path-less node ids, whose file key matches no covered file
    anyway.
    """
    nodes: dict[str, set[str]] = defaultdict(set)
    whole_file: set[str] = set()
    for result in record.test_results:
        file_half, _, tail = result.node_id.partition("::")
        file_key = normalize_path(file_half)
        if not file_key:
            continue
        symbol = normalize_symbol(tail)
        if symbol:
            nodes[file_key].add(symbol)
        else:
            whole_file.add(file_key)
            nodes.setdefault(file_key, set())
    return {
        file_key: frozenset() if file_key in whole_file else frozenset(symbols)
        for file_key, symbols in nodes.items()
    }


def discovered_test_files(record: RunRecord) -> frozenset[str]:
    """Normalized paths of the files owning ``record``'s test nodes."""
    return frozenset(discovered_test_nodes(record))


@dataclass(frozen=True, slots=True)
class SuppressedLocation:
    """One positively-scored candidate the filter removed.

    ``score_raw`` is the SELECTED formula's score — the same number the
    surviving entries carry in ``score_raw``, so a consumer can compare
    the two directly.
    """

    file: str
    symbol: str | None
    score_raw: float


@dataclass(frozen=True, slots=True)
class ExclusionResult(Generic[T]):
    """Outcome of applying the exclusion to one mode's candidate list.

    - ``candidates`` — the list to rank (filtered, or the original when
      ``reverted``).
    - ``excluded_count`` — how many candidates the filter matched. Non-zero
      with ``reverted=True`` means "matched, then put back".
    - ``reverted`` — the filter emptied the positively-scored ranking and
      was undone.
    - ``suppressed`` — the removed candidates that scored above zero, best
      first, capped at ``SUPPRESSED_CAP``. Empty when ``reverted`` (nothing
      was removed in the end).
    - ``basis`` — how node-id paths met candidate paths: ``exact``,
      ``path_suffix`` (re-keyed, monorepo rootdir) or ``none`` (no node id
      resembles any candidate path — the expected state for ecosystems
      whose node ids carry no file path).
    """

    candidates: list[T]
    excluded_count: int
    reverted: bool
    suppressed: tuple[SuppressedLocation, ...] = ()
    basis: str = BASIS_NONE


def _is_path_suffix(shorter: str, longer: str) -> bool:
    """Is ``shorter`` the tail of ``longer`` on a path-component boundary?"""
    return longer.endswith("/" + shorter)


def _reconcile_bases(
    test_nodes: Mapping[str, frozenset[str]], candidate_files: frozenset[str]
) -> tuple[Mapping[str, frozenset[str]], str]:
    """Re-key node-id paths onto candidate paths when the bases differ.

    Exact matches win outright. Otherwise each node path is matched to the
    candidate path that shares its basename AND is a path-suffix of it (or
    vice versa: the workspace root can sit either side of the test
    engine's rootdir). Ambiguous basenames — more than one candidate
    qualifies — are left unmatched rather than guessed.
    """
    if not test_nodes:
        return test_nodes, BASIS_NONE
    if any(file_key in candidate_files for file_key in test_nodes):
        return test_nodes, BASIS_EXACT

    by_basename: dict[str, list[str]] = defaultdict(list)
    for candidate_file in candidate_files:
        by_basename[candidate_file.rpartition("/")[2]].append(candidate_file)

    remapped: dict[str, frozenset[str]] = {}
    for file_key, symbols in test_nodes.items():
        peers = [
            peer
            for peer in by_basename.get(file_key.rpartition("/")[2], ())
            if _is_path_suffix(peer, file_key) or _is_path_suffix(file_key, peer)
        ]
        if len(peers) != 1:
            continue
        remapped[peers[0]] = remapped.get(peers[0], frozenset()) | symbols
    if not remapped:
        return test_nodes, BASIS_NONE
    return remapped, BASIS_PATH_SUFFIX


def _is_test_node(symbol: str | None, node_symbols: frozenset[str]) -> bool:
    """Does this candidate's symbol name a test node of its file?

    ``None`` (file-level candidate) and "the file's symbols are unknown"
    both answer yes: at that granularity the evidence cannot separate the
    test from the product, and the pre-narrowing whole-file exclusion is
    the safe default (module docstring, "over-approximations").
    """
    if symbol is None or not node_symbols:
        return True
    return any(
        symbol == node_symbol
        or symbol.startswith(node_symbol + ".")
        or node_symbol.startswith(symbol + ".")
        for node_symbol in node_symbols
    )


def apply_test_file_exclusion(
    candidates: Sequence[T],
    *,
    test_nodes: Mapping[str, frozenset[str]],
    file_of: Callable[[T], str],
    symbol_of: Callable[[T], str | None],
    score_of: Callable[[T], float],
) -> ExclusionResult[T]:
    """Drop test-node candidates, reverting rather than emptying the ranking.

    ``score_of`` reads the SELECTED formula's score. Only positively-scored
    candidates ever become entries (the ANA-08 rule both SBFL modes apply
    downstream), so "would this exclusion empty the ranking?" is decided on
    the positive candidates alone.
    """
    files = [normalize_path(file_of(candidate)) for candidate in candidates]
    nodes, basis = _reconcile_bases(test_nodes, frozenset(files))

    kept: list[T] = []
    dropped: list[SuppressedLocation] = []
    for candidate, file_key in zip(candidates, files, strict=True):
        node_symbols = nodes.get(file_key)
        if node_symbols is not None and _is_test_node(
            symbol_of(candidate), node_symbols
        ):
            score = score_of(candidate)
            if score > 0:
                dropped.append(
                    SuppressedLocation(
                        file=file_of(candidate),
                        symbol=symbol_of(candidate),
                        score_raw=score,
                    )
                )
            continue
        kept.append(candidate)

    excluded_count = len(candidates) - len(kept)
    if excluded_count == 0:
        return ExclusionResult(list(candidates), 0, False, (), basis)

    dropped.sort(key=lambda s: (-s.score_raw, s.file, s.symbol or ""))
    suppressed = tuple(dropped[:SUPPRESSED_CAP])

    if any(score_of(candidate) > 0 for candidate in kept):
        return ExclusionResult(kept, excluded_count, False, suppressed, basis)
    if any(score_of(candidate) > 0 for candidate in candidates):
        # Every positive suspect is a test node — surface them rather than
        # an empty ``entries`` list. Nothing ends up removed, so nothing is
        # reported as suppressed.
        return ExclusionResult(list(candidates), excluded_count, True, (), basis)
    # Nothing is suspicious anywhere; the exclusion changes no output.
    return ExclusionResult(kept, excluded_count, False, (), basis)


__all__ = [
    "BASIS_EXACT",
    "BASIS_NONE",
    "BASIS_PATH_SUFFIX",
    "SUPPRESSED_CAP",
    "ExclusionResult",
    "SuppressedLocation",
    "apply_test_file_exclusion",
    "discovered_test_files",
    "discovered_test_nodes",
    "normalize_path",
    "normalize_symbol",
]
