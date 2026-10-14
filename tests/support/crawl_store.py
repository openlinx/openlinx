"""The crawl_store factory: crawl files a Crawl could leave behind (050-add-query-and-segments,
Test seams)."""

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Connection, select

from spider.aio import loop_factory
from spider.crawl.urls import NormalizedUrl
from spider.rules.model import Rule
from spider.rules.registry import RULES
from spider.store.crawls import record_state
from spider.store.issues import materialise_issues
from spider.store.records import FetchedUrl, NewUrl, RuleRow
from spider.store.schema import urls
from spider.store.urls import record_fetched, record_seed
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, default_rule_rows
from tests.support.rules import responded
from tests.support.workspace import TempWorkspace

SEED = NormalizedUrl("https://example.com/")
_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def crawl_store(
    temp_workspace: TempWorkspace,
    *,
    links: Sequence[str] = (),
    later_rules: Sequence[Rule] = (),
    completed: bool = False,
) -> Path:
    """A crawl file in the current Workspace whose Seed, SEED, links to `links`, each of which
    answered 200 as a URL that is no Page.

    `later_rules` are Rules of a later tool: the file records them after the catalogue's, and
    a `completed` Crawl's post-crawl pass stores their Issues too. Otherwise it is `running`.
    """
    crawl = create_any_crawl(
        temp_workspace, rules=(*default_rule_rows(), *map(_recorded, later_rules))
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
            for link in links
        )
        writer.run(record_fetched(_html(seed_id, found), {}))
        for url_id in writer.run(_ids_of(links)):
            writer.run(responded(200)(url_id))
        if completed:
            asyncio.run(
                materialise_issues(writer, (*RULES, *later_rules)), loop_factory=loop_factory
            )
            writer.run(record_state("completed", _AT))
    return crawl.path


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


def _html(url_id: int, discovered: tuple[NewUrl, ...]) -> FetchedUrl:
    return FetchedUrl(
        url_id=url_id,
        status_code=200,
        content_type="text/html",
        fetched_at=_AT,
        response_time_ms=1,
        parsed=True,
        discovered=discovered,
    )


def _ids_of(links: Sequence[str]) -> Callable[[Connection], list[int]]:
    def unit(connection: Connection) -> list[int]:
        return list(connection.execute(select(urls.c.id).where(urls.c.url.in_(links))).scalars())

    return unit
