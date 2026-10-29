"""Fixture sites that several test modules crawl, named after the spec's examples."""

from tests.fixture_site.routes import Page, Site

# The URL limit scenarios' site: / links to /p1 to /p9.
NINE_PAGES = Site(
    routes={
        "/": Page(body="".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 10))),
        **{f"/p{n}": Page(body=f"<p>P{n}</p>") for n in range(1, 10)},
    }
)
