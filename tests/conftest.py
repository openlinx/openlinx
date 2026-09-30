"""Test plugins, hypothesis profiles and the test event loop (designs D5 and D15 of 000)."""

import asyncio
import os
from collections.abc import Callable, Mapping

import pytest
from hypothesis import settings

from spider.aio import loop_factory

pytest_plugins = ["pytester", "tests.support.isolation", "tests.support.workspace"]

settings.register_profile("dev")
settings.register_profile("ci", deadline=None, print_blob=True, max_examples=200)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_asyncio_loop_factories(
    config: pytest.Config, item: pytest.Item
) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    return {"loop_factory": loop_factory}
