# flaky-python

Nove Test fixture: a deliberately **flaky** pytest project used to validate
Replay flakiness classification (`inconsistent`).

The single test `tests/test_flaky_behavior.py::test_flaky_outcome_is_even_invocation`
asserts `flaky_outcome() is True`. `flaky_outcome()` reads and increments an
on-disk invocation counter (`.flaky_invocations` at the project root):

- **Within one subprocess** the counter is read once → fixed outcome (so the
  original `novetest run` is byte-identically storable).
- **Across subprocess invocations** the counter increments → outcome flips by
  parity (even = pass, odd = fail).

Invocation 0 (original run) passes; replay reruns alternate fail/pass, so a
`novetest replay <run_id> --reruns=5` yields a divergent mix that the Replay
classifier labels `inconsistent`.

The counter file is created lazily in the workspace copy at run time; it is
NOT committed. Delete `.flaky_invocations` to reset the parity.
