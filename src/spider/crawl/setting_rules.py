"""Rules that the CLI and the settings file share, one message each (020-add-crawl-core D11)."""

import math
import re
import unicodedata

# RFC 9309 2.2.1: a product token.
_ROBOTS_USER_AGENT = re.compile(r"[a-zA-Z_-]+")


def as_rate(rate: float) -> float:
    if not (math.isfinite(rate) and rate > 0 and math.isfinite(1 / rate)):
        raise ValueError(
            "a rate is a finite number of requests per second above 0, whose interval 1/rate "
            "is finite"
        )
    return rate


def as_user_agent(user_agent: str) -> str:
    # A control character such as CR or LF would end the header, or start another one.
    if not user_agent or any(unicodedata.category(char) == "Cc" for char in user_agent):
        raise ValueError("a user agent is a non-empty header value without control characters")
    return user_agent


def as_robots_token(token: str) -> str:
    if _ROBOTS_USER_AGENT.fullmatch(token) is None:
        raise ValueError("a robots user-agent token has letters, '_' and '-' only (RFC 9309)")
    return token
