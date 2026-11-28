"""Build running or completed Crawls through Store units for the Query Service."""

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from openlinx.crawl.urls import NormalizedUrl
from openlinx.rules.model import Rule
from openlinx.rules.registry import RULES
from openlinx.store.crawls import record_state
from openlinx.store.issues import affected_urls_unit
from openlinx.store.links import write_links
from openlinx.store.page_records import PageRow
from openlinx.store.pages import write_pages
from openlinx.store.records import (
    FetchedUrl,
    IssueType,
    JournalSetting,
    NewUrl,
    Priority,
    Provenance,
    RuleRow,
)
from openlinx.store.rows import HandlerRows
from openlinx.store.urls import queued_batch, record_fetched, record_seed
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, create_any_crawl
from tests.support.page_data import page_link_rows, page_row
from tests.support.workspace import TempWorkspace

type IssueExample = tuple[str, IssueType, Priority, int]

_ORDERED_ISSUES: tuple[IssueExample, ...] = (
    ("rule-a", "warning", "high", 50),
    ("rule-b", "issue", "low", 3),
    ("rule-c", "issue", "high", 1),
    ("rule-d", "issue", "high", 9),
    ("rule-e", "issue", "high", 9),
    ("rule-f", "issue", "medium", 10),
    ("rule-g", "opportunity", "high", 1),
)


def _rules(examples: tuple[IssueExample, ...]) -> tuple[tuple[Rule, ...], tuple[RuleRow, ...]]:
    matching_urls = text("SELECT id AS url_id, NULL AS detail FROM urls WHERE url LIKE :pattern")
    rules = tuple(
        Rule(
            id=rule_id,
            category="response_codes",
            issue_type=issue_type,
            priority=priority,
            applies_to="internal_urls",
            description=f"Fixture Rule {rule_id}.",
            why_it_matters="The test records an Issue for this Rule.",
            how_to_fix="Use the literal Issue order.",
            reproduce_sql=str(
                matching_urls.bindparams(pattern=f"https://example.com/{rule_id}/%").compile(
                    compile_kwargs={"literal_binds": True}
                )
            ),
        )
        for rule_id, issue_type, priority, _ in examples
    )
    snapshots = tuple(
        RuleRow(
            id=rule.id,
            category=rule.category,
            issue_type=rule.issue_type,
            priority=rule.priority,
            applies_to=rule.applies_to,
            enabled=True,
            thresholds={},
            description=f"Recorded guidance for {rule.id}.",
            why_it_matters=rule.why_it_matters,
            how_to_fix=rule.how_to_fix,
            reproduce_sql=rule.reproduce_sql,
        )
        for rule in rules
    )
    return rules, snapshots


def crawl_store(
    temp_workspace: TempWorkspace,
    *,
    pages: Mapping[str, str] | None = None,
    journal_setting: JournalSetting = "wal",
    completed: bool = True,
    example_issues: tuple[IssueExample, ...] = _ORDERED_ISSUES,
) -> Path:
    """Record linked HTML Pages with the installed Rules, completing the Crawl by default.

    Without explicit Pages, record non-HTML 404s for the example Issues of later Rules.
    """
    responses: Mapping[str, str | None]
    if pages is None:
        rules, snapshots = _rules(example_issues)
        crawl_file = create_any_crawl(
            temp_workspace, rules=snapshots, journal_setting=journal_setting
        )
        responses = {
            f"https://example.com/{rule_id}/{index}": None
            for rule_id, _, _, count in example_issues
            for index in range(count)
        }
    else:
        rules = RULES
        crawl_file = create_any_crawl(temp_workspace, journal_setting=journal_setting)
        responses = pages

    root = NormalizedUrl("https://example.com/")
    body = (
        '<title>Home</title><meta name="description" content="Home"><h1>Home</h1><h2>Pages</h2>'
    ) + "".join(
        f'<a href="/{url.removeprefix("https://example.com/")}">Page</a>' for url in responses
    )

    with CrawlWriter(crawl_file.path, FakeClock()) as writer:
        seed_id = writer.run(record_seed(root, is_internal=True, in_scope=True))
        links = tuple(
            NewUrl(
                url=NormalizedUrl(url),
                discovered_via="hyperlink",
                is_internal=True,
                in_scope=True,
            )
            for url in responses
        )
        seed_at = STARTED_AT + timedelta(seconds=1)
        writer.run(
            record_fetched(
                FetchedUrl(
                    url_id=seed_id,
                    provenance=Provenance(
                        crawl_depth=0, discovered_via="seed", found_on_url_id=None
                    ),
                    status_code=200,
                    content_type="text/html",
                    fetched_at=seed_at,
                    response_time_ms=10,
                    parsed=True,
                    attempt_count=1,
                    redirect=None,
                    discovered=links,
                    rows=(
                        _page_rows(body, root, seed_id, seed_at),
                        HandlerRows(write_links, page_link_rows(body, url=str(root))),
                    ),
                )
            )
        )
        queued = writer.run(queued_batch(1, 0, len(responses), 10))
        assert len(queued) == len(responses)
        for index, url in enumerate(queued):
            html = responses[url.url]
            fetched_at = STARTED_AT + timedelta(seconds=index + 2)
            writer.run(
                record_fetched(
                    FetchedUrl(
                        url_id=url.id,
                        provenance=Provenance(
                            crawl_depth=url.crawl_depth,
                            discovered_via=url.discovered_via,
                            found_on_url_id=url.found_on_url_id,
                        ),
                        status_code=404 if html is None else 200,
                        content_type="text/plain" if html is None else "text/html",
                        fetched_at=fetched_at,
                        response_time_ms=10,
                        parsed=html is not None,
                        attempt_count=1,
                        redirect=None,
                        rows=(
                            () if html is None else (_page_rows(html, url.url, url.id, fetched_at),)
                        ),
                    )
                )
            )
        if completed:
            for rule in rules:
                writer.run(affected_urls_unit(rule))
            writer.run(record_state("completed", STARTED_AT + timedelta(seconds=len(queued) + 2)))
    return crawl_file.path


def _page_rows(html: str, url: NormalizedUrl, url_id: int, at: datetime) -> HandlerRows[PageRow]:
    # The extractor test helper supplies a stand-alone URL id and clock.
    row = replace(
        page_row(html, content_type="text/html", url=url),
        url_id=url_id,
        crawl_timestamp=at,
        response_time_ms=10,
    )
    return HandlerRows(write_pages, (row,))
