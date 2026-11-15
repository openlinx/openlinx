"""Share setting validation rules and messages between the CLI and settings file."""

import math
import re

# RFC 9309 2.2.1: a product token.
_ROBOTS_USER_AGENT = re.compile(r"[a-zA-Z_-]+")
# RFC 9110 5.5: VCHAR, SP and HTAB. aiohttp would send any other character as UTF-8 bytes,
# which the RFC treats as obsolete and servers and log pipelines misread; CR or LF would end
# the header, or start another one.
_HEADER_VALUE = re.compile(r"[\t\x20-\x7e]+")
_HEADER_NAME = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_ACCEPT_ENCODING_ITEM = re.compile(
    _HEADER_NAME.pattern + r"(?:[ \t]*;[ \t]*[qQ]=(?:0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?))?"
)


def as_rate(rate: float) -> float:
    if not (math.isfinite(rate) and rate > 0 and math.isfinite(1 / rate)):
        raise ValueError(
            "a rate is a finite number of requests per second above 0, whose interval 1/rate "
            "is finite"
        )
    return rate


def as_timeout(timeout: float) -> float:
    if not (math.isfinite(timeout) and timeout > 0):
        raise ValueError("a timeout is a finite number of seconds above 0")
    return timeout


def as_user_agent(user_agent: str) -> str:
    if not user_agent.strip() or _HEADER_VALUE.fullmatch(user_agent) is None:
        raise ValueError(
            "a user agent has visible ASCII characters, spaces and tabs only, and not only "
            "whitespace"
        )
    return user_agent


def as_auth(auth: str) -> str:
    if ":" not in auth or any(ord(char) < 32 or ord(char) == 127 for char in auth):
        raise ValueError("auth needs user:password without ASCII control characters")
    try:
        auth.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("auth must be encodable as UTF-8") from None
    return auth


def as_robots_token(token: str) -> str:
    if _ROBOTS_USER_AGENT.fullmatch(token) is None:
        raise ValueError("a robots user-agent token has letters, '_' and '-' only (RFC 9309)")
    return token


def as_header(header: str) -> tuple[str, str]:
    name, colon, value = header.partition(":")
    if not colon or _HEADER_NAME.fullmatch(name) is None:
        raise ValueError("a header needs a token name followed by ':' and a value")
    if value and _HEADER_VALUE.fullmatch(value) is None:
        raise ValueError("a header value has visible ASCII characters, spaces and tabs only")
    value = value.strip(" \t")
    if name.lower() == "user-agent":
        as_user_agent(value)
    if (
        name.lower() == "accept-encoding"
        and value
        and any(
            _ACCEPT_ENCODING_ITEM.fullmatch(item.strip(" \t")) is None for item in value.split(",")
        )
    ):
        raise ValueError("Accept-Encoding needs coding tokens with optional RFC 9110 qvalues")
    return name, value


def as_headers(headers: list[str]) -> tuple[tuple[str, str], ...]:
    parsed = tuple(as_header(header) for header in headers)
    if sum(name.lower() == "user-agent" for name, _ in parsed) > 1:
        raise ValueError("custom headers allow only one User-Agent entry")
    encodings = [value for name, value in parsed if name.lower() == "accept-encoding"]
    if len(encodings) > 1 and "" in encodings:
        raise ValueError("repeated Accept-Encoding entries must all have non-empty values")
    return parsed
