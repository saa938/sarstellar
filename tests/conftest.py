"""Shared pytest setup: network tests are marked `live` and skipped by default."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.live (they need network and Earthdata credentials)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "live: needs network access; skipped unless -m live")


def _live_requested(config) -> bool:
    if config.getoption("--run-live"):
        return True
    markexpr = config.getoption("-m") or ""
    return "live" in markexpr and "not live" not in markexpr


def pytest_collection_modifyitems(config, items):
    if _live_requested(config):
        return
    skip_live = pytest.mark.skip(reason="live network test; run with -m live or --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
