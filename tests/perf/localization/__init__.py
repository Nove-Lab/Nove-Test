"""Localization-engine performance benchmarks (NFR-LOC-002).

Mirrors the Coverage perf precedent (``tests/perf/coverage/``). Lives
outside ``[tool.pytest.ini_options].testpaths`` so ``uv run pytest`` does
NOT auto-collect it; run explicitly via ``uv run pytest tests/perf``.
"""
