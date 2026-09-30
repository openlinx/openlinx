"""A file with mixed line endings, served byte for byte (design D9 of 000-scaffold-project)."""

from pathlib import Path

from tests.fixture_site.routes import Page, Site

SITE = Site(root=Path(__file__).parent, routes={"/mixed": Page(file="mixed-endings.txt")})
