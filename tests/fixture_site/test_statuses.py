"""`Status` routes (design D9 of 000-scaffold-project)."""

import http.client
from urllib.parse import urlsplit

import aiohttp
import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Site, Status
from tests.fixture_site.server import ServerHandle

STATUSES = Site(routes={f"/s/{code}": Status(code) for code in range(200, 600)})


@pytest.fixture(scope="module")
def statuses(module_fixture_site: StartSite) -> ServerHandle:
    return module_fixture_site(STATUSES)


def status_of(server: ServerHandle, path: str) -> int:
    address = urlsplit(server.base_url)
    connection = http.client.HTTPConnection(address.hostname or "", address.port, timeout=10)
    try:
        connection.request("GET", path)
        with connection.getresponse() as response:
            response.read()
            return response.status
    finally:
        connection.close()


@given(code=st.integers(min_value=200, max_value=599))
def test_a_status_route_answers_with_its_status(statuses: ServerHandle, code: int) -> None:
    assert status_of(statuses, f"/s/{code}") == code


async def test_a_status_route_may_answer_with_an_html_body(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/gone": Status(404, body='<a href="/x">X</a>')}))

    async with aiohttp.ClientSession() as session, session.get(server.url("/gone")) as response:
        body = await response.read()

    assert (response.status, response.headers["Content-Type"], body) == (
        404,
        "text/html; charset=utf-8",
        b'<a href="/x">X</a>',
    )


def test_a_status_route_may_answer_with_its_own_reason_phrase(fixture_site: StartSite) -> None:
    server = fixture_site(Site(routes={"/old": Status(404, reason="Page Not Here")}))
    address = urlsplit(server.base_url)
    connection = http.client.HTTPConnection(address.hostname or "", address.port, timeout=10)
    try:
        connection.request("GET", "/old")
        with connection.getresponse() as response:
            response.read()
            answered = (response.status, response.reason)
    finally:
        connection.close()

    assert answered == (404, "Page Not Here")
