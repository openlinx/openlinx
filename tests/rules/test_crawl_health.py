"""The Health Score a Crawl stores on its crawl row (040-add-rules D8; seam 3+6)."""

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# A small shop on plain HTTP, whose sale Page lost its <title>.
SHOP = Site(
    {
        "/": Page(
            body='<title>Shoe shop</title><h1>Shoe shop</h1><a href="/shoes">Shoes</a> '
            '<a href="/boots">Boots</a> <a href="/sale">Sale</a>'
        ),
        "/shoes": Page(body="<title>Running shoes</title><h1>Running shoes</h1>"),
        "/boots": Page(body="<title>Trail boots</title><h1>Trail boots</h1>"),
        "/sale": Page(body="<h1>Sale</h1><p>Everything half price this week.</p>"),
    }
)


def test_end_to_end_score_on_the_fixture_site(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    crawl_file = crawled(fixture_site(SHOP).url("/"))

    assert query(
        crawl_file,
        "SELECT state, health_score, health_internal_page_count, health_affected_page_count, "
        "started_at <= health_calculated_at AND health_calculated_at <= completed_at FROM crawl",
    ) == [("completed", 75, 4, 1, 1)]


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
