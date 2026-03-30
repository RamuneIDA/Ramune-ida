"""Shared pytest configuration and fixtures."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-ida", action="store_true", default=False,
        help="Run tests that require a real IDA Pro installation",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "ida: requires real IDA Pro")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-ida"):
        return
    skip_ida = pytest.mark.skip(reason="need --run-ida to run")
    for item in items:
        if "ida" in item.keywords:
            item.add_marker(skip_ida)
