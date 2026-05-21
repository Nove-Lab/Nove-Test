"""Performance benchmarks.

This tree sits OUTSIDE ``[tool.pytest.ini_options].testpaths`` (which is
``tests/unit`` + ``tests/integration``), so the default ``uv run pytest``
never collects it — the same pattern ``tests/release/`` uses. Run the perf
suite explicitly with ``uv run pytest tests/perf``.
"""
