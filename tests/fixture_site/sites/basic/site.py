"""Serve a basic fixture site with one Page at the root path."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(root=Path(__file__).parent, routes={"/": Page(file="index.html")})
