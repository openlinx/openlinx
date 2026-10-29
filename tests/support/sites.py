"""Fixture sites that several test modules crawl, named after the spec's examples."""

from tests.fixture_site.routes import Page, Site

# The URL limit scenarios' site: / links to /p1 to /p9.
NINE_PAGES = Site(
    routes={
        "/": Page(body="".join(f'<a href="/p{n}">P{n}</a>' for n in range(1, 10))),
        **{f"/p{n}": Page(body=f"<p>P{n}</p>") for n in range(1, 10)},
    }
)

# /c is three deep through /a and /b, and two deep through the check /late.html, which ends
# after a frontier under --max-depth 2 has skipped /c at depth 3: long against a local request.
LATE_SHORTER_PATH = Site(
    routes={
        "/": Page(body='<img src="/late.html"><a href="/a">A</a>'),
        "/late.html": Page(body='<a href="/c">C</a>', delay=1.0),
        "/a": Page(body='<a href="/b">B</a>'),
        "/b": Page(body='<a href="/c">C</a>'),
        "/c": Page(body="<p>C</p>"),
    }
)
