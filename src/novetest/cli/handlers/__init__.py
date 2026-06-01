"""Thin per-verb CLI handlers.

Each handler exports a pure function ``build_<verb>_envelope`` that takes
the resolved workflow inputs and returns ``(Envelope, exit_code)``. The
``cli/app.py`` registration layer wraps these in Cyclopts commands and
applies ``_emit_and_exit`` / ``_require_store`` boilerplate around them
— per the team charter ("CLI handlers are thin: wrap orchestration calls
+ the v1 JSON envelope; no business logic in cli/").

This package was introduced at Phase 6 entry to keep the integrated
``novetest test`` envelope-building logic isolated from the Cyclopts
dispatch surface, so the envelope shape can be unit-tested without
spawning a subprocess. Older verbs (init, run, status, inspect, memory
*, coverage *, regression *, compare, localization) remain inlined in
``cli/app.py``; migrating them is out of scope of this slice.
"""

__all__: list[str] = []
