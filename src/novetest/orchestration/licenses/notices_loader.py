"""Resolve the verbatim ``NOTICES.md`` body for the ``novetest licenses`` verb.

Two resolution strategies, tried in this order:

1. **Source tree** (editable install / source checkout / running from a
   clone): walk up from this module's location to the first ancestor holding
   *both* ``pyproject.toml`` and ``NOTICES.md`` and read it. This is the
   authoritative live copy whenever Nove Test runs from its own source tree
   — which is every dev / test / CI environment, and precisely the case
   where an installed ``*.dist-info`` copy may be **stale** (an editable
   install pins the ``NOTICES.md`` snapshot from whenever the package was
   last ``pip install``-ed, not the current working-tree edit).

2. **Installed distribution metadata** (a real published wheel / PyApp
   single-binary with no source tree above this module): read the PEP 639
   license file embedded at ``*.dist-info/licenses/NOTICES.md`` via
   ``importlib.metadata``. ``Distribution.read_text`` is tried for both the
   bare and the ``licenses/``-prefixed name because the bare name resolves
   to ``*.dist-info/NOTICES.md`` — which PEP 639 does not populate — and
   returns ``None``.

The source-tree strategy is tried FIRST (not the brief's suggested
distribution-first order) for one empirical reason: in an editable install
the embedded ``*.dist-info/licenses/NOTICES.md`` is whatever shipped at the
last ``pip install`` and goes stale the moment ``NOTICES.md`` is edited in
the working tree. Source-tree-first makes dev/test always read the live
file; a true installed wheel (no ``pyproject.toml`` ancestor) falls through
to the dist-info copy, which for a freshly built wheel is current.

If neither resolves, raise ``LookupError`` — surfaced as the envelope error
``notices-unavailable`` at the CLI boundary (``cli/app.py::licenses_cmd``).
"""

from __future__ import annotations

from importlib.metadata import Distribution, PackageNotFoundError
from pathlib import Path

_NOTICES_FILENAME = "NOTICES.md"
_DISTRIBUTION_NAME = "novetest"
# PEP 639 embeds license files under ``<dist-info>/licenses/``; the bare name
# resolves to ``<dist-info>/NOTICES.md`` (unpopulated) and returns ``None``.
_DISTRIBUTION_CANDIDATES = (_NOTICES_FILENAME, f"licenses/{_NOTICES_FILENAME}")


def read_notices_text() -> str:
    """Return the verbatim ``NOTICES.md`` body (UTF-8, LF line endings).

    Raises ``LookupError`` when the file cannot be located by either strategy.
    """

    from_source = _read_from_source_tree()
    if from_source is not None:
        return from_source
    from_distribution = _read_from_distribution()
    if from_distribution is not None:
        return from_distribution
    raise LookupError(
        "NOTICES.md could not be located: no ancestor of "
        f"{Path(__file__).resolve().parent} holds both pyproject.toml and "
        "NOTICES.md, and the installed distribution metadata does not embed it."
    )


def _read_from_source_tree() -> str | None:
    for ancestor in Path(__file__).resolve().parents:
        notices = ancestor / _NOTICES_FILENAME
        if notices.is_file() and (ancestor / "pyproject.toml").is_file():
            return notices.read_text(encoding="utf-8")
    return None


def _read_from_distribution() -> str | None:
    try:
        distribution = Distribution.from_name(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return None
    for candidate in _DISTRIBUTION_CANDIDATES:
        try:
            text = distribution.read_text(candidate)
        except (FileNotFoundError, OSError):
            text = None
        if text is not None:
            return text
    return None
