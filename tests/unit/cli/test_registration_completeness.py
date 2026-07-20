"""Completeness guard across the three command-registration sites (ORC-11 / S46).

A verb is registered in THREE independent places that must stay in lockstep:

1. the Cyclopts ``@app.command`` tree (``cli/app.py``) — the runtime surface;
2. ``cli/renderers/registry._RENDERERS`` — the verb → text-renderer dispatch;
3. ``orchestration/onboarding/command_surface`` — the ``--help`` catalog.

Before S46 nothing enforced their agreement: adding, renaming, or dropping a
verb in one site alone slipped through silently (a missing renderer falls back
to ``render_fallback``; a missing surface entry just vanishes from ``--help``).
These tests derive the canonical token set from the LIVE app tree and turn both
silent sites loud at test time.

Two structural facts about the mapping:

- ``--version`` / ``--help`` are Cyclopts built-in flag-commands, not
  ``@app.command`` registrations, yet they DO emit envelopes and so carry a
  renderer and a surface entry. They are the closed ``PSEUDO_COMMANDS`` set.
- ``localization latest`` USED to be a real, renderer-backed subcommand the
  onboarding catalog did not advertise (while its sibling ``regression latest``
  was). That asymmetry was closed at Gate-1 D4=A (2026-07-20, W2c6/S19 rider):
  the mirroring ``CommandSpec`` was added and the token dropped from
  ``KNOWN_SURFACE_OMISSIONS`` in the SAME commit. The catalog now covers the
  app tree with ZERO omissions — ``KNOWN_SURFACE_OMISSIONS`` is empty, and any
  newly-unadvertised verb (or a re-opened omission) fails the gap test below.
"""

from __future__ import annotations

from cyclopts import App

from novetest.cli.app import app
from novetest.cli.renderers.registry import _RENDERERS
from novetest.orchestration.onboarding.command_surface import (
    describe_command_surface,
)

# Built-in ``--version`` / ``--help`` flag-commands: they render an envelope
# (hence a renderer + a surface entry) but never appear as ``@app.command``.
PSEUDO_COMMANDS = frozenset({"version", "help"})

# Real commands the onboarding catalog does not advertise. Empty since Gate-1
# D4=A (2026-07-20) advertised ``localization latest`` — the catalog now covers
# the app tree exactly. Pinned so the gap cannot silently grow (or a new
# omission reopen) without updating this constant in lockstep.
KNOWN_SURFACE_OMISSIONS: frozenset[str] = frozenset()


def _app_command_tokens(sub_app: App | None = None, prefix: str = "") -> set[str]:
    """Collect every runnable command token from the live Cyclopts app tree.

    Tokens are dotted (``memory.list``, ``localization.latest``) to match the
    ``_RENDERERS`` key form. In Cyclopts 4.x each ``@app.command`` becomes a
    child ``App`` whose ``default_command`` is the verb body; a pure group
    (``memory``) has no ``default_command`` but real subcommands; a group that
    is itself runnable (``localization``, with a ``@app.default``) has both.
    Built-in flag keys (``--help`` / ``-h`` / ``--version``) are skipped.
    """

    current = app if sub_app is None else sub_app
    tokens: set[str] = set()
    for name, child in current._commands.items():
        if name.startswith("-"):  # --help / -h / --version built-ins
            continue
        token = f"{prefix}{name}"
        if isinstance(child, App):
            if child.default_command is not None:
                tokens.add(token)  # a runnable verb (leaf or group-with-default)
            real_subs = any(
                not k.startswith("-") for k in child._commands
            )
            if real_subs:
                tokens |= _app_command_tokens(child, prefix=f"{token}.")
        else:  # pragma: no cover - defensive; not seen in cyclopts 4.x
            tokens.add(token)
    return tokens


def _surface_command_tokens() -> set[str]:
    """Map every ``CommandSpec`` display name to its dotted command token."""

    surface = describe_command_surface()
    tokens: set[str] = set()
    for spec in list(surface.onboarding) + list(surface.operating):
        assert spec.name.startswith("novetest "), spec.name
        rest = spec.name[len("novetest ") :].strip()
        if rest.startswith("--"):
            tokens.add(rest[2:])  # "--version" -> "version"
        else:
            tokens.add(".".join(rest.split()))  # "memory list" -> "memory.list"
    return tokens


def test_app_tree_walk_is_not_vacuous() -> None:
    """Guard against a cyclopts-internals change silently emptying the walk
    (which would make the equality tests pass vacuously) and pin that the
    walk descends into both pure groups and default+subcommand groups."""

    tree = _app_command_tokens()
    assert len(tree) >= 15, tree
    assert {"init", "run", "memory.list", "localization", "localization.latest"} <= (
        tree
    )


def test_renderer_registry_matches_app_tree_exactly() -> None:
    """Every runtime command has a text renderer and every renderer maps to a
    real command (or the version/help pseudo-commands) — no drift either way."""

    tree = _app_command_tokens()
    renderer_keys = set(_RENDERERS)
    expected = tree | PSEUDO_COMMANDS
    assert renderer_keys == expected, (
        "cli/renderers/registry._RENDERERS drifted from the Cyclopts app tree. "
        f"Missing renderers (registered command, no renderer): "
        f"{sorted(expected - renderer_keys)}; orphan renderers (renderer, no "
        f"command): {sorted(renderer_keys - expected)}."
    )


def test_onboarding_surface_advertises_no_phantom_commands() -> None:
    """Every advertised command maps to a real command (or version/help) — a
    surface entry for an unimplemented verb (e.g. ``workspaces``) fails here."""

    tree = _app_command_tokens()
    phantom = _surface_command_tokens() - tree - PSEUDO_COMMANDS
    assert not phantom, (
        "command_surface advertises tokens that map to no registered command "
        f"(and are not the version/help pseudo-commands): {sorted(phantom)}"
    )


def test_onboarding_surface_gap_matches_documented_known_omissions() -> None:
    """The set of real commands NOT advertised is exactly the tracked
    ``KNOWN_SURFACE_OMISSIONS`` — a new unadvertised verb, or closing a known
    omission, forces this constant to be updated in lockstep."""

    tree = _app_command_tokens()
    gap = (tree | PSEUDO_COMMANDS) - _surface_command_tokens()
    assert gap == KNOWN_SURFACE_OMISSIONS, (
        "command_surface coverage of the app tree changed. Newly UNadvertised "
        f"commands: {sorted(gap - KNOWN_SURFACE_OMISSIONS)}; known omissions "
        f"now advertised (drop from KNOWN_SURFACE_OMISSIONS): "
        f"{sorted(KNOWN_SURFACE_OMISSIONS - gap)}. Known omissions are tracked "
        "in agent-comms/questions/orchestration-team-2026-07-16-"
        "localization-latest-onboarding-surface.md."
    )
