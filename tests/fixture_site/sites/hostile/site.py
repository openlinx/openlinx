"""Hostile pages: bytes that their declared charset cannot decode (020-add-crawl-core D16)."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(
    root=Path(__file__).parent,
    routes={
        "/": Page(body='<a href="/bad-bytes">Bad bytes</a>'),
        "/bad-bytes": Page(file="bad-bytes.html", content_type="text/html; charset=utf-8"),
        "/after": Page(body="<p>After</p>"),
    },
)
