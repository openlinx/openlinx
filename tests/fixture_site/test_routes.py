"""Sites are checked when they are declared (design D9 of 000-scaffold-project)."""

import pytest

from tests.fixture_site.routes import Page, Site


@pytest.mark.parametrize(("file", "body"), [(None, None), ("index.html", "home")])
def test_a_page_takes_exactly_one_of_file_and_body(file: str | None, body: str | None) -> None:
    with pytest.raises(ValueError, match="exactly one of file= and body="):
        Page(file=file, body=body)


def test_a_site_with_file_pages_needs_a_root() -> None:
    with pytest.raises(ValueError, match="root"):
        Site(routes={"/": Page(file="index.html")})
