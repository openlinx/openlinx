"""Exercise Where diagnostics against the schema of a new HTTP Crawl."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select

from openlinx.output.diagnostics import OpenLinxError
from openlinx.query.where import parse
from openlinx.store.query_where import compile_where
from openlinx.store.reading import reading_selected
from openlinx.store.records import CrawlFile
from openlinx.store.schema import pages
from openlinx.store.selection import resolve_crawl
from openlinx.workspace.discovery import resolve_workspace
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.fixture_site.server import ServerHandle
from tests.support.crawling import crawl_result
from tests.support.crawls import sha256_of
from tests.support.workspace import TempWorkspace


@pytest.fixture
def where_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> Iterator[tuple[CrawlFile, ServerHandle]]:
    site = fixture_site(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nAllow: /\n"),
                "/": Page(body='<title>Home</title><a href="/gone">Gone</a>'),
                "/gone": Status(404, body="<html><title>Gone</title></html>"),
            }
        )
    )
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"
    cwd = temp_workspace.root
    workspace = resolve_workspace(cwd=cwd, flag=None, home=temp_workspace.home)
    selected = resolve_crawl(crawl.crawl_id, workspace=workspace, cwd=cwd)
    before = sha256_of(selected.path)

    yield selected, site

    assert sha256_of(selected.path) == before
    assert sorted((request.method, request.path) for request in site.requests) == [
        ("GET", "/"),
        ("GET", "/gone"),
        ("GET", "/robots.txt"),
    ]


def _matching_addresses(crawl: CrawlFile, expression: str) -> list[str]:
    predicate = compile_where(parse(expression), pages)
    statement = select(pages.c.address).where(predicate).order_by(pages.c.address)
    with reading_selected(crawl) as connection:
        return list(connection.execute(statement).scalars())


def test_unknown_column_in_a_conjunction(
    where_crawl: tuple[CrawlFile, ServerHandle],
) -> None:
    crawl, site = where_crawl
    assert _matching_addresses(crawl, "STATUS_CODE = 404") == [site.url("/gone")]

    with pytest.raises(OpenLinxError) as caught:
        _matching_addresses(crawl, "status_code = 200 and XYZZY = 200")

    assert (caught.value.code, caught.value.exit_code) == ("unknown_column", 2)
    diagnostic = caught.value.diagnostic
    assert diagnostic.level == "error"
    assert "XYZZY" in diagnostic.message
    assert diagnostic.hint is not None
    assert "linx schema" in diagnostic.hint
    assert diagnostic.details.get("suggestions") == []


@pytest.mark.parametrize(
    ("expression", "in_range"),
    [
        ("status_code < 9223372036854775808", "status_code < 9223372036854775807"),
        ("status_code > -9223372036854775809", "status_code > -9223372036854775808"),
    ],
)
def test_integer_outside_sqlite_range_in_where(
    where_crawl: tuple[CrawlFile, ServerHandle], expression: str, in_range: str
) -> None:
    crawl, site = where_crawl
    assert _matching_addresses(crawl, in_range) == [site.url("/"), site.url("/gone")]

    with pytest.raises(OpenLinxError) as caught:
        _matching_addresses(crawl, expression)

    assert (caught.value.code, caught.value.exit_code) == ("invalid_where", 2)
    diagnostic = caught.value.diagnostic
    assert diagnostic.level == "error"
    assert "status_code" in diagnostic.message
    assert "outside the SQLite INTEGER range" in diagnostic.message
    assert diagnostic.hint == "Use an integer from -9223372036854775808 to 9223372036854775807."


def test_large_real_literal_in_where(where_crawl: tuple[CrawlFile, ServerHandle]) -> None:
    crawl, site = where_crawl

    assert _matching_addresses(crawl, "status_code < 100000000000000000000.0") == [
        site.url("/"),
        site.url("/gone"),
    ]
