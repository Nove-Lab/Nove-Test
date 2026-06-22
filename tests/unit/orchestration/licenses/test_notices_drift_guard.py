"""Drift guard between the static ``LICENSE_ENTRIES`` const and ``NOTICES.md``.

The const is the machine-readable mirror of the canonical ``NOTICES.md``
attribution document. This guard fails the build if the two diverge, in
either direction, so a manual edit to one that is not mirrored into the
other is caught before merge.

**Join key = ``project_url``.** A literal heading/license string match is NOT
reliable because ``NOTICES.md`` is a human document whose display form
diverges from the machine-readable const (verified empirically against the
file this guard reads):

* The vendored entry's ``###`` heading is the display name *JUnit Platform
  Console Standalone*, not the package id ``junit-platform-console-standalone``.
* ``python-build-standalone``'s heading carries ``CPython`` inline with no
  ``(version)`` parenthetical.
* The runtime entries' ``- License:`` bullets carry a ``— verbatim text:
  [...]`` markdown-link suffix.
* ``python-build-standalone``'s license is wrapped prose ("Python Software
  Foundation License plus permissive licenses for sub-components (...)")
  whereas the const pins the compact form "PSF + permissive (...)".

The ``project_url`` (``- Project:`` bullet) is byte-identical on both sides
for all five entries, so it is the stable join key. License equality is
checked after normalization (link-suffix stripped, whitespace collapsed),
falling back to a shared-distinctive-parenthetical check for the one prose
license. Version is checked only where the heading exposes a ``(version)``.

NOTE (surfaced to PM): the brief's §"Field semantics" says ``package`` is
"as it appears in the NOTICES.md ``### <package>`` heading", but the pinned
JSON data contract uses package *ids* (e.g. ``junit-platform-console-standalone``)
that differ from the NOTICES display headings. This guard reconciles the two
via ``project_url`` rather than failing; see the handoff question.
"""

from __future__ import annotations

import re

from novetest.orchestration.licenses import LICENSE_ENTRIES, read_notices_text

_TARGET_SECTIONS: dict[str, str] = {
    "## Runtime dependencies": "runtime",
    "## Vendored binary": "vendored",
    "## Install-time bootstrap": "install-time-bootstrap",
}


def _section_source(heading_line: str) -> str | None:
    for prefix, source in _TARGET_SECTIONS.items():
        if heading_line.startswith(prefix):
            return source
    return None


def _normalize_license(value: str) -> str:
    # Strip the markdown "— verbatim text: [...]" link suffix; collapse ws.
    for separator in ("—", " -- "):  # — == em dash
        if separator in value:
            value = value.split(separator, 1)[0]
    return " ".join(value.split())


def _heading_version(heading: str) -> str | None:
    match = re.search(r"\(([^()]+)\)\s*$", heading)
    return match.group(1) if match else None


def _parse_notices_dependency_sections(text: str) -> list[dict[str, str]]:
    """Parse the dependency ``###`` blocks under the three attribution ``##``.

    Sections outside the three target ``##`` headers (e.g. ``## License
    texts``) are ignored. License values are normalized; multi-line wrapped
    ``- License:`` bullets are joined.
    """

    entries: list[dict[str, str]] = []
    current_source: str | None = None
    current: dict[str, str] | None = None
    lines = text.split("\n")
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
                current = None
            current_source = _section_source(line)
        elif line.startswith("### "):
            if current is not None:
                entries.append(current)
                current = None
            if current_source is not None:
                current = {
                    "source": current_source,
                    "heading": line[4:].strip(),
                    "project_url": "",
                    "license": "",
                }
        elif current is not None:
            if line.startswith("- Project:"):
                current["project_url"] = line.split(":", 1)[1].strip()
            elif line.startswith("- License:"):
                raw = line.split(":", 1)[1].strip()
                look = index + 1
                while look < total:
                    nxt = lines[look]
                    stripped = nxt.strip()
                    is_continuation = (
                        nxt.startswith(" ")
                        and stripped != ""
                        and not stripped.startswith("- ")
                        and not nxt.lstrip().startswith("#")
                    )
                    if not is_continuation:
                        break
                    raw += " " + stripped
                    look += 1
                index = look - 1
                current["license"] = _normalize_license(raw)
        index += 1

    if current is not None:
        entries.append(current)
    return entries


def _extract_paren(value: str) -> str:
    start = value.find("(")
    end = value.rfind(")")
    return value[start : end + 1] if start != -1 and end > start else ""


def _license_consistent(const_license: str, notices_license: str) -> bool:
    const_norm = " ".join(const_license.lower().split())
    notices_norm = " ".join(notices_license.lower().split())
    if const_norm == notices_norm or const_norm in notices_norm or notices_norm in const_norm:
        return True
    # Prose-abbreviation case: require the distinctive shared parenthetical
    # (e.g. "(openssl, libffi, ncurses, etc.)").
    paren = _extract_paren(const_norm)
    return bool(paren) and paren in notices_norm


def test_every_static_entry_has_matching_notices_section() -> None:
    parsed = _parse_notices_dependency_sections(read_notices_text())
    by_url = {section["project_url"]: section for section in parsed}

    for entry in LICENSE_ENTRIES:
        assert entry.project_url in by_url, (
            f"{entry.package}: no NOTICES.md section with "
            f"`- Project: {entry.project_url}`"
        )
        section = by_url[entry.project_url]
        assert section["source"] == entry.source, (
            f"{entry.package}: source group mismatch "
            f"(const={entry.source!r}, NOTICES={section['source']!r})"
        )
        assert _license_consistent(entry.license, section["license"]), (
            f"{entry.package}: license {entry.license!r} inconsistent with "
            f"NOTICES.md {section['license']!r}"
        )
        heading_version = _heading_version(section["heading"])
        if heading_version is not None:
            assert heading_version == entry.version, (
                f"{entry.package}: version mismatch "
                f"(const={entry.version!r}, NOTICES heading={heading_version!r})"
            )


def test_every_notices_section_has_matching_static_entry() -> None:
    parsed = _parse_notices_dependency_sections(read_notices_text())
    by_url = {entry.project_url: entry for entry in LICENSE_ENTRIES}

    assert len(parsed) == len(LICENSE_ENTRIES), (
        f"NOTICES.md exposes {len(parsed)} dependency sections under the three "
        f"attribution headers; the const has {len(LICENSE_ENTRIES)}"
    )
    for section in parsed:
        assert section["project_url"] in by_url, (
            f"NOTICES.md section {section['heading']!r} "
            f"({section['project_url']}) has no LICENSE_ENTRIES match"
        )
        entry = by_url[section["project_url"]]
        assert entry.source == section["source"]
        assert _license_consistent(entry.license, section["license"])


def test_parser_finds_exactly_the_five_known_urls() -> None:
    parsed = _parse_notices_dependency_sections(read_notices_text())
    assert {section["project_url"] for section in parsed} == {
        "https://github.com/BrianPugh/cyclopts",
        "https://github.com/numpy/numpy",
        "https://github.com/junit-team/junit5",
        "https://github.com/ofek/pyapp",
        "https://github.com/indygreg/python-build-standalone",
    }
