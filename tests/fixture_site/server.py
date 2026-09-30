"""The fixture-site server: aiohttp on 127.0.0.1 in a background thread (design D9 of 000)."""

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

from aiohttp import web

from spider.aio import loop_factory
from tests.fixture_site.routes import CONTENT_TYPES, DEFAULT_CONTENT_TYPE, Page, Route, Site


class ServerHandle:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def url(self, path: str) -> str:
        return self.base_url + path


def _page_response(site: Site, page: Page) -> web.Response:
    if page.file is not None:
        assert site.root is not None, "a Page with a file needs Site(root=...)"
        path = site.root / page.file
        body = path.read_bytes()
        content_type = CONTENT_TYPES.get(path.suffix.lower(), DEFAULT_CONTENT_TYPE)
    else:
        body = (page.body or "").encode()
        content_type = CONTENT_TYPES[".html"]
    return web.Response(body=body, headers={"Content-Type": content_type})


def _respond(site: Site, route: Route) -> web.StreamResponse:
    return _page_response(site, route)


def _build_app(site: Site) -> web.Application:
    async def handle(request: web.Request) -> web.StreamResponse:
        route = site.routes.get(request.path)
        if route is None:
            raise web.HTTPNotFound
        return _respond(site, route)

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handle)
    return app


class RunningServer:
    def __init__(self, site: Site) -> None:
        self._loop = loop_factory()
        self._thread = threading.Thread(target=self._loop.run_forever, name="fixture-site")
        self._thread.start()
        self._runner = web.AppRunner(_build_app(site))
        self._call(self._runner.setup())
        self._call(web.TCPSite(self._runner, "127.0.0.1", 0).start())
        host, port = self._runner.addresses[0][:2]
        self.handle = ServerHandle(f"http://{host}:{port}")

    def _call[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def stop(self) -> None:
        self._call(self._runner.cleanup())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()
