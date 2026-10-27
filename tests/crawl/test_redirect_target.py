"""Where a response redirects to (022-add-fetch-policy D2; pure logic)."""

import pytest

from spider.crawl.following import redirect_target
from spider.crawl.urls import NormalizedUrl

_URL = NormalizedUrl("http://site.test/dir/page")

# A status, a Location header as received, and the target, None for no target.
_TARGETS = [
    (301, "/new", "http://site.test/new"),
    (302, "next", "http://site.test/dir/next"),
    (303, "//other.test/a", "http://other.test/a"),
    (307, "https://site.test/b", "https://site.test/b"),
    (308, "HTTP://SITE.TEST/c", "http://site.test/c"),
    (302, None, None),
    (300, "/choices", None),
    (304, "/cached", None),
    (305, "/proxy", None),
    (200, "/new", None),
    (301, "mailto:sales@site.test", None),
    (301, "ftp://site.test/file", None),
    (301, "http://[unclosed/", None),
    (301, "http://user:secret@site.test/", None),
]


@pytest.mark.parametrize(("status_code", "location", "target"), _TARGETS)
def test_a_location_that_is_no_http_url_has_no_target(
    status_code: int, location: str | None, target: str | None
) -> None:
    assert redirect_target(_URL, status_code, location, None) == target
