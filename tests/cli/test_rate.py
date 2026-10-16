"""The rate limit at the CLI (020-add-crawl-core D7, crawling; seam 1)."""

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.workspace import TempWorkspace

_NOT_RATES = ["0", "-1", "nan", "inf"]
_RATES = ["0.5", "2"]


@pytest.mark.parametrize("rate", _NOT_RATES)
def test_a_rate_that_is_not_a_finite_number_above_zero_is_rejected(
    temp_workspace: TempWorkspace, rate: str
) -> None:
    result = run_cli("crawl", "http://site.test/", f"--rate={rate}")

    assert (
        result.exit_code,
        [(error["code"], "--rate" in error["message"]) for error in result.errors()],
    ) == (2, [("invalid_value", True)])


@pytest.mark.parametrize("rate", _NOT_RATES)
def test_a_rate_that_is_not_a_finite_number_above_zero_in_the_settings_file_is_refused(
    temp_workspace: TempWorkspace, rate: str
) -> None:
    # nan and inf are TOML floats as written.
    (temp_workspace.root / "spider.toml").write_bytes(f"[crawl]\nrate = {rate}\n".encode())

    result = run_cli("crawl", "http://site.test/")

    assert (
        result.exit_code,
        [
            (error["code"], problem["key"])
            for error in result.errors()
            for problem in error["details"]["errors"]
        ],
    ) == (3, [("settings_invalid", "crawl.rate")])


@pytest.mark.parametrize("rate", _RATES)
def test_a_finite_rate_above_zero_is_taken(
    temp_workspace: TempWorkspace, fixture_site: StartSite, rate: str
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>/</p>")}))

    result = run_cli("crawl", server.url("/"), "--rate", rate)

    assert (result.exit_code, result.errors()) == (0, [])
