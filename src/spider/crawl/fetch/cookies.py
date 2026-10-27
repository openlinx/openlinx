"""Cookie values are never kept: they are redacted where the Fetcher decodes the headers
(022-add-fetch-policy D7)."""

REDACTED = "***"


def redacted_header(name: str, value: str) -> str:
    """The header's value with each cookie value replaced by `***`; any other header as is."""
    match name.lower():
        case "set-cookie":
            return _redacted_set_cookie(value)
        case "cookie":
            return ";".join(_redacted_pair(pair) for pair in value.split(";"))
    return value


def _redacted_set_cookie(value: str) -> str:
    # The cookie value is the text after the first = and before the first ;.
    cookie, separator, attributes = value.partition(";")
    return _redacted_pair(cookie) + separator + attributes


def _redacted_pair(pair: str) -> str:
    name, equals, _ = pair.partition("=")
    if equals:
        return f"{name}={REDACTED}"
    if not pair.strip():
        return pair
    # A pair without = is a value alone; the space that sets it apart from the last one stays.
    return pair[: len(pair) - len(pair.lstrip())] + REDACTED
