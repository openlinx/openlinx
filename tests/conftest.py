"""Plugins, hypothesis profiles, test loop (designs D5, D13 and D15 of 000-scaffold-project)."""

import asyncio
import os
from collections.abc import Callable, Mapping

from hypothesis import settings

from spider.aio import loop_factory

pytest_plugins = ["pytester", "tests.support.isolation", "tests.support.workspace"]

settings.register_profile("dev")
settings.register_profile("ci", deadline=None, print_blob=True, max_examples=200)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


def pytest_asyncio_loop_factories() -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
    return {"loop_factory": loop_factory}
