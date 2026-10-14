"""The robots.txt reader: Protego over the file's first 512,000 bytes (020-add-crawl-core D6)."""

from dataclasses import dataclass

from protego import Protego

# RFC 9309 2.5: a crawler parses at least the first 500 KiB of a robots.txt.
ROBOTS_TXT_LIMIT = 512_000
# SQLite's largest INTEGER: a Crawl-delay of any size still fits robots_crawl_delay_ms.
_LONGEST_DELAY_MS = 2**63 - 1


@dataclass(frozen=True, slots=True)
class RobotsTxt:
    """The rules of one origin's robots.txt, read for one robots user-agent token."""

    # As parsed: the first ROBOTS_TXT_LIMIT bytes, decoded.
    text: str
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


@dataclass(frozen=True, slots=True)
class OriginRobots:
    """What an origin's robots.txt says for the URLs of the origin."""

    # None: everything is allowed.
    rules: RobotsTxt | None

    def allows(self, url: str) -> bool:
        return self.rules is None or self.rules.allows(url)


def read_robots_txt(body: bytes, token: str) -> RobotsTxt:
    # utf-8-sig: a byte order mark would otherwise hide the first line's directive.
    text = body[:ROBOTS_TXT_LIMIT].decode("utf-8-sig", errors="replace")
    return RobotsTxt(text, Protego.parse(text), token)
