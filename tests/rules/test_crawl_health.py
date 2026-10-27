"""The Health Score a Crawl stores on its crawl row (040-add-rules D8; seam 3+6)."""

from datetime import UTC, datetime

from sqlalchemy import select

from spider.rules.registry import RULES
from spider.store.health import health
from spider.store.issues import health_affected_in
from spider.store.reading import reading
from spider.store.records import Health
from spider.store.schema import urls
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
# A small shop on plain HTTP, whose sale Page lost its <title> and whose size guide PDF is gone:
# its 404 is an Internal URL with an Issue, not a Page.
SHOP = Site(
    {
        "/": Page(
            body='<title>Shoe shop</title><h1>Shoe shop</h1><a href="/shoes">Shoes</a> '
            '<a href="/boots">Boots</a> <a href="/sale">Sale</a>'
        ),
        "/shoes": Page(
            body="<title>Running shoes</title><h1>Running shoes</h1>"
            '<a href="/shoes/size-guide.pdf">Size guide</a>'
        ),
        "/shoes/size-guide.pdf": Status(404, body="Not found", content_type="text/plain"),
        "/boots": Page(body="<title>Trail boots</title><h1>Trail boots</h1>"),
        "/sale": Page(body="<h1>Sale</h1><p>Everything half price this week.</p>"),
    }
)


def test_end_to_end_score_on_the_fixture_site(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawl_result(fixture_site(SHOP).url("/"), clock=FakeClock(start=AT)).crawl_file

    assert query(
        crawl_file,
        "SELECT state, health_score, health_internal_page_count, health_affected_page_count, "
        "health_calculated_at FROM crawl",
    ) == [("completed", 75, 4, 1, "2026-01-02T03:04:05.000Z")]


def test_health_score_of_a_segment_of_urls(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(SHOP)
    crawl_file = crawled(server.url("/"))
    # The URLs under /shoes: the Page and the size guide's 404, which is no Page to rate.
    segment = select(urls.c.id.label("url_id")).where(urls.c.url.startswith(server.url("/shoes")))

    with reading(crawl_file) as connection:
        found = health(connection, segment, health_affected_in(connection, RULES))

    assert found == Health(score=100, internal_pages=1, affected_pages=0)


def test_no_pages_means_no_score(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nDisallow: /\n"),
                "/": Page(body="<title>Home</title>"),
            }
        )
    )

    assert query(
        crawled(server.url("/")),
        "SELECT state, health_score, health_internal_page_count, health_affected_page_count "
        "FROM crawl",
    ) == [("completed", None, 0, 0)]


def test_health_fields_are_derived() -> None:
    columns = run_cli("schema", "crawl").json()["items"][0]["columns"]

    assert [
        (column["name"], column["nullable"], column["description"].startswith("Derived: "))
        for column in columns
        if column["name"].startswith("health_")
    ] == [
        ("health_score", True, True),
        ("health_internal_page_count", True, True),
        ("health_affected_page_count", True, True),
        ("health_calculated_at", True, True),
    ]
