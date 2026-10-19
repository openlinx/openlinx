"""The URL of a meta refresh or a Refresh header, as HTML reads it (020-add-crawl-core D5)."""

_WHITESPACE = "\t\n\x0c\r "
_DIGITS = "0123456789"
_QUOTES = ("'", '"')


def refresh_url(content: str) -> str | None:
    """The reference of HTML's shared declarative refresh steps, or None when there is none."""
    rest = content.lstrip(_WHITESPACE)
    after_time = rest.lstrip(_DIGITS)
    if after_time == rest and not rest.startswith("."):
        return None
    rest = after_time.lstrip(_DIGITS + ".")
    if not rest or rest[0] not in ";," + _WHITESPACE:
        return None
    rest = rest.lstrip(_WHITESPACE)
    if rest[:1] in (";", ","):
        rest = rest[1:].lstrip(_WHITESPACE)
    # No URL refreshes the Page itself, which links to no other URL.
    return _url_string(rest) or None


def _url_string(rest: str) -> str:
    # HTML skips url, white space, = and an opening quote only when url= is all there; a start
    # that merely looks like it, such as uploads/x, is the URL itself, unquoted.
    if rest[:3].lower() == "url":
        after = rest[3:].lstrip(_WHITESPACE)
        if after[:1] != "=":
            return rest
        rest = after[1:].lstrip(_WHITESPACE)
    elif rest[:1].lower() == "u":
        return rest
    if rest[:1] in _QUOTES:
        return rest[1:].partition(rest[0])[0]
    return rest
