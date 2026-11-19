"""Shared data platform library for the semantic layer comparison study.

Pure PySpark transformations used by the Lakeflow pipelines and jobs under
02-implementations/platform and exercised locally by scripts/test_platform.py.
Nothing in this package writes data; callers own all side effects.
"""

__all__ = ["calendar", "nyctaxi", "replay", "schema", "wwi"]
