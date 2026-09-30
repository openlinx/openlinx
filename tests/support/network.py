"""The network guard: tests reach only loopback (design D13 of 000-scaffold-project)."""

import asyncio
import ipaddress
import socket
from contextlib import closing
from typing import Any

import pytest

from spider.aio import loop_factory


class NetworkAccessBlocked(OSError):
    pass


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_address(address: object) -> None:
    if isinstance(address, tuple) and not _is_loopback(str(address[0])):
        raise NetworkAccessBlocked(f"tests may connect only to loopback, not to {address!r}")


def block_remote_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    getaddrinfo = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if host is not None and not _is_loopback(host):
            raise NetworkAccessBlocked(f"tests may resolve only loopback names, not {host!r}")
        return getaddrinfo(host, *args, **kwargs)

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        _check_address(address)
        connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        _check_address(address)
        return connect_ex(sock, address)

    with closing(loop_factory()) as loop:
        loop_type = type(loop)
    sock_connect = loop_type.sock_connect

    # The Windows Proactor loop connects through ConnectEx and never calls socket.connect.
    async def guarded_sock_connect(
        loop: asyncio.AbstractEventLoop, sock: socket.socket, address: Any
    ) -> None:
        _check_address(address)
        await sock_connect(loop, sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(loop_type, "sock_connect", guarded_sock_connect)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
