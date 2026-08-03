"""Fixture package for ``pytest-fixture-error``.

Intentionally healthy, exactly like ``pytest-collection-error``'s package. The
defects this fixture reproduces live in the test modules' **pytest fixtures**
(setup and teardown), not in this code — which is the point: nothing is wrong
with the production module, and yet a run of the suite establishes nothing
about it.
"""
