"""Read Pages through the Query Service from a real Crawl file."""

from dataclasses import replace

import pytest

from openlinx.crawl.urls import NormalizedUrl
from openlinx.services import query
from openlinx.store.pages import write_pages
from openlinx.store.records import FetchedUrl, Provenance
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, sha256_of
from tests.support.page_data import page_row
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize(
    ("where", "expected"),
    [
        ("title_1 contains 'КАТАЛОГ'", ["/a"]),
        ("title_1 contains 'STRASSE'", ["/c"]),
        ("STATUS_CODE CoNtAiNs '04' and title_1 contains 'товаров'", ["/a"]),
        ("title_1 contains ''", ["/a", "/b", "/c"]),
        ("title_1 contains '%_'", []),
    ],
)
def test_contains_ignores_case_in_any_script(
    temp_workspace: TempWorkspace, where: str, expected: list[str]
) -> None:
    root = "https://example.com"
    crawl = create_any_crawl(temp_workspace)
    # Record the column values directly because the Fetcher only extracts titles on 2xx.
    examples = (
        ("/a", "Каталог товаров", 404),
        ("/b", "\u041e компании", 200),
        ("/c", "Straße", 500),
        ("/d", None, 201),
    )
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        for path, title, status in examples:
            url = NormalizedUrl(root + path)
            url_id = writer.run(record_seed(url, is_internal=True, in_scope=True))
            row = replace(
                page_row("<p>Page</p>", url=url),
                url_id=url_id,
                title_1=title,
                status_code=status,
                crawl_timestamp=STARTED_AT,
            )
            writer.run(
                record_fetched(
                    FetchedUrl(
                        url_id=url_id,
                        provenance=Provenance(
                            crawl_depth=0, discovered_via="seed", found_on_url_id=None
                        ),
                        status_code=status,
                        content_type="text/html",
                        fetched_at=STARTED_AT,
                        response_time_ms=1,
                        parsed=200 <= status < 300,
                        attempt_count=1,
                        redirect=None,
                        rows=(HandlerRows(write_pages, (row,)),),
                    )
                )
            )
    request = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=crawl.path.stem
    )
    all_pages = query.pages(request, fields="address,title_1,status_code")
    assert all_pages.items == [
        {"address": root + "/a", "title_1": "Каталог товаров", "status_code": 404},
        {"address": root + "/b", "title_1": "\u041e компании", "status_code": 200},
        {"address": root + "/c", "title_1": "Straße", "status_code": 500},
        {"address": root + "/d", "title_1": None, "status_code": 201},
    ]

    result = query.pages(request, fields="address", where=where)

    assert (result.total, result.next_cursor) == (len(expected), None)
    assert result.items == [{"address": root + path} for path in expected]


def test_a_specific_crawl_is_selected(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    site = fixture_site(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nAllow: /\n"),
                "/three/": Page(body='<a href="a">A</a><a href="b">B</a>'),
                "/three/a": Page(body="<title>A</title>"),
                "/three/b": Page(body="<title>B</title>"),
                "/five/": Page(
                    body='<a href="a">A</a><a href="b">B</a><a href="c">C</a><a href="d">D</a>'
                ),
                "/five/a": Page(body="<title>A</title>"),
                "/five/b": Page(body="<title>B</title>"),
                "/five/c": Page(body="<title>C</title>"),
                "/five/d": Page(body="<title>D</title>"),
            }
        )
    )
    first = crawl_result(site.url("/three/"))
    second = crawl_result(site.url("/five/"))
    assert (first.summary.state, second.summary.state) == ("completed", "completed")
    first_before = sha256_of(first.crawl_file)
    second_before = sha256_of(second.crawl_file)

    request = query.QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    chosen = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=first.crawl_id
    )
    assert query.pages(request).total == 5
    assert query.pages(chosen).total == 3
    assert sha256_of(first.crawl_file) == first_before
    assert sha256_of(second.crawl_file) == second_before


def test_default_page_fields(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(Site({"/": Page(body="<title>Home</title><h1>Welcome</h1>")}))
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"
    request = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=crawl.crawl_id
    )

    result = query.pages(request)

    assert (result.total, result.next_cursor) == (1, None)
    assert result.items == [
        {
            "address": site.url("/"),
            "status_code": 200,
            "indexability": "indexable",
            "indexability_status": None,
            "title_1": "Home",
            "crawl_depth": 0,
        }
    ]
    assert list(result.items[0]) == [
        "address",
        "status_code",
        "indexability",
        "indexability_status",
        "title_1",
        "crawl_depth",
    ]


def test_selected_fields(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(Site({"/": Page(body="<title>Home</title><p>" + "word " * 812 + "</p>")}))
    crawl = crawl_result(site.url("/"))
    request = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=crawl.crawl_id
    )

    result = query.pages(request, fields="address,word_count")

    assert (result.total, result.next_cursor) == (1, None)
    assert result.items == [{"address": site.url("/"), "word_count": 812}]
    assert list(result.items[0]) == ["address", "word_count"]


def test_all_page_fields(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(Site({"/": Page(body="<title>Home</title><p>one two three</p>")}))
    crawl = crawl_result(site.url("/"))
    request = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=crawl.crawl_id
    )
    schema = run_cli("schema", "pages")
    assert schema.exit_code == 0, schema.stderr
    (table,) = schema.json()["items"]

    result = query.pages(request, fields="all")

    assert (result.total, result.next_cursor) == (1, None)
    (item,) = result.items
    assert list(item) == [column["name"] for column in table["columns"]]
    assert (item["address"], item["title_1"], item["word_count"], item["crawl_depth"]) == (
        site.url("/"),
        "Home",
        3,
        0,
    )
    assert item["meta_description_1"] is None


def test_default_order(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(
        Site(
            {
                "/c": Page(body='<a href="/a">A</a>'),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body="<title>B</title>"),
            }
        )
    )
    crawl = crawl_result(site.url("/c"))
    request = query.QueryRequest(
        cwd=temp_workspace.root, home=temp_workspace.home, crawl=crawl.crawl_id
    )

    result = query.pages(request)
    assert result.total == 3
    assert [item["address"] for item in result.items] == [
        site.url("/a"),
        site.url("/b"),
        site.url("/c"),
    ]

    first = query.pages(request, limit=1)
    assert first.next_cursor is not None
    second = query.pages(request, limit=2, cursor=first.next_cursor)
    count_only = query.pages(request, limit=0)

    assert [item["address"] for item in first.items] == [site.url("/a")]
    assert [item["address"] for item in second.items] == [site.url("/b"), site.url("/c")]
    assert (first.total, second.total, second.next_cursor) == (3, 3, None)
    assert (count_only.total, count_only.items, count_only.next_cursor) == (3, [], None)
