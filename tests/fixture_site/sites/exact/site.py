"""Files whose exact bytes matter: mixed line endings, windows-1251 (design D9 of 000)."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(
    root=Path(__file__).parent,
    routes={
        "/mixed": Page(file="mixed-endings.txt"),
        "/cp1251": Page(file="cp1251.html", content_type="text/html; charset=windows-1251"),
    },
)
