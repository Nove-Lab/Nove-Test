"""Unit tests for ``notices_loader`` — the NOTICES.md resolution strategy.

Pins the load-bearing precedence decision: **source tree first, installed
distribution metadata second**, ``LookupError`` if neither resolves. The
source-tree-first order is why an editable install (whose ``*.dist-info``
copy can be stale) still reports the live working-tree ``NOTICES.md``.
"""

from __future__ import annotations

import pytest

from novetest.orchestration.licenses import notices_loader
from novetest.orchestration.licenses.notices_loader import read_notices_text


def test_reads_live_source_tree_notices() -> None:
    text = read_notices_text()
    assert text.startswith("# Third-Party Notices\n")
    # The live (post-2026-06-19 expansion) file is ~15.5 KB — proves we read
    # the source tree, not a stale 2 KB dist-info copy.
    assert len(text) > 15000


def test_source_tree_is_tried_before_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "# Third-Party Notices\nSOURCE-TREE-SENTINEL\n"
    monkeypatch.setattr(notices_loader, "_read_from_source_tree", lambda: sentinel)

    def _fail() -> str | None:
        raise AssertionError("distribution path must not be consulted when source tree resolves")

    monkeypatch.setattr(notices_loader, "_read_from_distribution", _fail)
    assert read_notices_text() == sentinel


def test_falls_back_to_distribution_when_no_source_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notices_loader, "_read_from_source_tree", lambda: None)
    monkeypatch.setattr(
        notices_loader, "_read_from_distribution", lambda: "# Third-Party Notices\nFROM-DIST\n"
    )
    assert read_notices_text() == "# Third-Party Notices\nFROM-DIST\n"


def test_raises_lookuperror_when_neither_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(notices_loader, "_read_from_source_tree", lambda: None)
    monkeypatch.setattr(notices_loader, "_read_from_distribution", lambda: None)
    with pytest.raises(LookupError):
        read_notices_text()
