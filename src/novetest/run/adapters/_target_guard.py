"""Boundary Test Target guards shared by the adapters.

Two platform-independent, pre-spawn rejection guards live here:

- ``reject_dash_leading_target`` — dash-leading value would be parsed as
  an engine flag (RUN-22, W1/S1).
- ``reject_shell_metachar_target`` — a ``cmd.exe`` metacharacter would be
  interpreted by the Windows command interpreter on the ``cmd /c``
  launcher paths (jest ``cmd /c npx``, junit ``cmd /c mvn``/``gradle``),
  a shell-injection / RCE surface (RUN-09 [RCE·Windows] / RUN-10, W1/S5).

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

    ``kind="invalid-target"`` is dedicated to this boundary rejection
    (W1/S8 companion slice; W1/S1 originally reused the
    ``unparseable-output`` invocation-level catch-all because its data
    contract froze the kind set). The CLI projects it to the envelope
    error code ``adapter-invalid-target``, so agents can distinguish
    "flag-shaped target" from "engine output could not be parsed".
    """

    if target_expression.startswith("-"):
        raise AdapterInvocationError(
            f"target_expression {target_expression!r} begins with '-' and would "
            f"be consumed as a {engine_label} flag, not a test target; pass a "
            "path / node id / test filter instead (for a file whose name "
            "really starts with '-', prefix it with './')",
            kind="invalid-target",
        )


# The ``cmd.exe`` special characters. A ``target_expression`` carrying any
# of these would be interpreted by the Windows command interpreter on the
# ``cmd /c`` launcher paths (jest's ``cmd /c npx``, junit's ``cmd /c mvn``
# / ``cmd /c gradle``) — a shell-injection / RCE surface when the target
# originates from an untrusted repository (a malicious test name or file
# name). We reject UNCONDITIONALLY (every platform), matching the
# platform-independent posture of ``reject_dash_leading_target``: the
# check is a cheap substring scan, these characters are never legitimate
# in a jest test-path pattern or a junit ``-Dtest``/``--tests`` filter,
# and one uniform rule keeps the six-engine argv-hygiene contract simple.
_CMD_METACHARACTERS: frozenset[str] = frozenset("&|<>^%\"")


def reject_shell_metachar_target(
    target_expression: str, *, engine_label: str
) -> None:
    """Raise ``invalid-target`` when ``target_expression`` carries a
    ``cmd.exe`` metacharacter (``& | < > ^ % "``).

    Defends the ``cmd /c`` launcher paths (jest ``cmd /c npx``, junit
    ``cmd /c mvn`` / ``cmd /c gradle``) against shell-metacharacter
    injection (review finding RUN-09 [RCE·Windows] / RUN-10). Rejected
    BEFORE any subprocess spawn, mirroring ``reject_dash_leading_target``,
    and projected by the CLI to the envelope error code
    ``adapter-invalid-target`` (exit 2, usage error — reclassified from
    exit 4 by the 2026-07-09 decision). A target whose filename
    legitimately contains one of these characters is out of scope — it is
    rejected loudly with an actionable message rather than silently
    shell-quoted.
    """

    found = sorted(c for c in _CMD_METACHARACTERS if c in target_expression)
    if found:
        raise AdapterInvocationError(
            f"target_expression {target_expression!r} contains shell "
            f"metacharacter(s) {''.join(found)!r} that the Windows command "
            f"interpreter would interpret on the {engine_label} launcher path "
            "(command injection); pass a path / node id / test filter with none "
            'of the & | < > ^ % " characters',
            kind="invalid-target",
        )


__all__ = ["reject_dash_leading_target", "reject_shell_metachar_target"]
