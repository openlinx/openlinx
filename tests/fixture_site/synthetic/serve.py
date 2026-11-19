"""Serve the synthetic site separately so its work stays out of Crawl measurements."""

import multiprocessing
import signal
import sys
from dataclasses import dataclass
from multiprocessing.connection import Connection
from types import TracebackType
from typing import Self

from tests.fixture_site.routes import Answer, Site, Status
from tests.fixture_site.server import RunningServer
from tests.fixture_site.synthetic.site import SyntheticSite, page_number

# The child imports aiohttp at startup and cancels in-flight handlers on shutdown.
PROCESS_TIMEOUT = 60
STOP = "stop"


@dataclass(frozen=True, kw_only=True)
class Tally:
    pages_requested: int
    pages_requested_more_than_once: int
    other_requests: int
    not_found: int


class SiteProcess:
    """Use as a context manager. Call stop to collect counts after the server ends."""

    def __init__(self, site: SyntheticSite) -> None:
        spawn = multiprocessing.get_context("spawn")
        self._connection, child = spawn.Pipe()
        self._process = spawn.Process(target=_serve, args=(site, child), name="synthetic-site")
        try:
            self._process.start()
        except BaseException:
            self._connection.close()
            self._process.close()
            raise
        finally:
            child.close()
        try:
            if not self._connection.poll(PROCESS_TIMEOUT):
                raise RuntimeError("The synthetic site's process did not start.")
            self.base_url: str = self._connection.recv()
        except BaseException:
            self._close()
            raise
        assert self._process.pid is not None
        self.pid = self._process.pid

    def stop(self) -> Tally:
        self._connection.send(STOP)
        if not self._connection.poll(PROCESS_TIMEOUT):
            raise RuntimeError("The synthetic site's process did not return its tally.")
        tally: Tally = self._connection.recv()
        self._process.join(PROCESS_TIMEOUT)
        if self._process.exitcode != 0:
            raise RuntimeError("The synthetic site's process did not exit cleanly.")
        return tally

    def _close(self) -> None:
        if self._process.is_alive():
            self._process.kill()
            self._process.join()
        self._process.close()
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._close()


def _serve(site: SyntheticSite, connection: Connection) -> None:
    # A console interrupt reaches every process. The parent stops the site in order.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    # One byte per Page, saturating, so repeated requests never grow the tally.
    per_page = bytearray(site.pages)
    other = not_found = 0

    def counted(path: str) -> Answer:
        nonlocal other, not_found
        route = site.route(path)
        n = page_number(path, site.pages)
        if n is not None:
            per_page[n] = min(per_page[n] + 1, 255)
        elif isinstance(route, Status) and route.code == 404:
            not_found += 1
        else:
            other += 1
        return route

    with connection:
        server = RunningServer(Site(resolve=counted), keep_log=False)
        try:
            connection.send(server.handle.base_url)
            connection.recv()
        except EOFError:
            return
        finally:
            server.stop()
        visited = site.pages - per_page.count(0)
        connection.send(
            Tally(
                pages_requested=visited,
                pages_requested_more_than_once=visited - per_page.count(1),
                other_requests=other,
                not_found=not_found,
            )
        )
