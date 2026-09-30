"""Tests never inherit a proxy from the environment (design D13 of 000-scaffold-project)."""

import os

import pytest

INNER_TEST = """
import os

PROXY_VARIABLES = {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY"}


def test_no_proxy_variable_is_set():
    assert [name for name in os.environ if name.upper() in PROXY_VARIABLES] == []
"""


def test_a_proxy_in_the_environment_does_not_reach_a_test(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("https_proxy", "http://proxy.invalid:3128")
    pytester.makepyfile(INNER_TEST)

    result = pytester.runpytest(
        "-p", "tests.support.isolation", "-o", "asyncio_default_fixture_loop_scope=function"
    )

    result.assert_outcomes(passed=1)


def test_a_test_can_still_set_a_proxy_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.test:3128")

    assert os.environ["HTTP_PROXY"] == "http://proxy.test:3128"
