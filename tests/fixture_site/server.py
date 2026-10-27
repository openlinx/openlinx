"""The fixture-site server, aiohttp on 127.0.0.1 in a thread (design D9 of 000-scaffold-project)."""

import asyncio
import socket
import struct
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterator, Sequence
from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

from aiohttp import web
from multidict import CIMultiDict, CIMultiDictProxy

from spider.aio import loop_factory
from tests.fixture_site.routes import (
    CONTENT_TYPES,
    DEFAULT_CONTENT_TYPE,
    Answer,
    LargeFile,
    Page,
    Redirect,
    Responses,
    Robots,
    Site,
    Sitemap,
    SitemapIndex,
    Status,
)


@dataclass(frozen=True)
class LoggedRequest:
    method: str
    path: str
    headers: CIMultiDictProxy[str]
    received_at: float


class RequestLog:
    def __init__(self) -> None:
        self._entries: list[LoggedRequest] = []
        self._lock = threading.Lock()
        self._in_flight = 0
        self._most_in_flight = 0

    def add(self, request: web.Request) -> None:
        entry = LoggedRequest(
            method=request.method,
            path=request.path_qs,
            headers=CIMultiDictProxy(CIMultiDict(request.headers)),
            received_at=time.monotonic(),
        )
        with self._lock:
            self._entries.append(entry)
            self._in_flight += 1
            self._most_in_flight = max(self._most_in_flight, self._in_flight)

    def answered(self) -> None:
        with self._lock:
            self._in_flight -= 1

    @property
    def most_in_flight(self) -> int:
        with self._lock:
            return self._most_in_flight

    def snapshot(self) -> tuple[LoggedRequest, ...]:
        with self._lock:
            return tuple(self._entries)


class ServerHandle:
    def __init__(self, base_url: str, log: RequestLog) -> None:
        self.base_url = base_url
        self._log = log

    def url(self, path: str) -> str:
        return self.base_url + path

    @property
    def requests(self) -> tuple[LoggedRequest, ...]:
        return self._log.snapshot()

    @property
    def most_simultaneous(self) -> int:
        """The most requests the site has handled at once."""
        return self._log.most_in_flight


def _page_response(site: Site, page: Page, base_url: str) -> web.Response:
    if page.file is not None:
        assert site.root is not None
        path = site.root / page.file
        body = path.read_bytes()
        content_type = CONTENT_TYPES.get(path.suffix.lower(), DEFAULT_CONTENT_TYPE)
    else:
        body = (page.body or "").encode()
        content_type = CONTENT_TYPES[".html"]
    if page.template:
        body = body.replace(b"{{base_url}}", base_url.encode())
    return web.Response(body=body, headers={"Content-Type": content_type})


