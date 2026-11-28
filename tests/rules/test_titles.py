"""Verify title Rules over Pages written by a real Crawl."""

import pytest
from sqlalchemy import update

from openlinx.clock import SystemClock
from openlinx.rules.headings import H1_MISSING
from openlinx.rules.registry import RULES
from openlinx.rules.titles import TITLE_DUPLICATE, TITLE_MISSING, TITLE_TOO_LONG
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from openlinx.store.schema import pages
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


@pytest.mark.usefixtures("temp_workspace")
def test_missing_title_produces_an_affected_url(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/missing">Missing</a>'),
                "/missing": Page(body="<p>No title</p>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(missing_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/missing"),))

    assert evaluate_rule(file, TITLE_MISSING) == [AffectedUrl(url_id=missing_id, detail=None)]


@pytest.mark.usefixtures("temp_workspace")
def test_empty_title_counts_as_missing(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Present</title><a href="/empty">Empty title</a>'),
                "/empty": Page(body="<title></title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(empty_id, title_count, title_1)] = query(
        file, "SELECT url_id, title_count, title_1 FROM pages WHERE url_path = '/empty'"
    )
    assert (title_count, title_1) == (1, "")

    assert evaluate_rule(file, TITLE_MISSING) == [AffectedUrl(url_id=empty_id, detail=None)]


@pytest.mark.usefixtures("temp_workspace")
def test_non_analysed_pages_are_skipped_by_page_rules(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/not-found">Broken link</a>'),
                "/not-found": Status(404, body="<h1>Not found</h1>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(analysed_id,)] = query(
        file, "SELECT id FROM urls WHERE url = ? AND parsed = 1", (server.url("/"),)
    )
    [(unanalysed_id, status, parsed, title_count, title, h1_count, h1)] = query(
        file,
        "SELECT urls.id, urls.status_code, urls.parsed, pages.title_count, pages.title_1, "
        "pages.h1_count, pages.h1_1 "
        "FROM urls JOIN pages ON pages.url_id = urls.id WHERE urls.url = ?",
        (server.url("/not-found"),),
    )
    assert (status, parsed, title_count, title, h1_count, h1) == (404, 0, None, None, None, None)

    expected = [AffectedUrl(url_id=analysed_id, detail=None)]
    assert evaluate_rule(file, TITLE_MISSING) == expected
    assert evaluate_rule(file, H1_MISSING) == expected

    # Zero counts isolate the parsed population filter from the missing-element predicates.
    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(
            executing(
                update(pages)
                .where(pages.c.url_id == unanalysed_id)
                .values(title_count=0, h1_count=0)
            )
        )

    assert query(
        file,
        "SELECT urls.parsed, pages.title_count, pages.h1_count FROM urls "
        "JOIN pages ON pages.url_id = urls.id WHERE urls.id = ?",
        (unanalysed_id,),
    ) == [(0, 0, 0)]
    assert evaluate_rule(file, TITLE_MISSING) == expected
    assert evaluate_rule(file, H1_MISSING) == expected


@pytest.mark.usefixtures("temp_workspace")
def test_duplicate_titles_among_indexable_pages(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Home</title><a href="/boots">Boots</a>'
                    '<a href="/trainers">Trainers</a><a href="/sale">Sale</a>'
                    '<a href="/empty-a">Empty A</a><a href="/empty-b">Empty B</a>'
                ),
                "/boots": Page(body="<title>Shoes</title>"),
                "/trainers": Page(body="<title>Shoes</title>"),
                "/sale": Page(body="<title>shoes</title>"),
                "/empty-a": Page(body="<title></title>"),
                "/empty-b": Page(body="<title></title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    rows = query(
        file, "SELECT url_path, url_id, title_1, indexability FROM pages ORDER BY url_path"
    )
    assert [(path, title, indexability) for path, _, title, indexability in rows] == [
        ("/", "Home", "indexable"),
        ("/boots", "Shoes", "indexable"),
        ("/empty-a", "", "indexable"),
        ("/empty-b", "", "indexable"),
        ("/sale", "shoes", "indexable"),
        ("/trainers", "Shoes", "indexable"),
    ]
    paths = {url_id: path for path, url_id, _, _ in rows}
    rule = next((rule for rule in RULES if rule.id == "title-duplicate"), None)
    assert rule is not None, "title-duplicate is missing from the Rule catalogue"

    affected = [(paths[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=lambda item: item[0]) == [
        ("/boots", {"title_1": "Shoes", "pages": 2}),
        ("/trainers", {"title_1": "Shoes", "pages": 2}),
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_non_indexable_pages_are_not_compared(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Home</title><a href="/boots">Boots</a>'
                    '<a href="/trainers">Trainers</a>'
                ),
                "/boots": Page(body="<title>Shoes</title>"),
                "/trainers": Page(
                    body='<title>Shoes</title><meta name="robots" content="noindex">'
                ),
            }
        )
    )
    file = crawled(server.url("/"))
    assert query(
        file,
        "SELECT pages.url_path, pages.indexability, pages.indexability_status "
        "FROM pages JOIN urls ON urls.id = pages.url_id "
        "WHERE urls.parsed = 1 AND pages.title_1 = 'Shoes' ORDER BY pages.url_path",
    ) == [("/boots", "indexable", None), ("/trainers", "non_indexable", "noindex")]

    assert evaluate_rule(file, TITLE_DUPLICATE) == []


@pytest.mark.usefixtures("temp_workspace")
def test_title_too_long_by_characters(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<title>Home</title><a href="/long">Long title</a>'),
                "/long": Page(body="<title>" + "я" * 61 + "</title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(url_id, length, width)] = query(
        file,
        "SELECT url_id, title_1_length, title_1_width_px FROM pages WHERE address = ?",
        (server.url("/long"),),
    )
    assert (length, width) == (61, None)
    assert evaluate_rule(file, TITLE_TOO_LONG) == [
        AffectedUrl(url_id=url_id, detail={"length": 61})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_title_at_the_limit(fixture_site: StartSite) -> None:
    server = fixture_site(Site({"/": Page(body="<title>" + "a" * 60 + "</title>")}))
    file = crawled(server.url("/"))
    assert query(file, "SELECT title_1_length FROM pages") == [(60,)]
    assert evaluate_rule(file, TITLE_TOO_LONG) == []


def test_raised_title_limit(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    settings.write_text("[rules.title-too-long]\nmax_chars = 70\n", encoding="utf-8")
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body="<title>" + "a" * 65 + '</title><a href="/at-limit">At the limit</a>'
                    '<a href="/long">Long title</a>'
                ),
                "/at-limit": Page(body="<title>" + "a" * 70 + "</title>"),
                "/long": Page(body="<title>" + "b" * 71 + "</title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    [(long_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (server.url("/long"),))
    assert query(file, "SELECT url_path, title_1_length FROM pages ORDER BY url_path") == [
        ("/", 65),
        ("/at-limit", 70),
        ("/long", 71),
    ]
    settings.write_text("[rules.title-too-long]\nmax_chars = 85\n", encoding="utf-8")
    assert evaluate_rule(file, TITLE_TOO_LONG) == [
        AffectedUrl(url_id=long_id, detail={"length": 71})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_long_title_requires_an_analysed_page(fixture_site: StartSite) -> None:
    title = "a" * 61
    server = fixture_site(
        Site(
            {
                "/": Page(body=f'<title>{title}</title><a href="/not-found">Broken link</a>'),
                "/not-found": Status(404, body=f"<title>{title}</title>"),
            }
        )
    )
    file = crawled(server.url("/"))
    analysed = server.url("/")
    unanalysed = server.url("/not-found")
    ids = dict(query(file, "SELECT url, id FROM urls WHERE url IN (?, ?)", (analysed, unanalysed)))

    # An unanalysed Page normally has NULL title fields. Set them to values that
    # satisfy the length predicate so only the parsed filter can exclude it.
    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(
            executing(
                update(pages)
                .where(pages.c.url_id == ids[unanalysed])
                .values(title_count=1, title_1=title, title_1_length=61)
            )
        )

    assert query(
        file,
        "SELECT urls.parsed, pages.title_1_length FROM urls "
        "JOIN pages ON pages.url_id = urls.id WHERE urls.id = ?",
        (ids[unanalysed],),
    ) == [(0, 61)]
    assert evaluate_rule(file, TITLE_TOO_LONG) == [
        AffectedUrl(url_id=ids[analysed], detail={"length": 61})
    ]
