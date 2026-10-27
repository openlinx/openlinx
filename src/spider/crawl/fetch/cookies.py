"""Cookie values are never kept: they are redacted where the Fetcher decodes the headers
(022-add-fetch-policy D7)."""

REDACTED = "***"


def redacted_header(name: str, value: str) -> str:
    """The header's value with its cookie value replaced by `***`; any other header as is."""
    if name.lower() == "set-cookie":
        return _redacted_set_cookie(value)
    return value


def _redacted_set_cookie(value: str) -> str:
    # The cookie value is the text after the first = and before the first ;.
    cookie, separator, attributes = value.partition(";")
    cookie_name = cookie.partition("=")[0]
    return f"{cookie_name}={REDACTED}{separator}{attributes}"
