"""Smoke test: package imports cleanly. Replace/extend as modules land."""

import re

import chronosync


def test_version_is_set() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", chronosync.__version__)


def test_all_exposes_version() -> None:
    assert "__version__" in chronosync.__all__


def test_version_matches_installed_metadata() -> None:
    from importlib.metadata import version

    assert version("chronosync") == chronosync.__version__
