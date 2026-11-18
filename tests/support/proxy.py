"""Relay HTTP and tunnel HTTPS through a local proxy with separate CONNECT logs."""

import asyncio
import ssl
import threading
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

import aiohttp
import yarl
from aiohttp import web
from aiohttp.abc import AbstractResolver
from multidict import CIMultiDict, CIMultiDictProxy

from openlinx.aio import loop_factory

# Headers of one connection, which a proxy never relays, and the framing aiohttp sets itself.
_NOT_RELAYED = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "content-length",
    }
)


@dataclass(frozen=True, slots=True)
class ConnectRequest:
    method: str
    target: str
    headers: CIMultiDictProxy[str]


@dataclass(frozen=True, slots=True)
class ConnectReply:
    """Bytes sent by the fixture proxy before relaying or closing the connection."""

    chunks: tuple[bytes, ...] = (b"HTTP/1.1 200 Connection Established\r\n\r\n",)
    relay: bool = True

    async def send(self, writer: asyncio.StreamWriter) -> None:
        for chunk in self.chunks:
            writer.write(chunk)
            await writer.drain()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65_536):
        writer.write(data)
        await writer.drain()


async def _relay_bytes(
    client: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    tasks = (
        asyncio.create_task(_pipe(client, upstream_writer)),
        asyncio.create_task(_pipe(upstream, client_writer)),
    )
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class ForwardProxy:
    """Relay absolute-form HTTP and CONNECT, resolving fixture names at the proxy:
    the client resolves only the proxy's address, and retains origin TLS verification."""

    def __init__(
        self,
        resolver: AbstractResolver,
        *,
        auth: tuple[str, str] | None = None,
        connect_replies: tuple[ConnectReply, ...] = (),
        strict_connect_host: bool = False,
        tls: ssl.SSLContext | None = None,
    ) -> None:
        self._resolver = resolver
        self._authorization = aiohttp.encode_basic_auth(*auth) if auth is not None else None
        self._connect_replies = connect_replies or (ConnectReply(),)
        self._strict_connect_host = strict_connect_host
        self._tls = tls
        self._requests: list[str] = []
        self._connect_requests: list[ConnectRequest] = []
        self._lock = threading.Lock()
        self._tasks: set[asyncio.Task[Any]] = set()
        self._errors: list[BaseException] = []
        self._server: asyncio.Server | None = None
        self._closing = False
        app = web.Application()
        app.middlewares.append(self._track_http)
        app.router.add_route("*", "/{tail:.*}", self._relay)
        self._runner = web.AppRunner(app)
        self._loop = loop_factory()
        self._thread = threading.Thread(target=self._loop.run_forever, name="forward-proxy")
        self._thread.start()
        try:
            self.url = self._call(self._start())
        except BaseException:
            self.stop()
            raise

    def _call[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    async def _start(self) -> str:
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        address = self._runner.addresses[0]
        self._http_address = (str(address[0]), int(address[1]))
        # aiohttp's path router cannot serve authority-form CONNECT; keep its HTTP relay
        # behind a TCP listener that takes ownership of tunnel bytes without private APIs.
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0, ssl=self._tls)
        host, port = self._server.sockets[0].getsockname()[:2]
        scheme = "https" if self._tls is not None else "http"
        return f"{scheme}://{host}:{port}"

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self._closing:
            writer.close()
            return
        task = asyncio.create_task(self._serve(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            self._errors.append(error)

    @web.middleware
    async def _track_http(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        task = asyncio.current_task()
        assert task is not None
        if self._closing:
            raise asyncio.CancelledError
        self._tasks.add(task)
        try:
            return await handler(request)
        finally:
            self._tasks.discard(task)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            first, *lines = head.decode("latin-1").split("\r\n")
            method, target, _ = first.split(" ", 2)
            if method == "CONNECT":
                headers: CIMultiDict[str] = CIMultiDict()
                for line in lines:
                    if line:
                        name, value = line.split(":", 1)
                        headers.add(name, value.strip())
                with self._lock:
                    index = len(self._connect_requests)
                    self._connect_requests.append(
                        ConnectRequest(method, target, CIMultiDictProxy(headers))
                    )
                if self._strict_connect_host and headers.getall("Host", []) != [target]:
                    writer.write(
                        b"HTTP/1.1 400 Host differs from CONNECT authority\r\n"
                        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                    await writer.drain()
                    return
                if (
                    self._authorization is not None
                    and headers.get("Proxy-Authorization") != self._authorization
                ):
                    writer.write(
                        b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                        b'Proxy-Authenticate: Basic realm="fixture"\r\n'
                        b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                    await writer.drain()
                    return
                reply = self._connect_replies[min(index, len(self._connect_replies) - 1)]
                if not reply.relay:
                    await reply.send(writer)
                    return
                origin = yarl.URL(f"//{target}")
                [address] = await self._resolver.resolve(origin.host or "", origin.port or 443)
                upstream, upstream_writer = await asyncio.open_connection(
                    address["host"], address["port"], family=address["family"]
                )
                await reply.send(writer)
            else:
                upstream, upstream_writer = await asyncio.open_connection(*self._http_address)
                upstream_writer.write(head)
                await upstream_writer.drain()
            await _relay_bytes(reader, writer, upstream, upstream_writer)
        except (asyncio.IncompleteReadError, ConnectionError):
            # A client can close while sending its header, TLS handshake or tunnel bytes.
            pass
        finally:
            writers = [writer] if upstream_writer is None else [writer, upstream_writer]
            for stream in writers:
                stream.close()
            for stream in writers:
                with suppress(ConnectionError):
                    await stream.wait_closed()

    @property
    def requests(self) -> tuple[str, ...]:
        """The URL of each request relayed, in the order received."""
        with self._lock:
            return tuple(self._requests)

    @property
    def connect_requests(self) -> tuple[ConnectRequest, ...]:
        """CONNECT attempts, including rejected ones, separate from relayed HTTP URLs."""
        with self._lock:
            return tuple(self._connect_requests)

    async def _shutdown(self) -> None:
        self._closing = True
        if self._server is not None:
            self._server.close()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()
        await self._runner.cleanup()
        await self._loop.shutdown_asyncgens()

    def stop(self) -> None:
        try:
            self._call(self._shutdown())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()
        if self._errors:
            raise AssertionError(f"Proxy handlers failed: {self._errors!r}")

    async def _relay(self, request: web.Request) -> web.Response:
        # The request target as received: a proxy request names an absolute URL.
        target = yarl.URL(request.raw_path, encoded=True)
        if not target.absolute:
            return web.Response(status=400, text="A proxy request names an absolute URL.")
        with self._lock:
            self._requests.append(str(target))
        async with (
            aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(resolver=self._resolver),
                auto_decompress=False,
                cookie_jar=aiohttp.DummyCookieJar(),
            ) as session,
            session.request(
                request.method,
                target,
                headers=_relayed(request.headers),
                data=await request.read(),
                allow_redirects=False,
            ) as relayed,
        ):
            body = await relayed.read()
            return web.Response(status=relayed.status, headers=_relayed(relayed.headers), body=body)


def _relayed(headers: Mapping[str, str]) -> CIMultiDict[str]:
    return CIMultiDict(
        (name, value) for name, value in headers.items() if name.lower() not in _NOT_RELAYED
    )


class StartProxy(Protocol):
    def __call__(
        self,
        resolver: AbstractResolver,
        *,
        auth: tuple[str, str] | None = None,
        connect_replies: tuple[ConnectReply, ...] = (),
        strict_connect_host: bool = False,
        tls: ssl.SSLContext | None = None,
    ) -> ForwardProxy: ...
