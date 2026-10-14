"""The synthetic site in its own process, with a tally (design D6 of 026-add-parse-pool)."""

import multiprocessing
import signal
import sys
from dataclasses import dataclass
from multiprocessing.connection import Connection
from types import TracebackType
from typing import Self

from tests.fixture_site.hosts import FixtureResolver
from tests.fixture_site.routes import Route, Site, Status
from tests.fixture_site.server import RequestLog, RunningServer, ServerHandle
from tests.fixture_site.synthetic.site import EXTERNAL_HOSTS, SyntheticSite, page_number

# A spawned child imports aiohttp and the site first, about a second on Windows.
START_TIMEOUT = 60
# Its server cancels the handlers still running, so a stop takes seconds at most.
STOP_TIMEOUT = 60
STOP = "stop"


@dataclass(frozen=True, kw_only=True)
class Tally:
    pages_requested: int
    pages_requested_more_than_once: int
    # Every request but a Page's or a 404: Resources, External and not-followed URLs.
    other_requests: int
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

    def resolver(self) -> FixtureResolver:
        """The DNS resolver hook that sends each External host of the site to this process."""
        handle = ServerHandle(self.base_url, RequestLog(keep=False))
        return FixtureResolver(dict.fromkeys(EXTERNAL_HOSTS, handle))

    def stop(self) -> Tally:
        self._connection.send(STOP)
        if not self._connection.poll(STOP_TIMEOUT):
            self._process.kill()
            raise RuntimeError("The synthetic site's process did not stop.")
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
    others = {"other": 0, "not_found": 0}

    def counted(path: str) -> Route:
        route = site.route(path)
        n = page_number(path, site.pages)
        if n is not None:
            per_page[n] = min(per_page[n] + 1, 255)
        else:
            others["not_found" if isinstance(route, Status) and route.code == 404 else "other"] += 1
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
            other_requests=others["other"],
            not_found=others["not_found"],
        )
    )
