"""The run of 403 and 429 responses behind the blocking warning (020-add-crawl-core D7)."""

import pytest

from openlinx.crawl.fetch.politeness import BlockingRuns
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawl_result
from tests.support.workspace import TempWorkspace

A, B = "a.test", "b.test"


@pytest.mark.parametrize(
    ("responses", "warned"),
    [
        ([(A, 403)] * 10, [A]),
        ([(A, 429), (A, 403)] * 5, [A]),
        ([(A, 403)] * 12, [A]),
        # Again after a reset: the warning log keeps one warning per host.
        ([(A, 403)] * 10 + [(A, 200)] + [(A, 403)] * 10, [A, A]),
        ([(A, 403)] * 9, []),
        ([(A, 403)] * 9 + [(A, 200)] + [(A, 403)] * 9, []),
        ([(A, 403)] * 9 + [(A, 404)] + [(A, 403)] * 9, []),
        # A request without an HTTP response.
        ([(A, 403)] * 9 + [(A, None)] + [(A, 403)], [A]),
        ([(A, 403)] * 8 + [(A, None)] + [(A, 403)], []),
        ([(A, 403)] * 9 + [(B, 200)] + [(A, 403)], [A]),
        ([(A, 403)] * 5 + [(B, 403)] * 5 + [(A, 403)] * 4, []),
    ],
)
def test_a_host_warns_at_ten_403_or_429_responses_in_a_row(
    responses: list[tuple[str, int | None]], warned: list[str]
) -> None:
    runs = BlockingRuns()

    assert [host for host, status in responses if runs.responded(host, status)] == warned


def test_403_responses_of_an_external_host_raise_no_warning(
    temp_workspace: TempWorkspace, fixture_hosts: StartHosts
) -> None:
    links = "".join(f'<a href="http://other.test/blocked/{n}">{n}</a>' for n in range(1, 13))
    hosts = fixture_hosts(
        Site(routes={"/": Page(body=links)}),
        Site(routes={f"/blocked/{n}": Status(403) for n in range(1, 13)}),
    )

    result = crawl_result("http://site.test/", resolver=hosts.resolver)

    assert [warning.code for warning in result.warnings] == []
