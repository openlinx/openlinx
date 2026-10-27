"""Cookie values are redacted before storage (022-add-fetch-policy D7, seam 4)."""

import pytest

from spider.crawl.fetch.cookies import redacted_header


def test_a_cookie_header_is_redacted_pair_by_pair() -> None:
    assert redacted_header("Cookie", "a=1; b=2") == "a=***; b=***"


@pytest.mark.parametrize(
    ("name", "value", "stored"),
    [
        # A value with no = before its first ; is all value: *** and its attributes.
        ("Set-Cookie", "abc123; Path=/; Secure", "***; Path=/; Secure"),
        ("set-cookie", "sid=abc123; Path=/", "sid=***; Path=/"),
        # The value runs from the first = to the first ;, an = inside it included.
        ("Set-Cookie", "prefs=lang=en; Max-Age=3600", "prefs=***; Max-Age=3600"),
        ("COOKIE", "session=x7f; theme=dark", "session=***; theme=***"),
        ("Cookie", "lang=en; 9f2c", "lang=***; ***"),
        ("Cookie", "lang=en;", "lang=***;"),
        ("X-Session", "sid=abc123", "sid=abc123"),
    ],
)
def test_each_cookie_value_is_redacted_and_the_rest_kept(
    name: str, value: str, stored: str
) -> None:
    assert redacted_header(name, value) == stored
