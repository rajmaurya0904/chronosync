"""Smoke test: package imports cleanly. Replace/extend as modules land."""

import chronosync


def test_version_is_set() -> None:
    assert chronosync.__version__ == "0.1.0"


def test_all_exposes_version() -> None:
    assert "__version__" in chronosync.__all__
