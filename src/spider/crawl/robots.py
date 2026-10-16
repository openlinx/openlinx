"""The robots.txt reader: Protego over the file's first 512,000 bytes (020-add-crawl-core D6)."""

from dataclasses import dataclass

from protego import Protego

from spider.store.records import FetchError, RobotsState

# RFC 9309 2.5: a crawler parses at least the first 500 KiB of a robots.txt.
ROBOTS_TXT_LIMIT = 512_000
# SQLite's largest INTEGER: a Crawl-delay of any size still fits robots_crawl_delay_ms.
_LONGEST_DELAY_MS = 2**63 - 1


@dataclass(frozen=True, slots=True)
class RobotsTxt:
    """The rules of one origin's robots.txt, read for one robots user-agent token; its text
    goes to the store, not into the run's memo of origins (design D6)."""

    _rules: Protego
    _token: str

    def allows(self, url: str) -> bool:
        return self._rules.can_fetch(url, self._token)

    @property
    def crawl_delay_ms(self) -> int | None:
        seconds = self._rules.crawl_delay(self._token)
        if seconds is None:
            return None
        # Protego gives a finite delay, which a thousand times may still overflow.
        milliseconds = seconds * 1000
        return _LONGEST_DELAY_MS if milliseconds >= _LONGEST_DELAY_MS else round(milliseconds)

    @property
    def sitemaps(self) -> tuple[str, ...]:
        return tuple(self._rules.sitemaps)


@dataclass(frozen=True, slots=True, kw_only=True)
class OriginRobots:
    """What an origin's robots.txt request gave, for the URLs of the origin."""

    state: RobotsState
    # The rules of an ok robots.txt; without them every URL is allowed.
    rules: RobotsTxt | None = None
    # Of the final robots.txt response; None without one.
    status_code: int | None = None
    # Why the robots.txt request got no HTTP response: every URL of the origin gets it.
    fetch_error: FetchError | None = None
    fetch_error_message: str | None = None

    def allows(self, url: str) -> bool:
        return self.rules is None or self.rules.allows(url)


def robots_state(status_code: int) -> RobotsState:
    """RFC 9309's mapping of the final robots.txt response."""
    if 200 <= status_code < 300:
        return "ok"
    if 300 <= status_code < 500 and status_code != 429:
        return "missing"
    # A server error or too many requests may hide rules, and a status no server should send
    # says it is broken: the origin is treated as disallowed.
    return "unreachable"


def robots_txt_text(body: bytes) -> str:
    """What is parsed: the first ROBOTS_TXT_LIMIT bytes, without a line that the limit cuts."""
    kept = body[:ROBOTS_TXT_LIMIT]
    if len(body) > ROBOTS_TXT_LIMIT and body[ROBOTS_TXT_LIMIT] not in b"\r\n":
        # A cut "Disallow: /private" would disallow every URL under the shorter prefix /priv.
        kept = kept[: max(kept.rfind(b"\n"), kept.rfind(b"\r")) + 1]
    # utf-8-sig: a byte order mark would otherwise hide the first line's directive.
    return kept.decode("utf-8-sig", errors="replace")


def read_robots_txt(text: str, token: str) -> RobotsTxt:
    return RobotsTxt(Protego.parse(text), token)
