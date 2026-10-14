"""The network guard: tests reach only loopback (design D13 of 000-scaffold-project)."""

import asyncio
import ipaddress
import socket
from contextlib import closing
from functools import cache
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


def _check_host(host: object, blocked: list[str]) -> None:
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host is not None and not _is_loopback(str(host)):
        blocked.append(f"resolve {host!r}")
        raise NetworkAccessBlocked(f"tests may resolve only loopback names, not {host!r}")


def _check_address(address: object, blocked: list[str]) -> None:
    if isinstance(address, tuple) and not _is_loopback(str(address[0])):
        blocked.append(f"connect to {address!r}")
        raise NetworkAccessBlocked(f"tests may connect only to loopback, not to {address!r}")


@cache
def _loop_type() -> type[asyncio.AbstractEventLoop]:
    with closing(loop_factory()) as loop:
        return type(loop)


def block_remote_connections(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Blocks remote names and addresses, and returns the list of what it blocked."""
    blocked: list[str] = []
    getaddrinfo = socket.getaddrinfo
    gethostbyname = socket.gethostbyname
    gethostbyname_ex = socket.gethostbyname_ex
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        _check_host(host, blocked)
        return getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host: str) -> str:
        _check_host(host, blocked)
        return gethostbyname(host)

    def guarded_gethostbyname_ex(host: str) -> tuple[str, list[str], list[str]]:
        _check_host(host, blocked)
        return gethostbyname_ex(host)

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        _check_address(address, blocked)
        connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: Any) -> int:
        _check_address(address, blocked)
        return connect_ex(sock, address)

    loop_type = _loop_type()
    sock_connect = loop_type.sock_connect

    # The Windows Proactor loop connects through ConnectEx and never calls socket.connect.
    async def guarded_sock_connect(
        loop: asyncio.AbstractEventLoop, sock: socket.socket, address: Any
    ) -> None:
        _check_address(address, blocked)
        await sock_connect(loop, sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket, "gethostbyname", guarded_gethostbyname)
    monkeypatch.setattr(socket, "gethostbyname_ex", guarded_gethostbyname_ex)
    monkeypatch.setattr(loop_type, "sock_connect", guarded_sock_connect)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    return blocked


def closed_port() -> int:
    """A loopback port that nothing listens on when this returns."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    return port
