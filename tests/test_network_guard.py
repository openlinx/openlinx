"""The network guard (design D13 of 000-scaffold-project)."""

import socket

import pytest

from tests.support.network import NetworkAccessBlocked


def test_a_socket_cannot_connect_to_a_remote_address() -> None:
    with pytest.raises(NetworkAccessBlocked):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
