"""Smoke test: package imports cleanly. Replace/extend as modules land."""

import chronosync


def test_version_is_set() -> None:
    assert chronosync.__version__
