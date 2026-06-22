"""Unit tests for the ``licenses`` data view assembly.

The ``LicensesView`` is the ``data`` payload of the ``novetest licenses``
envelope. These tests pin the contract surface AI agents parse against: the
5-component list, the opt-in ``notices_text`` body, and the two literal
``summary`` / ``notices_reference`` strings (drift guards).
"""

from __future__ import annotations

from novetest.orchestration.licenses import (
    LICENSE_ENTRIES,
    NOTICES_REFERENCE,
    SUMMARY,
    build_licenses_view,
)

_EXPECTED_PACKAGES = (
    "cyclopts",
    "numpy",
    "junit-platform-console-standalone",
    "PyApp",
    "python-build-standalone",
)
_VALID_SOURCES = {"runtime", "vendored", "install-time-bootstrap"}


def test_default_view_enumerates_5_packages() -> None:
    view = build_licenses_view(include_full=False)
    assert len(view.licenses) == 5
    assert tuple(e.package for e in view.licenses) == _EXPECTED_PACKAGES


def test_default_view_omits_notices_text() -> None:
    view = build_licenses_view(include_full=False)
    assert view.notices_text is None
    assert "notices_text" not in view.to_dict()


def test_full_view_includes_notices_text() -> None:
    view = build_licenses_view(include_full=True)
    assert view.notices_text is not None
    assert view.notices_text.startswith("# Third-Party Notices\n")
    assert len(view.notices_text) > 15000
    assert view.to_dict()["notices_text"] == view.notices_text


def test_summary_string_is_pinned() -> None:
    view = build_licenses_view(include_full=False)
    assert view.summary == "Nove Test redistributes or links to 5 third-party components."
    assert view.summary == SUMMARY


def test_notices_reference_is_pinned() -> None:
    view = build_licenses_view(include_full=False)
    assert view.notices_reference == "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)"
    assert view.notices_reference == NOTICES_REFERENCE


def test_each_entry_has_valid_source_and_full_shape() -> None:
    for entry in LICENSE_ENTRIES:
        assert entry.source in _VALID_SOURCES
        assert entry.project_url.startswith("https://")
        payload = entry.to_dict()
        assert set(payload) == {"package", "version", "license", "source", "project_url"}


def test_to_dict_key_set_is_stable() -> None:
    assert set(build_licenses_view(include_full=False).to_dict()) == {
        "summary",
        "licenses",
        "notices_reference",
    }
    assert set(build_licenses_view(include_full=True).to_dict()) == {
        "summary",
        "licenses",
        "notices_reference",
        "notices_text",
    }
