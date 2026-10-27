"""A forward proxy for the proxy scenarios: it relays plain-http requests and records each one
(022-add-fetch-policy D9)."""

import threading
from collections.abc import Callable, Mapping

import aiohttp
import yarl
from aiohttp import web
from aiohttp.abc import AbstractResolver
from multidict import CIMultiDict

from tests.fixture_site.server import ThreadedApp

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


class ForwardProxy:
    """Relays each request it receives in absolute form, resolving the fixture's names itself:
    behind a proxy, the crawler resolves only the proxy's address."""

    def __init__(self, resolver: AbstractResolver) -> None:
        self._resolver = resolver
        self._requests: list[str] = []
        self._lock = threading.Lock()
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._relay)
        self._app = ThreadedApp(app, name="forward-proxy")
        self.url = self._app.base_url

    @property
    def requests(self) -> tuple[str, ...]:
        """The URL of each request relayed, in the order received."""
        with self._lock:
            return tuple(self._requests)

    def stop(self) -> None:
        self._app.stop()

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


StartProxy = Callable[[AbstractResolver], ForwardProxy]
