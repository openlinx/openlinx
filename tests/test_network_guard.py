"""The network guard (design D13 of 000-scaffold-project)."""

import socket
import urllib.error
import urllib.request

import aiohttp
import pytest

from tests.support.network import NetworkAccessBlocked

# These tests are blocked on purpose; any other test that is blocked fails (see the last test).
pytestmark = pytest.mark.blocks_remote


def test_a_socket_cannot_connect_to_a_remote_address() -> None:
    with socket.socket() as sock, pytest.raises(NetworkAccessBlocked):
        sock.connect(("93.184.216.34", 80))


def test_a_remote_name_is_not_even_looked_up() -> None:
    with pytest.raises(NetworkAccessBlocked):
        socket.getaddrinfo("example.com", 80)


def test_urlopen_of_a_remote_url_fails_because_of_the_guard() -> None:
    with pytest.raises(urllib.error.URLError) as caught:
        urllib.request.urlopen("http://example.com/", timeout=1)

    assert isinstance(caught.value.reason, NetworkAccessBlocked)


async def test_an_event_loop_connection_to_a_remote_address_is_blocked() -> None:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session:
        with pytest.raises(aiohttp.ClientConnectorError) as caught:
            await session.get("http://93.184.216.34/")

    assert isinstance(caught.value.__cause__, NetworkAccessBlocked)


def test_loopback_stays_reachable() -> None:
    with (
        socket.create_server(("127.0.0.1", 0)) as server,
        socket.create_connection(server.getsockname(), timeout=1) as client,
    ):
        accepted, peer = server.accept()
        with accepted:
            assert peer == client.getsockname()


def test_connect_ex_to_a_remote_address_is_blocked_too() -> None:
    with socket.socket() as sock, pytest.raises(NetworkAccessBlocked):
        sock.connect_ex(("93.184.216.34", 80))


def test_gethostbyname_does_not_look_up_a_remote_name() -> None:
    with pytest.raises(NetworkAccessBlocked):
        socket.gethostbyname("example.com")


def test_gethostbyname_ex_does_not_look_up_a_remote_name() -> None:
    with pytest.raises(NetworkAccessBlocked):
        socket.gethostbyname_ex("example.com")


SWALLOWED = """
import socket


def test_swallows_the_block():
    try:
        socket.getaddrinfo("example.com", 80)
    except OSError:
        pass
"""


def test_a_test_that_swallows_a_blocked_attempt_still_fails(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(SWALLOWED)

    result = pytester.runpytest(
        "-p", "tests.support.isolation", "-o", "asyncio_default_fixture_loop_scope=function"
    )

    result.assert_outcomes(passed=1, errors=1)
