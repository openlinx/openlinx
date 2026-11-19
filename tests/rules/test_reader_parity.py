"""Compare the two Issues reader paths over one completed fixture Crawl."""

from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.clock import SystemClock
from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.rules.registry import RULES
from openlinx.services.crawling import CrawlRequest, plan_crawl, start_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import read_affected_urls, read_issues
from openlinx.store.records import AffectedUrl, Issue
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace

# Discover z-not-found before a-gone so URL id order differs from URL text order.
_RULE_PAGES = Site(
    {
        "/rules/": Page(
            body='<a href="/rules/z-not-found">Not found</a><a href="/rules/titled">Tea</a>',
        ),
        "/rules/titled": Page(body='<title>Tea</title><a href="/rules/a-gone">Gone</a>'),
        "/rules/z-not-found": Status(404, body="Not found", content_type="text/plain"),
        "/rules/a-gone": Status(410, body="Gone", content_type="text/plain"),
    }
)

type _IssueRead = tuple[list[Issue], dict[str, list[AffectedUrl]]]


def _read_issues_and_affected_urls(crawl_file: Path) -> _IssueRead:
    return read_issues(crawl_file, RULES), {
        rule.id: read_affected_urls(crawl_file, rule.id, RULES) for rule in RULES
    }


def _crawl_rule_pages(seed: str) -> tuple[Path, _IssueRead]:
    plan = plan_crawl(
        CrawlRequest(
            seed=seed,
            cwd=Path.cwd(),
            home=Path.home(),
            workspace=None,
            command_argv=["linx", "crawl", seed],
            flags={},
            secret_flags={},
        )
    )
    reporter = Collected()
    observations: list[_IssueRead] = []

    async def observe_live_issues(_context: PassContext) -> None:
        (event,) = (data for name, data in reporter.events if name == "crawl_started")
        crawl_file = Path(event["crawl_file"])
        assert query(
            crawl_file, "SELECT state, EXISTS(SELECT 1 FROM affected_urls) FROM crawl"
        ) == [("running", 0)]
        observations.append(_read_issues_and_affected_urls(crawl_file))

    # Capture the committed Pages and link counts before the final Issues pass writes its results.
    hooks = default_hooks(plan.loaded)
    hooks = replace(
        hooks,
        passes=(
            *hooks.passes[:-1],
            Pass("observe-live-issues", observe_live_issues),
            hooks.passes[-1],
        ),
    )
    result = start_crawl(plan, SystemClock(), reporter, hooks)
    (live,) = observations
    return result.crawl_file, live


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_live_and_materialised_issues_agree(
    temp_workspace: TempWorkspace, fixture_site: StartSite, journal_mode: str
) -> None:
    (temp_workspace.root / "openlinx.toml").write_text(
        f'[store]\njournal_mode = "{journal_mode}"\n', encoding="utf-8"
    )
    server = fixture_site(_RULE_PAGES)
    crawl_file, (live_issues, live_affected) = _crawl_rule_pages(server.url("/rules/"))
    assert query(crawl_file, "SELECT state FROM crawl") == [("completed",)]
    assert query(crawl_file, "PRAGMA journal_mode") == [(journal_mode,)]
    stored_issues, stored_affected = _read_issues_and_affected_urls(crawl_file)
    assert stored_issues == live_issues
    assert stored_affected == live_affected

    not_found_url = server.url("/rules/z-not-found")
    gone_url = server.url("/rules/a-gone")
    errors = query(
        crawl_file,
        "SELECT url, id, status_code FROM urls WHERE url IN (?, ?) ORDER BY id",
        (not_found_url, gone_url),
    )
    assert [(url, code) for url, _, code in errors] == [(not_found_url, 404), (gone_url, 410)]
    (_, not_found, _), (_, gone, _) = errors
    [(missing,)] = query(crawl_file, "SELECT id FROM urls WHERE url = ?", (server.url("/rules/"),))
    rule_ids = {"internal-4xx", "title-missing", "title-too-long"}
    fixture_issues = [issue for issue in live_issues if issue.rule_id in rule_ids]
    assert fixture_issues == [
        Issue(
            rule_id="internal-4xx",
            category="response_codes",
            issue_type="issue",
            priority="high",
            affected_count=2,
        ),
        Issue(
            rule_id="title-missing",
            category="titles",
            issue_type="issue",
            priority="high",
            affected_count=1,
        ),
    ]
    assert live_affected["internal-4xx"] == [
        AffectedUrl(url_id=not_found, detail={"status_code": 404}),
        AffectedUrl(url_id=gone, detail={"status_code": 410}),
    ]
    assert live_affected["title-missing"] == [AffectedUrl(url_id=missing, detail=None)]
    assert live_affected["title-too-long"] == []
