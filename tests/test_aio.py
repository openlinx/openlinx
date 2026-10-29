"""`openlinx.aio.loop_factory` (design D15 of 000-scaffold-project)."""

import asyncio
import sys
from contextlib import closing

import pytest

from openlinx.aio import loop_factory


@pytest.mark.skipif(sys.platform != "win32", reason="the Proactor loop exists only on Windows")
def test_windows_gets_a_proactor_loop() -> None:
    with closing(loop_factory()) as loop:
        if sys.platform == "win32":
            assert type(loop) is asyncio.ProactorEventLoop


@pytest.mark.skipif(sys.platform == "win32", reason="Windows gets the Proactor loop")
def test_other_systems_get_a_selector_loop() -> None:
    with closing(loop_factory()) as loop:
        assert type(loop) is asyncio.SelectorEventLoop


async def test_async_tests_run_on_the_loop_that_loop_factory_makes() -> None:
    with closing(loop_factory()) as reference:
        expected = type(reference)

    assert type(asyncio.get_running_loop()) is expected
