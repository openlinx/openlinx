"""The network guard (design D13 of 000-scaffold-project)."""

import socket
import urllib.error
import urllib.request

import pytest

from tests.support.network import NetworkAccessBlocked


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
