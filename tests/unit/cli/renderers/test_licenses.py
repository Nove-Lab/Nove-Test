"""Renderer tests for the ``licenses`` verb text surface.

Snapshots the default summary block and the ``--full`` append (with a small
sentinel body — the real 15 KB NOTICES.md body is covered by the integration
substring tests, not snapshotted). Routes through ``render_text`` so the
registry wiring is exercised too.
"""

from __future__ import annotations

from typing import Any

from syrupy.assertion import SnapshotAssertion

from novetest.cli.output import Envelope, EnvelopeError
from novetest.cli.renderers import render_text

_LICENSES: list[dict[str, Any]] = [
    {
        "package": "cyclopts",
        "version": ">=3.0",
        "license": "Apache-2.0",
        "source": "runtime",
        "project_url": "https://github.com/BrianPugh/cyclopts",
    },
    {
        "package": "numpy",
        "version": ">=1.26",
        "license": "BSD-3-Clause",
        "source": "runtime",
        "project_url": "https://github.com/numpy/numpy",
    },
    {
        "package": "junit-platform-console-standalone",
        "version": "1.11.4",
        "license": "EPL-2.0",
        "source": "vendored",
        "project_url": "https://github.com/junit-team/junit5",
    },
    {
        "package": "PyApp",
        "version": "0.22.0",
        "license": "Apache-2.0 OR MIT",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/ofek/pyapp",
    },
    {
        "package": "python-build-standalone",
        "version": "CPython",
        "license": "PSF + permissive (OpenSSL, libffi, ncurses, etc.)",
        "source": "install-time-bootstrap",
        "project_url": "https://github.com/indygreg/python-build-standalone",
    },
]


def _default_data() -> dict[str, Any]:
    return {
        "summary": "Nove Test redistributes or links to 5 third-party components.",
        "licenses": _LICENSES,
        "notices_reference": "NOTICES.md (in wheel at *.dist-info/licenses/NOTICES.md)",
    }


def test_render_licenses_default(snapshot: SnapshotAssertion) -> None:
    envelope = Envelope(command="licenses", ok=True, data=_default_data())
    assert render_text(envelope) == snapshot


def test_render_licenses_full_appends_verbatim(snapshot: SnapshotAssertion) -> None:
    data = _default_data()
    data["notices_text"] = "# Third-Party Notices\n\n<verbatim body sentinel>\n"
    envelope = Envelope(command="licenses", ok=True, data=data)
    assert render_text(envelope) == snapshot


def test_render_licenses_error_gates_to_error_block() -> None:
    envelope = Envelope(
        command="licenses",
        ok=False,
        errors=(EnvelopeError(code="notices-unavailable", message="NOTICES.md not found"),),
    )
    rendered = render_text(envelope)
    assert rendered.startswith("✗ licenses")
    assert "notices-unavailable: NOTICES.md not found" in rendered
