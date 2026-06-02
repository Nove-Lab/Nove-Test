from flaky_python.flaky_module import flaky_outcome


def test_flaky_outcome_is_even_invocation() -> None:
    """Passes on even subprocess invocations, fails on odd ones.

    Deterministic within a single process (the counter is read once);
    divergent across subprocess invocations (the counter persists on disk).
    The original run is invocation 0 → even → pass; replay reruns alternate.
    """
    assert flaky_outcome() is True
