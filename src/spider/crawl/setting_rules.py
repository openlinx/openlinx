"""Rules that the CLI and the settings file share, one message each (020-add-crawl-core D11)."""

import math
import re

# RFC 9309 2.2.1: a product token.
_ROBOTS_USER_AGENT = re.compile(r"[a-zA-Z_-]+")
# RFC 9110 5.5: VCHAR, SP and HTAB. aiohttp would send any other character as UTF-8 bytes,
# which the RFC treats as obsolete and servers and log pipelines misread; CR or LF would end
# the header, or start another one.
_HEADER_VALUE = re.compile(r"[\t\x20-\x7e]+")


def as_rate(rate: float) -> float:
    if not (math.isfinite(rate) and rate > 0 and math.isfinite(1 / rate)):
        raise ValueError(
            "a rate is a finite number of requests per second above 0, whose interval 1/rate "
            "is finite"
        )
    return rate


def as_user_agent(user_agent: str) -> str:
    if not user_agent.strip() or _HEADER_VALUE.fullmatch(user_agent) is None:
        raise ValueError(
            "a user agent has visible ASCII characters, spaces and tabs only, and not only "
            "whitespace"
        )
    return user_agent


def as_robots_token(token: str) -> str:
    if _ROBOTS_USER_AGENT.fullmatch(token) is None:
        raise ValueError("a robots user-agent token has letters, '_' and '-' only (RFC 9309)")
    return token
