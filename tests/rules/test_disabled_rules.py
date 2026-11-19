"""Verify disabled Rules stay out of live and materialised Issues."""

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
from tests.fixture_site.routes import Page, Site
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


@pytest.mark.usefixtures("temp_workspace")
@pytest.mark.parametrize(
    "enabled",
    [pytest.param(True, id="enabled-control"), pytest.param(False, id="disabled")],
)
def test_disabled_rule_produces_no_issue(
    temp_workspace: TempWorkspace, fixture_site: StartSite, enabled: bool
) -> None:
    if not enabled:
        (temp_workspace.root / "openlinx.toml").write_text(
            "[rules.title-missing]\nenabled = false\n", encoding="utf-8"
        )

    server = fixture_site(
        Site(
            {
                "/rules/": Page(body='<a href="/rules/untitled">Untitled</a>'),
                "/rules/untitled": Page(body="<p>No title</p>"),
            }
        )
    )
    seed = server.url("/rules/")
    request = CrawlRequest(
        seed=seed,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=None,
        command_argv=["linx", "crawl", seed],
        flags={},
        secret_flags={},
    )
    plan = plan_crawl(request)
    reporter = Collected()
    live_reads: list[tuple[list[Issue], list[AffectedUrl]]] = []

    async def read_live_issues(context: PassContext) -> None:
        (event,) = (data for name, data in reporter.events if name == "crawl_started")
        crawl_file = Path(event["crawl_file"])
        assert query(
            crawl_file, "SELECT state, EXISTS(SELECT 1 FROM affected_urls) FROM crawl"
        ) == [("running", 0)]
        live_reads.append(
            (
                [
                    issue
                    for issue in read_issues(crawl_file, RULES)
                    if issue.rule_id == "title-missing"
                ],
                read_affected_urls(crawl_file, "title-missing", RULES),
            )
        )

    hooks = default_hooks(plan.loaded)
    hooks = replace(
        hooks,
        passes=(
            *hooks.passes[:-1],
            Pass("read-disabled-rule-live", read_live_issues),
            hooks.passes[-1],
        ),
    )
    result = start_crawl(plan, SystemClock(), reporter, hooks)
    crawl_file = result.crawl_file
    assert result.summary.state == "completed"

    [(stored_enabled,)] = query(crawl_file, "SELECT enabled FROM rules WHERE id = 'title-missing'")
    assert stored_enabled == int(enabled)
    ids_by_url = dict(query(crawl_file, "SELECT url, id FROM urls WHERE parsed = 1"))
    expected_affected = (
        [
            AffectedUrl(url_id=ids_by_url[url], detail=None)
            for url in (seed, server.url("/rules/untitled"))
        ]
        if enabled
        else []
    )
    expected_issue = (
        [
            Issue(
                rule_id="title-missing",
                category="titles",
                issue_type="issue",
                priority="high",
                affected_count=2,
            )
        ]
        if enabled
        else []
    )

    assert live_reads == [(expected_issue, expected_affected)]
    assert [
        issue for issue in read_issues(crawl_file, RULES) if issue.rule_id == "title-missing"
    ] == expected_issue
    assert read_affected_urls(crawl_file, "title-missing", RULES) == expected_affected
    assert query(
        crawl_file,
        "SELECT url_id, detail FROM affected_urls WHERE rule_id = 'title-missing' ORDER BY url_id",
    ) == [(item.url_id, None) for item in expected_affected]
    assert query(
        crawl_file,
        "SELECT rule_id, affected_count FROM issues WHERE rule_id = 'title-missing'",
    ) == ([("title-missing", 2)] if enabled else [])
