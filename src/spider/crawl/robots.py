"""The robots.txt reader: Protego over the file's first 512,000 bytes (020-add-crawl-core D6)."""

from dataclasses import dataclass

from protego import Protego

# RFC 9309 2.5: a crawler parses at least the first 500 KiB of a robots.txt.
ROBOTS_TXT_LIMIT = 512_000


@dataclass(frozen=True, slots=True)
class RobotsTxt:
    """The rules of one origin's robots.txt, read for one robots user-agent token."""

    _rules: Protego
    _token: str

    def allows(self, url: str) -> bool:
        return self._rules.can_fetch(url, self._token)


def read_robots_txt(body: bytes, token: str) -> RobotsTxt:
    # utf-8-sig: a byte order mark would otherwise hide the first line's directive.
    text = body[:ROBOTS_TXT_LIMIT].decode("utf-8-sig", errors="replace")
    return RobotsTxt(Protego.parse(text), token)
