"""``novetest licenses`` data model: the static third-party attribution list.

``LICENSE_ENTRIES`` is the machine-readable mirror of ``NOTICES.md`` (the
canonical attribution document at the repo root). It is hand-maintained to
match the data contract pinned in the licenses-verb task brief. The guard at
``tests/unit/orchestration/licenses/test_notices_drift_guard.py`` fails the
build if the const and ``NOTICES.md`` drift apart — joined on
``project_url`` (the only field that is byte-identical on both sides; the
NOTICES headings use display names and the license bullets carry link
suffixes / prose, so a literal heading/license match is not reliable).

``build_licenses_view`` is a pure assembly function; it performs NO I/O
unless ``include_full=True`` requests the verbatim ``NOTICES.md`` body (read
via ``notices_loader.read_notices_text``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from novetest.orchestration.licenses.notices_loader import read_notices_text

__all__ = [
    "LICENSE_ENTRIES",
    "NOTICES_REFERENCE",
    "SUMMARY",
    "LicenseEntry",
    "LicensesView",
    "build_licenses_view",
    "read_notices_text",
]

# Pinned strings (drift-guarded). ``SUMMARY`` is a literal, NOT a computed
# "{n} components" string — the count is part of the contract.
SUMMARY = "Nove Test redistributes or links to 5 third-party components."
NOTICES_REFERENCE = "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)"


@dataclass(slots=True, frozen=True)
class LicenseEntry:
    package: str
    version: str
    license: str
    source: str  # "runtime" | "vendored" | "install-time-bootstrap"
    project_url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "package": self.package,
            "version": self.version,
            "license": self.license,
            "source": self.source,
            "project_url": self.project_url,
        }


LICENSE_ENTRIES: tuple[LicenseEntry, ...] = (
    LicenseEntry(
        package="cyclopts",
        version=">=3.0",
        license="Apache-2.0",
        source="runtime",
        project_url="https://github.com/BrianPugh/cyclopts",
    ),
    LicenseEntry(
        package="numpy",
        version=">=1.26",
        license="BSD-3-Clause",
        source="runtime",
        project_url="https://github.com/numpy/numpy",
    ),
    LicenseEntry(
        package="junit-platform-console-standalone",
        version="1.11.4",
        license="EPL-2.0",
        source="vendored",
        project_url="https://github.com/junit-team/junit5",
    ),
    LicenseEntry(
        package="PyApp",
        version="0.22.0",
        license="Apache-2.0 OR MIT",
        source="install-time-bootstrap",
        project_url="https://github.com/ofek/pyapp",
    ),
    LicenseEntry(
        package="python-build-standalone",
        version="CPython",
        license="PSF + permissive (OpenSSL, libffi, ncurses, etc.)",
        source="install-time-bootstrap",
        project_url="https://github.com/indygreg/python-build-standalone",
    ),
)


@dataclass(slots=True, frozen=True)
class LicensesView:
    summary: str
    licenses: tuple[LicenseEntry, ...]
    notices_reference: str
    notices_text: str | None  # present only when --full

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "summary": self.summary,
            "licenses": [entry.to_dict() for entry in self.licenses],
            "notices_reference": self.notices_reference,
        }
        if self.notices_text is not None:
            data["notices_text"] = self.notices_text
        return data


def build_licenses_view(include_full: bool) -> LicensesView:
    """Assemble the ``data`` payload for the ``licenses`` envelope.

    Pure when ``include_full`` is ``False`` (no I/O). When ``True``, reads
    the verbatim ``NOTICES.md`` body — which may raise ``LookupError`` if the
    file cannot be located (surfaced as ``notices-unavailable`` at the CLI).
    """

    notices_text = read_notices_text() if include_full else None
    return LicensesView(
        summary=SUMMARY,
        licenses=LICENSE_ENTRIES,
        notices_reference=NOTICES_REFERENCE,
        notices_text=notices_text,
    )
