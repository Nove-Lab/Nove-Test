"""Wire tests: an unrecognized output mode refuses inside the envelope.

Delivery-phasing board row 48 (superseding row 37(d) with the confirmation
that the failure is verb-universal, not verb-specific).

``resolve_output_mode`` is the very first thing ``main()`` does — before
the pre-parse that ``01588ea`` added, so the envelope machinery that now
covers ``--help``, ``<verb> --version`` and every Cyclopts usage error
never got a chance to run. ``OutputMode(value)`` raised a bare
``ValueError`` straight out of the enum: a raw Python traceback on stderr,
**zero bytes on stdout**, on every single verb. An agent piping stdout
through a JSON parser got an empty-string parse failure with no diagnosis
— precisely the failure mode the row-30 lane existed to eliminate, one
capitalization (``NOVETEST_OUTPUT=JSON``) away from any docs-following
consumer.

Asserted on the REAL subprocess bytes. Exit code is 2 (``EXIT_USAGE``) —
the same bucket ``_validate_engine_flag``'s ``invalid-flag`` uses, since a
bad value for a known option is a configuration/usage problem. The broader
exit-code-policy question (row 37(a): Cyclopts-level usage errors exit 1
while handler-level flag validation exits 2) is deliberately NOT touched
here; this closes "no envelope at all", nothing more.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def _envelope(stdout: str) -> dict[str, Any]:
    """Parse stdout the way an agent's ``json.tool`` pipe would."""

    payload = json.loads(stdout)
    assert isinstance(payload, dict)
    assert payload["schema"] == "novetest/v1"
    return payload


class TestInvalidOutputModeIsAnEnvelope:
    @pytest.mark.parametrize(
        ("args", "env_overrides", "expected_source"),
        [
            (["--version"], {"NOVETEST_OUTPUT": "bogus"}, "NOVETEST_OUTPUT"),
            (["--version", "--output=bogus"], None, "--output"),
        ],
        ids=["env-var", "explicit-flag"],
    )
    def test_refusal_is_parseable_json_with_exit_2(
        self,
        run_cli: Any,
        args: list[str],
        env_overrides: dict[str, str] | None,
        expected_source: str,
    ) -> None:
        result = run_cli(args, env_overrides=env_overrides)

        assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
        assert result.stdout, "stdout must not be empty — that was the whole defect"
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["errors"], payload
        error = payload["errors"][0]
        assert error["code"] == "invalid-output-mode"
        assert error["details"]["value"] == "bogus"
        assert error["details"]["source"] == expected_source
        assert error["details"]["supported"] == ["text", "json", "ndjson"]

    def test_no_raw_traceback_reaches_stderr(self, run_cli: Any) -> None:
        """The negative half: a traceback is what the fix removes."""

        result = run_cli(["--version"], env_overrides={"NOVETEST_OUTPUT": "bogus"})
        assert "Traceback (most recent call last)" not in result.stderr
        assert "is not a valid OutputMode" not in result.stderr

    def test_wrong_capitalization_is_the_realistic_mistake(
        self, run_cli: Any
    ) -> None:
        """``NOVETEST_OUTPUT=JSON`` — one plausible slip from the docs.

        Matching stays exact: ``JSON`` is REFUSED rather than silently
        accepted as ``json``. A mode that resolves differently depending on
        capitalization is a worse contract than one that refuses and says
        which values it takes — but the refusal has to be readable, which
        is what this asserts.
        """

        result = run_cli(["status"], env_overrides={"NOVETEST_OUTPUT": "JSON"})
        assert result.returncode == 2
        payload = _envelope(result.stdout)
        assert payload["errors"][0]["details"]["value"] == "JSON"

    @pytest.mark.parametrize(
        "verb",
        [["--version"], ["--help"], ["status"], ["test"], ["memory", "list"], []],
        ids=["version", "help", "status", "test", "memory-list", "bare"],
    )
    def test_the_failure_is_verb_universal(self, run_cli: Any, verb: list[str]) -> None:
        """Row 48's headline claim, asserted rather than assumed.

        The refusal happens before verb dispatch, so EVERY surface must
        answer identically — including bare ``novetest`` and ``--help``,
        which never reach a handler at all.
        """

        result = run_cli(verb, env_overrides={"NOVETEST_OUTPUT": "bogus"})
        assert result.returncode == 2, verb
        payload = _envelope(result.stdout)
        assert payload["ok"] is False
        assert payload["command"] == "cli"
        assert payload["errors"][0]["code"] == "invalid-output-mode"

    def test_valid_modes_are_untouched(self, run_cli: Any) -> None:
        """Guard: the fix must not have changed the accepting path.

        Every supported value still resolves and still exits 0 on
        ``--version``.
        """

        for mode in ("text", "json", "ndjson"):
            result = run_cli(["--version"], env_overrides={"NOVETEST_OUTPUT": mode})
            assert result.returncode == 0, (mode, result.stderr)
            assert result.stdout