def _sitemap_xml(root: str, entry: str, base_url: str, paths: Sequence[str]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<{root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        *(f"  <{entry}><loc>{escape(base_url + path)}</loc></{entry}>" for path in paths),
        f"</{root}>",
        "",
    ]
    return "\n".join(lines).encode()


def _xml_response(body: bytes) -> web.Response:
    return web.Response(body=body, headers={"Content-Type": CONTENT_TYPES[".xml"]})


def _respond(site: Site, route: Answer, base_url: str) -> web.StreamResponse:
    match route:
        case Page():
            return _page_response(site, route, base_url)
        case Status(code=code, body=None, reason=reason):
            return web.Response(status=code, reason=reason)
        case Status(code=code, body=body, reason=reason):
            return web.Response(
                status=code,
                reason=reason,
                body=(body or "").encode(),
                headers={"Content-Type": CONTENT_TYPES[".html"]},
            )
        case Redirect(location=location, status=status):
            return web.Response(status=status, headers={"Location": location})
        case Robots(text=text):
            return web.Response(body=text.encode(), headers={"Content-Type": CONTENT_TYPES[".txt"]})
        case Sitemap(paths=paths):
            return _xml_response(_sitemap_xml("urlset", "url", base_url, paths))
        case SitemapIndex(paths=paths):
            return _xml_response(_sitemap_xml("sitemapindex", "sitemap", base_url, paths))
        case LargeFile(size=size):
            response = web.StreamResponse(headers={"Content-Type": DEFAULT_CONTENT_TYPE})
            response.content_length = size
            return response


async def _endless_body(
    request: web.Request, response: web.StreamResponse, *, trickle: bool
) -> web.StreamResponse:
    # The declared headers, then a body that never ends: a hostile server's slow read.
    stream = web.StreamResponse(status=response.status, headers=response.headers)
    await stream.prepare(request)
    if not trickle:
        await asyncio.Event().wait()
    while True:
        await stream.write(b" ")
        await asyncio.sleep(0.1)


async def _reset_inside_body(
    request: web.Request, response: web.Response, sent: int
) -> web.StreamResponse:
    body = response.body
    assert isinstance(body, bytes)
    headers = CIMultiDict(response.headers)
    headers.popall("Content-Length", None)
    stream = web.StreamResponse(status=response.status, headers=headers)
    stream.content_length = len(body)
    await stream.prepare(request)
    await stream.write(body[:sent])
    transport = request.transport
    assert transport is not None
    # A zero linger makes the close an RST, as a peer that drops the connection sends.
    transport.get_extra_info("socket").setsockopt(
        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
    )
    transport.abort()
    return stream


def _pattern_chunks(size: int) -> Iterator[bytes]:
    block = bytes(range(256)) * 256
    for start in range(0, size, len(block)):
        yield block[: size - start]


def _build_app(site: Site, base_url: Callable[[], str], log: RequestLog) -> web.Application:
    @web.middleware
    async def logged(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        log.add(request)
        try:
            return await handler(request)
        finally:
            log.answered()

    # Requests so far, per path of a Responses route.
    answered: dict[str, int] = {}

    async def handle(request: web.Request) -> web.StreamResponse:
        found = site.routes.get(request.path)
        if found is None:
            raise web.HTTPNotFound
        if isinstance(found, Responses):
            count = answered.get(request.path, 0)
            answered[request.path] = count + 1
            route = found.answers[min(count, len(found.answers) - 1)]
        else:
            route = found
        if route.delay:
            await asyncio.sleep(route.delay)
        if route.hang:
            await asyncio.Event().wait()
        response = _respond(site, route, base_url())
        if route.content_type is not None:
            response.headers["Content-Type"] = route.content_type
        for name, value in route.headers:
            response.headers.add(name, value)
        if route.reset_after is not None:
            assert isinstance(response, web.Response)
            return await _reset_inside_body(request, response, route.reset_after)
        if route.stall_body or route.trickle:
            return await _endless_body(request, response, trickle=route.trickle)
        if isinstance(route, LargeFile):
            await response.prepare(request)
            for chunk in _pattern_chunks(route.size):
                await response.write(chunk)
            await response.write_eof()
        return response

    app = web.Application(middlewares=[logged])
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


class ThreadedApp:
    """An aiohttp app on 127.0.0.1, served from a thread of its own."""

    def __init__(self, app: web.Application, name: str) -> None:
        self._in_flight: set[asyncio.Task[Any]] = set()
        app.middlewares.append(self._track)
        self._loop = loop_factory()
        self._thread = threading.Thread(target=self._loop.run_forever, name=name)
        self._thread.start()
        self._runner = web.AppRunner(app)
        try:
            self._call(self._runner.setup())
            self._call(web.TCPSite(self._runner, "127.0.0.1", 0).start())
        except BaseException:
            self._stop_loop()
            raise
        host, port = self._runner.addresses[0][:2]
        self.base_url = f"http://{host}:{port}"

    @web.middleware
    async def _track(
        self, request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        task = asyncio.current_task()
        assert task is not None
        self._in_flight.add(task)
        try:
            return await handler(request)
        finally:
            self._in_flight.discard(task)

    def _call[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    async def _cancel_in_flight(self) -> None:
        for task in list(self._in_flight):
            task.cancel()

    def _stop_loop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def stop(self) -> None:
        # Handlers first: runner.cleanup() waits up to 60 s for open ones (hang, delay).
        try:
            self._call(self._cancel_in_flight())
            self._call(self._runner.cleanup())
        finally:
            self._stop_loop()


class RunningServer:
    def __init__(self, site: Site) -> None:
        log = RequestLog()
        self._app = ThreadedApp(
            _build_app(site, lambda: self.handle.base_url, log), name="fixture-site"
        )
        self.handle = ServerHandle(self._app.base_url, log)

    def stop(self) -> None:
        self._app.stop()
