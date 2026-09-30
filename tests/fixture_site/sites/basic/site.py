"""The basic site: one page at / (design D9 of 000-scaffold-project)."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(root=Path(__file__).parent, routes={"/": Page(file="index.html")})
