"""Files whose exact bytes matter: mixed line endings, windows-1251 and a precompressed script
(design D9 of 000)."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(
    root=Path(__file__).parent,
    routes={
        "/mixed": Page(file="mixed-endings.txt"),
        "/cp1251": Page(file="cp1251.html", content_type="text/html; charset=windows-1251"),
        # A build step's precompressed script: 10,000 bytes as a 2,500-byte gzip body.
        "/app.js": Page(
            file="app.js.gz",
            content_type="text/javascript",
            headers=[("Content-Encoding", "gzip")],
        ),
    },
)
