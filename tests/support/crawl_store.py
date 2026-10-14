"""The crawl_store factory of 050-add-query-and-segments (design, Test seams)."""

import asyncio
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from sqlalchemy import Connection, select

from spider.aio import loop_factory
from spider.crawl.urls import NormalizedUrl
from spider.extract.addresses import display_address
from spider.rules.model import Rule
from spider.rules.registry import RULES
from spider.rules.settings import RulesSettings
from spider.rules.titles import TITLE_MISSING
from spider.services.rules import rule_rows
from spider.store.crawls import record_state
from spider.store.issues import materialise_issues
from spider.store.page_records import PageRow
from spider.store.pages import write_page
from spider.store.records import FetchedUrl, IssueType, NewUrl, Priority, RuleRow
from spider.store.schema import urls
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.rules import responded
from tests.support.workspace import TempWorkspace

SEED = NormalizedUrl("https://example.com/")
_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_PAGE_WRITER: Mapping[type, Callable[[Connection, Any], None]] = MappingProxyType(
    {PageRow: write_page}
)
# Queries of a later tool's Rules, each firing on the URLs under one folder.
UNDER_A = "SELECT id AS url_id, NULL AS detail FROM urls WHERE url LIKE 'https://example.com/a/%'"
UNDER_B = "SELECT id AS url_id, NULL AS detail FROM urls WHERE url LIKE 'https://example.com/b/%'"
UNDER_C = "SELECT id AS url_id, NULL AS detail FROM urls WHERE url LIKE 'https://example.com/c/%'"
UNDER_D = "SELECT id AS url_id, NULL AS detail FROM urls WHERE url LIKE 'https://example.com/d/%'"
# The Seed is an analysed Page on which no Rule of the catalogue fires.
_SEED_PAGE = MappingProxyType(
    {"title_count": 1, "title_1": "Home", "title_1_length": 4, "h1_count": 1, "h1_1": "Home"}
)


def crawl_store(
    temp_workspace: TempWorkspace,
    *,
    links: Sequence[str] = (),
    statuses: Mapping[str, int] = MappingProxyType({}),
    pages: Mapping[str, Mapping[str, Any]] = MappingProxyType({}),
    rules: Mapping[str, Mapping[str, Any]] = MappingProxyType({}),
    later_rules: Sequence[Rule] = (),
    completed: bool = False,
) -> Path:
    """A crawl file in the current Workspace whose Seed, SEED, an analysed Page, links to
    `links`, each of which answered 200 as a URL that is no Page, to `statuses`, URLs that
    are no Page by the status they answered with, and to `pages`, analysed Pages with these
    Page data columns.

    `rules` are the Workspace's [rules.<id>] settings the Crawl was created with, such as
    {"title-too-long": {"max_chars": 70}}. `later_rules` are Rules of a later tool: the file
    records them after the catalogue's, and a `completed` Crawl's post-crawl pass stores
    their Issues too. Otherwise the Crawl is `running`.
    """
    crawl = create_any_crawl(
        temp_workspace,
        rules=(
            *rule_rows(RulesSettings.model_validate(rules).model_dump(by_alias=True)),
            *map(_recorded, later_rules),
        ),
    )
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(SEED, is_internal=True, in_scope=True))
        found = tuple(
            NewUrl(
                url=NormalizedUrl(link),
                crawl_depth=1,
                discovered_via="hyperlink",
                is_internal=True,
                in_scope=True,
            )
            for link in (*links, *statuses, *pages)
        )
        writer.run(record_fetched(_html(seed_id, SEED, _SEED_PAGE, found), _PAGE_WRITER))
        for url_id, _ in writer.run(_urls_of(links)):
            writer.run(responded(200)(url_id))
        for url_id, url in writer.run(_urls_of(statuses)):
            writer.run(responded(statuses[url])(url_id))
        for url_id, url in writer.run(_urls_of(pages)):
            writer.run(record_fetched(_html(url_id, url, pages[url], ()), _PAGE_WRITER))
        if completed:
            asyncio.run(
                materialise_issues(writer, (*RULES, *later_rules)), loop_factory=loop_factory
            )
            writer.run(record_state("completed", _AT))
    return crawl.path


def later_rule(rule_id: str, issue_type: IssueType, priority: Priority, sql: str) -> Rule:
    """A Rule of a later tool, which the catalogue lacks, with any Issue Type and Priority,
    and texts of its own, which only the Crawl's rules table holds."""
    return replace(
        TITLE_MISSING,
        id=rule_id,
        issue_type=issue_type,
        priority=priority,
        applies_to="internal_urls",
        description=f"What {rule_id} checks.",
        why_it_matters=f"Why {rule_id} matters.",
        how_to_fix=f"How to fix {rule_id}.",
        reproduce_sql=sql,
    )


def under(folder: str, count: int) -> list[str]:
    return [f"https://example.com/{folder}/{n}" for n in range(count)]


def _recorded(rule: Rule) -> RuleRow:
    return RuleRow(
        id=rule.id,
        category=rule.category,
        issue_type=rule.issue_type,
        priority=rule.priority,
        applies_to=rule.applies_to,
        enabled=True,
        thresholds={threshold.name: threshold.default for threshold in rule.thresholds},
        description=rule.description,
        why_it_matters=rule.why_it_matters,
        how_to_fix=rule.how_to_fix,
        reproduce_sql=rule.reproduce_sql,
    )


def _html(
    url_id: int, url: str, page_data: Mapping[str, Any], discovered: tuple[NewUrl, ...]
) -> FetchedUrl:
    page = PageRow(
        url_id=url_id,
        address=display_address(NormalizedUrl(url)),
        url_encoded_address=url,
        **page_data,
    )
    return FetchedUrl(
        url_id=url_id,
        status_code=200,
        content_type="text/html",
        fetched_at=_AT,
        response_time_ms=1,
        parsed=True,
        discovered=discovered,
        rows=(page,),
    )


def _urls_of(urls_: Iterable[str]) -> Callable[[Connection], list[tuple[int, str]]]:
    def unit(connection: Connection) -> list[tuple[int, str]]:
        found = connection.execute(select(urls.c.id, urls.c.url).where(urls.c.url.in_(urls_)))
        return [(url_id, url) for url_id, url in found]

    return unit
