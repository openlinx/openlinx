"""A forward proxy for the proxy scenarios: it relays plain-http requests and records each one
(022-add-fetch-policy D9)."""

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

import aiohttp
import yarl
from aiohttp import web
from aiohttp.abc import AbstractResolver
from multidict import CIMultiDict

from spider.aio import loop_factory

# Headers of one connection, never relayed (RFC 9110 7.6.1), and the framing aiohttp sets itself.
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


class ForwardProxy:
    """Relays each request it receives in absolute form, resolving the fixture's names itself:
    behind a proxy, the crawler resolves only the proxy's address."""

    def __init__(self, resolver: AbstractResolver) -> None:
        self._resolver = resolver
        self._requests: list[str] = []
        self._lock = threading.Lock()
        self._loop = loop_factory()
        self._thread = threading.Thread(target=self._loop.run_forever, name="forward-proxy")
        self._thread.start()
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._relay)
        self._runner = web.AppRunner(app)
        try:
            self._call(self._runner.setup())
            self._call(web.TCPSite(self._runner, "127.0.0.1", 0).start())
        except BaseException:
            self._stop_loop()
            raise
        host, port = self._runner.addresses[0][:2]
        self.url = f"http://{host}:{port}"

    @property
    def requests(self) -> tuple[str, ...]:
        """The URL of each request relayed, in the order received."""
        with self._lock:
            return tuple(self._requests)

    async def _relay(self, request: web.Request) -> web.Response:
        # The request target as received: a proxy request names an absolute URL.
        target = yarl.URL(request.raw_path, encoded=True)
        if not target.absolute:
            return web.Response(status=400, text="A proxy request names an absolute URL.")
        with self._lock:
            self._requests.append(str(target))
        headers = CIMultiDict(
            (name, value)
            for name, value in request.headers.items()
            if name.lower() not in _NOT_RELAYED
        )
        async with (
            aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(resolver=self._resolver),
                auto_decompress=False,
                cookie_jar=aiohttp.DummyCookieJar(),
            ) as session,
            session.request(
                request.method,
                target,
                headers=headers,
                data=await request.read(),
                allow_redirects=False,
            ) as relayed,
        ):
            body = await relayed.read()
            kept = CIMultiDict(
                (name, value)
                for name, value in relayed.headers.items()
                if name.lower() not in _NOT_RELAYED
            )
            return web.Response(status=relayed.status, headers=kept, body=body)

    def _call[T](self, coroutine: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()

    def _stop_loop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._loop.close()

    def stop(self) -> None:
        try:
            self._call(self._runner.cleanup())
        finally:
            self._stop_loop()


StartProxy = Callable[[AbstractResolver], ForwardProxy]
