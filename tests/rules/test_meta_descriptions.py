"""Verify meta description Rules over Pages in a real crawl store."""

import pytest
from sqlalchemy import Connection, case, update

from openlinx.clock import SystemClock
from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.rules.meta_descriptions import META_DESCRIPTION_TOO_LONG
from openlinx.rules.model import Threshold
from openlinx.rules.registry import RULES
from openlinx.store.issues import evaluate_rule
from openlinx.store.records import AffectedUrl
from openlinx.store.schema import pages
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawled
from tests.support.crawls import query
from tests.support.rule_cases import PageRuleCase, check_page_rule_cases
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


@pytest.mark.usefixtures("temp_workspace")
def test_missing_meta_description(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/empty">Empty</a><a href="/present">Present</a>'),
                "/empty": Page(
                    body='<meta name="description" content="">'
                    '<meta name="description" content="Second description">'
                    '<meta name="robots" content="noindex">'
                ),
                "/present": Page(body='<meta name="description" content="Buy shoes">'),
            }
        )
    )
    file = crawled(server.url("/"))
    rows = query(
        file,
        "SELECT url_path, url_id, meta_description_count, meta_description_1, "
        "meta_description_2, indexability_status FROM pages ORDER BY url_path",
    )
    measurements = [
        (path, count, first, second, status) for path, _, count, first, second, status in rows
    ]
    assert measurements == [
        ("/", 0, None, None, None),
        ("/empty", 2, "", "Second description", "noindex"),
        ("/present", 1, "Buy shoes", None, None),
    ]
    paths = {url_id: path for path, url_id, *_ in rows}
    matching = [rule for rule in RULES if rule.id == "meta-description-missing"]
    assert len(matching) == 1, "The catalogue must register meta-description-missing once"
    [rule] = matching
    assert (rule.category, rule.issue_type, rule.priority, rule.applies_to, rule.thresholds) == (
        "meta_descriptions",
        "opportunity",
        "medium",
        "internal_pages",
        (),
    )

    affected = [(paths[item.url_id], item.detail) for item in evaluate_rule(file, rule)]
    assert sorted(affected, key=lambda item: item[0]) == [("/", None), ("/empty", None)]


def _description(content: str) -> str:
    return f'<meta name="description" content="{content}">'


