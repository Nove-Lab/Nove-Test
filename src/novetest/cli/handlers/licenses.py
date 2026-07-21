"""``novetest licenses`` verb handler (W3/S47, ORC-01).

Extracted verbatim from ``cli/app.py``. Lists the third-party components
Nove Test redistributes or links to; ``--full`` appends the verbatim
NOTICES.md body. Pure motion — the wire contract is unchanged.
"""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter

from novetest.cli._shared import _emit_and_exit
from novetest.cli.output import EXIT_GENERIC, EXIT_OK, Envelope, EnvelopeError


def licenses_cmd(
    *,
    full: Annotated[bool, Parameter(name=["--full"])] = False,
) -> None:
    """List third-party components Nove Test redistributes or links to.

    With ``--full``, the envelope also carries the verbatim NOTICES.md text
    body in ``data.notices_text`` (the complete attribution document, ~15 KB).
    Without it, ``data`` carries the compact 5-component summary list only.
    """
    from novetest.orchestration.licenses import build_licenses_view

    try:
        view = build_licenses_view(include_full=full)
    except LookupError as exc:
        _emit_and_exit(
            Envelope(
                command="licenses",
                ok=False,
                errors=(EnvelopeError(code="notices-unavailable", message=str(exc)),),
            ),
            EXIT_GENERIC,
        )
    _emit_and_exit(
        Envelope(command="licenses", ok=True, data=view.to_dict()),
        EXIT_OK,
    )
