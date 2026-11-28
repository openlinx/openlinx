"""Verify directive Rules over Pages in a real Crawl Store."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.crawl.urls import NormalizedUrl
from openlinx.rules.model import Rule
from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from openlinx.store.page_records import IndexabilityStatus, PageRow
from openlinx.store.pages import write_pages
from openlinx.store.records import AffectedUrl, FetchedUrl, Provenance
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.clock import FakeClock
from tests.support.crawling import crawled
from tests.support.crawls import STARTED_AT, create_any_crawl, query
from tests.support.page_data import page_row, unprepared_page_row
from tests.support.rule_results import assert_rule_results
from tests.support.workspace import TempWorkspace

_SEED = "https://example.com/"
_META_NOINDEX = '<meta name="robots" content="noindex">'
_HEADER_NOINDEX = (("X-Robots-Tag", "noindex"),)


def _record_page(
    workspace: TempWorkspace,
    page: PageRow,
    *,
    parsed: bool = True,
    blocked_by_robots_txt: bool = False,
) -> tuple[Path, int]:
    crawl = create_any_crawl(workspace)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        url_id = writer.run(record_seed(NormalizedUrl(_SEED), is_internal=True, in_scope=True))
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=url_id,
                    provenance=Provenance(
                        crawl_depth=0, discovered_via="seed", found_on_url_id=None
                    ),
                    status_code=page.status_code,
                    content_type=page.content_type,
                    fetched_at=STARTED_AT,
                    response_time_ms=page.response_time_ms,
                    parsed=parsed,
                    attempt_count=1,
                    redirect=None,
                    blocked_by_robots_txt=blocked_by_robots_txt,
                    rows=(
                        HandlerRows(
                            write_pages, (replace(page, url_id=url_id, crawl_timestamp=STARTED_AT),)
                        ),
                    ),
                )
            )
        )
    return crawl.path, url_id


def test_noindex_from_x_robots_tag_only(temp_workspace: TempWorkspace) -> None:
    page = page_row("<title>Header only</title>", headers=_HEADER_NOINDEX, url=_SEED)
    file, url_id = _record_page(temp_workspace, page)
    assert query(file, "SELECT meta_robots_noindex, x_robots_tag_noindex FROM pages") == [(0, 1)]

    rule = _noindex_rule()
    assert (rule.category, rule.issue_type, rule.priority, rule.applies_to, rule.thresholds) == (
        "directives",
        "warning",
        "high",
        "internal_pages",
        (),
    )
    assert evaluate_rule(file, rule) == [
        AffectedUrl(url_id=url_id, detail={"sources": ["x_robots_tag"]})
    ]


def test_noindex_from_both_sources(temp_workspace: TempWorkspace) -> None:
    page = page_row(_META_NOINDEX, headers=_HEADER_NOINDEX, url=_SEED)
    file, url_id = _record_page(temp_workspace, page)
    assert query(file, "SELECT meta_robots_noindex, x_robots_tag_noindex FROM pages") == [(1, 1)]

    rule = _noindex_rule()
    detail = {"sources": ["meta_robots", "x_robots_tag"]}
    assert evaluate_rule(file, rule) == [AffectedUrl(url_id=url_id, detail=detail)]

    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = 'noindex'")
    assert [(row_id, json.loads(raw)) for row_id, raw in query(file, sql)] == [(url_id, detail)]


@pytest.mark.parametrize(
    ("meta", "header", "blocked", "status", "sources"),
    [
        pytest.param(True, False, False, "noindex", ["meta_robots"], id="meta-only"),
        pytest.param(False, False, False, None, [], id="neither"),
        pytest.param(False, False, True, "blocked_by_robots_txt", [], id="robots-txt-only"),
        pytest.param(
            True, False, True, "blocked_by_robots_txt", ["meta_robots"], id="robots-txt-and-meta"
        ),
        pytest.param(None, True, False, "noindex", ["x_robots_tag"], id="meta-unmeasured"),
        pytest.param(True, None, False, "noindex", ["meta_robots"], id="header-unmeasured"),
        pytest.param(None, None, False, None, [], id="both-unmeasured"),
    ],
)
def test_noindex_reports_only_measured_directives(
    temp_workspace: TempWorkspace,
    meta: bool | None,
    header: bool | None,
    blocked: bool,
    status: IndexabilityStatus | None,
    sources: list[str],
) -> None:
    page = replace(
        page_row("<title>Example</title>", url=_SEED),
        meta_robots_noindex=meta,
        x_robots_tag_noindex=header,
        indexability="indexable" if status is None else "non_indexable",
        indexability_status=status,
    )
    file, url_id = _record_page(temp_workspace, page, blocked_by_robots_txt=blocked)
    assert query(
        file,
        "SELECT urls.parsed, urls.blocked_by_robots_txt, pages.meta_robots_noindex, "
        "pages.x_robots_tag_noindex, pages.indexability_status "
        "FROM pages JOIN urls ON urls.id = pages.url_id",
    ) == [(1, blocked, meta, header, status)]

    expected = [AffectedUrl(url_id=url_id, detail={"sources": sources})] if sources else []
    assert evaluate_rule(file, _noindex_rule()) == expected


def test_noindex_skips_unanalysed_pages(temp_workspace: TempWorkspace) -> None:
    page = unprepared_page_row(headers=_HEADER_NOINDEX, url=_SEED, status_code=404)
    file, _ = _record_page(temp_workspace, page, parsed=False)
    assert query(
        file,
        "SELECT urls.parsed, pages.x_robots_tag_noindex "
        "FROM pages JOIN urls ON urls.id = pages.url_id",
    ) == [(0, 1)]

    assert evaluate_rule(file, _noindex_rule()) == []


def _noindex_rule() -> Rule:
    matching = [rule for rule in RULES if rule.id == "noindex"]
    assert len(matching) == 1, "The catalogue must register noindex once"
    return matching[0]


@pytest.mark.usefixtures("temp_workspace")
def test_nofollow_from_meta_robots(fixture_site: StartSite) -> None:
    meta = '<meta name="robots" content="nofollow">'
    header = (("X-Robots-Tag", "nofollow"),)
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        '<a href="/both">Both</a><a href="/header">Header</a>'
                        '<a href="/meta">Meta</a><a href="/link">Link</a>'
                    )
                ),
                "/both": Page(body=meta, headers=header),
                "/header": Page(body="<title>Header only</title>", headers=header),
                "/meta": Page(body=meta),
                "/link": Page(body='<a href="/header" rel="nofollow">Link-level nofollow</a>'),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(
        file,
        "SELECT url, meta_robots_nofollow, x_robots_tag_nofollow "
        "FROM urls JOIN pages ON pages.url_id = urls.id ORDER BY url",
    ) == [
        (server.url("/"), 0, 0),
        (server.url("/both"), 1, 1),
        (server.url("/header"), 0, 1),
        (server.url("/link"), 0, 0),
        (server.url("/meta"), 1, 0),
    ]
    assert_rule_results(
        file,
        "nofollow",
        [
            (server.url("/both"), {"sources": ["meta_robots", "x_robots_tag"]}),
            (server.url("/header"), {"sources": ["x_robots_tag"]}),
            (server.url("/meta"), {"sources": ["meta_robots"]}),
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_meta_refresh_used(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=(
                        '<a href="/old">Old</a><a href="/reload">Reload</a>'
                        '<a href="/header">Header</a>'
                    )
                ),
                "/old": Page(body='<meta http-equiv="refresh" content="0; url=/new">'),
                "/reload": Page(body='<meta http-equiv="refresh" content="5">'),
                "/header": Page(
                    body="<title>Header</title>", headers=(("Refresh", "0; url=/new"),)
                ),
                "/new": Page(body="<title>New</title>"),
            }
        )
    )
    file = crawled(server.url("/"))

    assert query(
        file,
        "SELECT url, meta_refresh, redirect_url "
        "FROM urls JOIN pages ON pages.url_id = urls.id ORDER BY url",
    ) == [
        (server.url("/"), None, None),
        (server.url("/header"), None, server.url("/new")),
        (server.url("/new"), None, None),
        (server.url("/old"), "0; url=/new", server.url("/new")),
        (server.url("/reload"), "5", None),
    ]
    assert_rule_results(
        file,
        "meta-refresh",
        [
            (
                server.url("/old"),
                {"meta_refresh": "0; url=/new", "redirect_url": server.url("/new")},
            ),
            (server.url("/reload"), {"meta_refresh": "5", "redirect_url": None}),
        ],
    )
