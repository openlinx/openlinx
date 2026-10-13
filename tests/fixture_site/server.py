"""The fixture-site server, aiohttp on 127.0.0.1 in a thread (design D9 of 000-scaffold-project)."""

import asyncio
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
    Bytes,
    LargeFile,
    Page,
    Redirect,
    Robots,
    Route,
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
    def __init__(self, *, keep: bool = True) -> None:
        self._entries: list[LoggedRequest] = []
        self._lock = threading.Lock()
        self._keep = keep

    def add(self, request: web.Request) -> None:
        if not self._keep:
            return
        entry = LoggedRequest(
            method=request.method,
            path=request.path_qs,
            headers=CIMultiDictProxy(CIMultiDict(request.headers)),
            received_at=time.monotonic(),
        )
        with self._lock:
            self._entries.append(entry)

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


def _respond(site: Site, route: Route, base_url: str) -> web.StreamResponse:
    match route:
        case Page():
            return _page_response(site, route, base_url)
        case Status(code=code):
            return web.Response(status=code)
        case Redirect(location=location, status=status):
            return web.Response(status=status, headers={"Location": location})
        case Robots(text=text):
            return web.Response(body=text.encode(), headers={"Content-Type": CONTENT_TYPES[".txt"]})
        case Sitemap(paths=paths):
            return _xml_response(_sitemap_xml("urlset", "url", base_url, paths))
        case SitemapIndex(paths=paths):
            return _xml_response(_sitemap_xml("sitemapindex", "sitemap", base_url, paths))
        case Bytes(data=data):
            return web.Response(body=data, headers={"Content-Type": DEFAULT_CONTENT_TYPE})
        case LargeFile(size=size):
            response = web.StreamResponse(headers={"Content-Type": DEFAULT_CONTENT_TYPE})
            response.content_length = size
            return response


def _pattern_chunks(size: int) -> Iterator[bytes]:
    block = bytes(range(256)) * 256
    for start in range(0, size, len(block)):
        yield block[: size - start]


def _build_app(
    site: Site, base_url: Callable[[], str], in_flight: set[asyncio.Task[Any]], log: RequestLog
) -> web.Application:
    @web.middleware
    async def log_and_track(
        request: web.Request, handler: Callable[[web.Request], Awaitable[web.StreamResponse]]
    ) -> web.StreamResponse:
        log.add(request)
        task = asyncio.current_task()
        assert task is not None
        in_flight.add(task)
        try:
            return await handler(request)
        finally:
            in_flight.discard(task)

    async def handle(request: web.Request) -> web.StreamResponse:
        route = site.routes.get(request.path)
        if route is None and site.resolve is not None:
            route = site.resolve(request.path)
        if route is None:
            raise web.HTTPNotFound
        if route.delay:
            await asyncio.sleep(route.delay)
        if route.hang:
            await asyncio.Event().wait()
        response = _respond(site, route, base_url())
        if route.content_type is not None:
            response.headers["Content-Type"] = route.content_type
        for name, value in route.headers:
            response.headers.add(name, value)
        if isinstance(route, LargeFile):
            await response.prepare(request)
            for chunk in _pattern_chunks(route.size):
                await response.write(chunk)
            await response.write_eof()
        return response

    app = web.Application(middlewares=[log_and_track])
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


class RunningServer:
    def __init__(self, site: Site, *, keep_log: bool = True) -> None:
        self._loop = loop_factory()
        self._thread = threading.Thread(target=self._loop.run_forever, name="fixture-site")
        self._thread.start()
        self._in_flight: set[asyncio.Task[Any]] = set()
        log = RequestLog(keep=keep_log)
        app = _build_app(site, lambda: self.handle.base_url, self._in_flight, log)
        self._runner = web.AppRunner(app)
        try:
            self._call(self._runner.setup())
            self._call(web.TCPSite(self._runner, "127.0.0.1", 0).start())
        except BaseException:
            self._stop_loop()
            raise
        host, port = self._runner.addresses[0][:2]
        self.handle = ServerHandle(f"http://{host}:{port}", log)

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
