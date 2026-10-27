"""The network pause: Internal requests in a row without an HTTP response (020-add-crawl-core
D16)."""

from spider.crawl.engine.stop import StopSignal
from spider.store.records import FetchError

# tls_error is not among them: a certificate failure is an answer of sorts, and a site-wide one
# must not wait --network-wait and then fail as site_unreachable.
NO_RESPONSE: frozenset[FetchError] = frozenset(
    {
        "dns_error",
        "connection_refused",
        "connection_error",
        "invalid_response",
        "watchdog",
        "timeout",
    }
)


def pause_after(concurrency: int) -> int:
    return max(8, 2 * concurrency)


class NetworkPause:
    """Kept by the engine from each Internal URL's outcome, since only it knows which URLs are
    Internal and every code that counts, a robots.txt one included."""

    def __init__(self, concurrency: int, network_wait: int, stop: StopSignal) -> None:
        self._limit = pause_after(concurrency)
        self._network_wait = network_wait
        self._stop = stop
        self._in_a_row = 0

    def responded(self) -> None:
        self._in_a_row = 0

    def failed(self, fetch_error: FetchError) -> None:
        if fetch_error not in NO_RESPONSE:
            return
        self._in_a_row += 1
        if self._in_a_row >= self._limit and self._network_wait == 0:
            self._stop.set("site_unreachable")
