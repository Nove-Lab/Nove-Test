"""Dash-leading Test Target guard shared by the bare-argv adapters.

pytest, go-test, and cargo-nextest receive ``target_expression`` as a bare
positional argv element, so a dash-leading value (``--pdb``,
``-p no:cacheprovider``, ``-run X``, ``--ignored``) would be parsed as an
ENGINE FLAG instead of a test target — silent flag injection (review
finding RUN-22, fixed in refactoring slice W1/S1).

Why rejection instead of a ``--`` separator (the frozen wave-1 text
prescribed ``--`` for pytest/jest/cargo — empirically verified 2026-07-07,
divergence recorded in the W1/S1 handoff):

- **pytest 9.0.3**: ``--`` does NOT terminate option parsing —
  ``pytest -q -- --collect-only`` still runs collect-only mode, so the
  separator is ineffective.
- **cargo-nextest 0.9.137**: args after ``--`` are TEST-BINARY args, not
  positional filters. Unsupported ones error loudly, but the libtest
  emulation set is still consumed as flags (``cargo nextest run --
  --ignored`` silently flips selection to ignored-only tests).
- **go test** has no ``--`` terminator at the go-command level (``-args``
  has different, test-binary-forwarding semantics).
- **jest 29.7.0** is the exception: yargs pins everything after ``--`` as
  positionals, so the jest adapter uses the separator instead of this
  guard (dash-leading patterns stay expressible there).

junit (``-Dtest=<expr>``) and dotnet (``FullyQualifiedName~<expr>``) embed
the value inside a flag argument and are structurally immune — no guard.
All six adapters' end-state is pinned by
``tests/unit/run/adapters/test_target_argv_hygiene.py``.
"""

from __future__ import annotations

from novetest.run.errors import AdapterInvocationError


def reject_dash_leading_target(target_expression: str, *, engine_label: str) -> None:
    """Raise a typed error when ``target_expression`` starts with ``-``.

    ``kind="unparseable-output"`` is reused deliberately: the W1/S1 data
    contract pins the ``AdapterInvocationError`` kind set as unchanged, and
    ``unparseable-output`` is the established invocation-level catch-all
    (build failures use it too). A dedicated ``invalid-target`` kind is a
    candidate for the S8 error-code contract slice.
    """

    if target_expression.startswith("-"):
        raise AdapterInvocationError(
            f"target_expression {target_expression!r} begins with '-' and would "
            f"be consumed as a {engine_label} flag, not a test target; pass a "
            "path / node id / test filter instead (for a file whose name "
            "really starts with '-', prefix it with './')",
            kind="unparseable-output",
        )


__all__ = ["reject_dash_leading_target"]
