"""`Responses` routes: a path answering each request in turn (022-add-fetch-policy D9)."""

import http.client
from urllib.parse import urlsplit

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Site, Status
from tests.fixture_site.server import ServerHandle


def _get(server: ServerHandle, path: str) -> tuple[int, bytes]:
    address = urlsplit(server.base_url)
    connection = http.client.HTTPConnection(address.hostname or "", address.port, timeout=10)
    try:
        connection.request("GET", path)
        with connection.getresponse() as response:
            return response.status, response.read()
    finally:
        connection.close()


def test_a_responses_route_answers_its_routes_in_turn_then_repeats_the_last(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(
        Site({"/flaky": Responses((Status(503), Status(502), Page(body="<p>Back</p>")))})
    )

    answers = [_get(server, "/flaky") for _ in range(4)]

    assert [status for status, _ in answers] == [503, 502, 200, 200]
    assert answers[-1][1] == b"<p>Back</p>"


def test_each_responses_route_counts_its_own_requests(fixture_site: StartSite) -> None:
    flaky = Responses((Status(503), Page(body="<p>Up</p>")))
    server = fixture_site(Site({"/a": flaky, "/b": flaky}))

    assert [_get(server, path)[0] for path in ("/a", "/b", "/a", "/b")] == [503, 503, 200, 200]
