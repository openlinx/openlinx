"""The synthetic site served from its own process, with a tally of its requests (026 D6)."""

import multiprocessing
import signal
import sys
from dataclasses import dataclass
from multiprocessing.connection import Connection
from types import TracebackType
from typing import Self

from tests.fixture_site.routes import Route, Site
from tests.fixture_site.server import RunningServer
from tests.fixture_site.synthetic.site import SyntheticSite, page_number

# A spawned child imports aiohttp and the site first, about a second on Windows.
START_TIMEOUT = 60
STOP = "stop"


@dataclass(frozen=True, kw_only=True)
class Tally:
    pages_requested: int
    pages_requested_more_than_once: int
    resource_requests: int
    not_found: int


class SiteProcess:
    """Use it as a context manager: it kills the process on the way out unless `stop` ran."""

    def __init__(self, site: SyntheticSite) -> None:
        spawn = multiprocessing.get_context("spawn")
        self._connection, child = spawn.Pipe()
        self._process = spawn.Process(target=_serve, args=(site, child), name="synthetic-site")
        self._process.start()
        child.close()
        if not self._connection.poll(START_TIMEOUT):
            self._process.kill()
            raise RuntimeError("The synthetic site's process did not start.")
        self.base_url: str = self._connection.recv()
        assert self._process.pid is not None
        self.pid: int = self._process.pid

    def stop(self) -> Tally:
        self._connection.send(STOP)
        tally: Tally = self._connection.recv()
        self._process.join()
        return tally

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._process.is_alive():
            self._process.kill()
            self._process.join()
        self._connection.close()


def _serve(site: SyntheticSite, connection: Connection) -> None:
    # Ctrl+C reaches every process of a console: the benchmark stops the site in order instead.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    # One byte per Page, saturating, so 500,000 Pages take 0.5 MB however long the run.
    per_page = bytearray(site.pages)
    others = {"resources": 0, "not_found": 0}

    def counted(path: str) -> Route | None:
        route = site.route(path)
        n = page_number(path, site.pages)
        if n is not None:
            per_page[n] = min(per_page[n] + 1, 255)
        else:
            others["resources" if route is not None else "not_found"] += 1
        return route

    server = RunningServer(Site(resolve=counted), keep_log=False)
    try:
        connection.send(server.handle.base_url)
        connection.recv()
    finally:
        server.stop()
    connection.send(
        Tally(
            pages_requested=site.pages - per_page.count(0),
            pages_requested_more_than_once=site.pages - per_page.count(0) - per_page.count(1),
            resource_requests=others["resources"],
            not_found=others["not_found"],
        )
    )