@pytest.mark.usefixtures("temp_workspace")
def test_duplicate_meta_descriptions(fixture_site: StartSite) -> None:
    shared = _description("Buy shoes online")
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body=shared + '<a href="/duplicate">Duplicate</a><a href="/third">Third</a>'
                    '<a href="/case">Case</a><a href="/noindex">Non-Indexable</a>'
                ),
                "/duplicate": Page(body=shared),
                "/third": Page(body=shared),
                "/case": Page(body=_description("Buy Shoes online")),
                "/noindex": Page(body=shared + '<meta name="robots" content="noindex">'),
            }
        )
    )
    check_page_rule_cases(
        server.url("/"),
        "meta_descriptions",
        [
            PageRuleCase(
                id="meta-description-duplicate",
                issue_type="opportunity",
                priority="low",
                affected={
                    server.url(path): {"meta_description_1": "Buy shoes online", "pages": 3}
                    for path in ("/", "/duplicate", "/third")
                },
            )
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_meta_description_too_long(fixture_site: StartSite) -> None:
    other_pages = {
        "/over-chars": Page(body=_description("a" * 156)),
        "/over-pixels": Page(body=_description("W" * 154)),
        "/null-width-long": Page(body=_description("i" * 156)),
        "/null-width-at-limit": Page(body=_description("i" * 155)),
    }
    links = "".join(f'<a href="{path}">{path}</a>' for path in other_pages)
    server = fixture_site(Site({"/": Page(body=links), **other_pages}))

    async def record_pixel_widths(context: PassContext) -> None:
        # Pin the stored inputs of the Rule independently of the 030 width calculator.
        widths = {"/over-chars": 900, "/over-pixels": 986}
        await context.writer.run_async(
            executing(
                update(pages).values(
                    meta_description_1_width_px=case(widths, value=pages.c.url_path)
                )
            )
        )

    check_page_rule_cases(
        server.url("/"),
        "meta_descriptions",
        [
            PageRuleCase(
                id="meta-description-too-long",
                issue_type="opportunity",
                priority="low",
                thresholds=(
                    Threshold("max_chars", 155, "characters"),
                    Threshold("max_pixels", 985, "pixels"),
                ),
                affected={
                    server.url("/over-chars"): {"length": 156, "width_px": 900},
                    server.url("/over-pixels"): {"length": 154, "width_px": 986},
                    server.url("/null-width-long"): {"length": 156, "width_px": None},
                },
            )
        ],
        prepare=Pass("record-description-widths", record_pixel_widths),
    )


@pytest.mark.usefixtures("temp_workspace")
def test_meta_description_at_both_limits(fixture_site: StartSite) -> None:
    server = fixture_site(Site({"/both-limits": Page(body=_description("b" * 155))}))

    def set_width(connection: Connection) -> tuple[str, int, int]:
        length, width = pages.c.meta_description_1_length, pages.c.meta_description_1_width_px
        path, chars, pixels = connection.execute(
            update(pages)
            .values(meta_description_1_width_px=985)
            .returning(pages.c.url_path, length, width)
        ).one()
        return path, chars, pixels

    async def record_pixel_width(context: PassContext) -> None:
        assert await context.writer.run_async(set_width) == ("/both-limits", 155, 985)

    check_page_rule_cases(
        server.url("/both-limits"),
        "meta_descriptions",
        [
            PageRuleCase(
                id="meta-description-too-long",
                issue_type="opportunity",
                priority="low",
                thresholds=(
                    Threshold("max_chars", 155, "characters"),
                    Threshold("max_pixels", 985, "pixels"),
                ),
                affected={},
            )
        ],
        prepare=Pass("record-description-width", record_pixel_width),
    )


@pytest.mark.usefixtures("temp_workspace")
def test_meta_description_too_short(fixture_site: StartSite) -> None:
    shared = _description("Buy shoes online")
    other_pages = {
        "/duplicate": Page(body=shared),
        "/third": Page(body=shared),
        "/case": Page(body=_description("Buy Shoes online")),
        "/noindex": Page(body=shared + '<meta name="robots" content="noindex">'),
        "/multiple": Page(body=_description("") + _description("Second description")),
        "/empty": Page(body=_description("")),
        "/missing": Page(body="<p>No meta description</p>"),
        "/short": Page(body=_description("a" * 69)),
        "/at-min": Page(body=_description("a" * 70)),
    }
    links = "".join(f'<a href="{path}">{path}</a>' for path in other_pages)
    server = fixture_site(Site({"/": Page(body=shared + links), **other_pages}))
    check_page_rule_cases(
        server.url("/"),
        "meta_descriptions",
        [
            PageRuleCase(
                id="meta-description-too-short",
                issue_type="opportunity",
                priority="low",
                thresholds=(Threshold("min_chars", 70, "characters"),),
                affected={
                    server.url("/"): {"length": 16},
                    server.url("/duplicate"): {"length": 16},
                    server.url("/third"): {"length": 16},
                    server.url("/case"): {"length": 16},
                    server.url("/noindex"): {"length": 16},
                    server.url("/short"): {"length": 69},
                },
            )
        ],
    )


@pytest.mark.usefixtures("temp_workspace")
def test_multiple_meta_descriptions_raise_an_issue(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body=_description("One") + '<a href="/multiple">Multiple</a>'),
                "/multiple": Page(body=_description("") + _description("Second description")),
            }
        )
    )
    check_page_rule_cases(
        server.url("/"),
        "meta_descriptions",
        [
            PageRuleCase(
                id="meta-description-multiple",
                issue_type="warning",
                priority="low",
                affected={server.url("/multiple"): {"count": 2}},
            )
        ],
    )


def test_meta_description_length_limits_use_recorded_overrides(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    settings.write_text(
        "[rules.meta-description-too-long]\nmax_chars = 160\nmax_pixels = 1000\n",
        encoding="utf-8",
    )
    server = fixture_site(
        Site(
            {
                "/": Page(body=_description("a" * 156) + '<a href="/wide">Wide</a>'),
                "/wide": Page(body=_description("W" * 155)),
            }
        )
    )
    file = crawled(server.url("/"))
    widths = {"/": 986, "/wide": 1001}
    with CrawlWriter(file, SystemClock()) as writer:
        writer.run(
            executing(
                update(pages).values(
                    meta_description_1_width_px=case(widths, value=pages.c.url_path)
                )
            )
        )
    settings.write_text(
        "[rules.meta-description-too-long]\nmax_chars = 1\nmax_pixels = 9999\n",
        encoding="utf-8",
    )
    [(wide_id,)] = query(file, "SELECT url_id FROM pages WHERE url_path = '/wide'")

    assert evaluate_rule(file, META_DESCRIPTION_TOO_LONG) == [
        AffectedUrl(url_id=wide_id, detail={"length": 155, "width_px": 1001}),
    ]
