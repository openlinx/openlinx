"""Compare the two Issues reader paths over one completed fixture Crawl."""

from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.clock import SystemClock
from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.rules.model import Rule
from openlinx.rules.registry import RULES
from openlinx.services.crawling import CrawlRequest, plan_crawl, start_crawl
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import (
    affected_urls_unit,
    materialise_issues,
    read_affected_urls,
    read_issues,
)
from openlinx.store.records import AffectedUrl, Issue, RuleRow
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawls import query

_RULE_PAGES = Site(
    {
        "/rules/": Page(body='<a href="/rules/z-titled">Pears</a>'),
        "/rules/z-titled": Page(
            body='<title>Pears</title><a href="/rules/a-titled">Tea</a>',
        ),
        "/rules/a-titled": Page(body="<title>Tea</title>"),
    }
)

# The fixture supplies a second Issue with measured detail while only title-missing can fire
# in the catalogue. Returning URLs in reverse ID order makes the reader's ordering observable.
_TITLE_LENGTH = Rule(
    id="fixture-title-length",
    category="titles",
    issue_type="opportunity",
    priority="low",
    applies_to="internal_pages",
    description="The length of a fixture Page title.",
    why_it_matters="The fixture needs a measured value for each Page.",
    how_to_fix="Edit the title of the fixture Page.",
    reproduce_sql="""\
SELECT url_id, json_object('length', length(title_1)) AS detail
FROM pages
WHERE title_1 IN ('Pears', 'Tea')
ORDER BY url_id DESC""",
)
_CATALOGUE = (*RULES, _TITLE_LENGTH)


type _IssueRead = tuple[list[Issue], dict[str, list[AffectedUrl]]]


def _read_issues_and_affected_urls(crawl_file: Path) -> _IssueRead:
    return read_issues(crawl_file, _CATALOGUE), {
        rule.id: read_affected_urls(crawl_file, rule.id, _CATALOGUE) for rule in _CATALOGUE
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
    rule = _TITLE_LENGTH
    snapshot = RuleRow(
        id=rule.id,
        category=rule.category,
        issue_type=rule.issue_type,
        priority=rule.priority,
        applies_to=rule.applies_to,
        enabled=True,
        thresholds={},
        description=rule.description,
        why_it_matters=rule.why_it_matters,
        how_to_fix=rule.how_to_fix,
        reproduce_sql=rule.reproduce_sql,
    )
    plan = replace(plan, new_crawl=replace(plan.new_crawl, rules=(*plan.new_crawl.rules, snapshot)))

    reporter = Collected()
    observations: list[_IssueRead] = []

    async def read_live_then_materialise_fixture_issue(context: PassContext) -> None:
        (event,) = (data for name, data in reporter.events if name == "crawl_started")
        crawl_file = Path(event["crawl_file"])
        assert query(
            crawl_file, "SELECT state, EXISTS(SELECT 1 FROM affected_urls) FROM crawl"
        ) == [("running", 0)]
        observations.append(_read_issues_and_affected_urls(crawl_file))
        await materialise_issues(context.writer, {rule.id: affected_urls_unit(rule)})

    # Capture the committed Pages and link counts before the final Issues pass writes its results.
    hooks = default_hooks(plan.loaded)
    hooks = replace(
        hooks,
        passes=(
            *hooks.passes[:-1],
            Pass("fixture-issues", read_live_then_materialise_fixture_issue),
            hooks.passes[-1],
        ),
    )
    result = start_crawl(plan, SystemClock(), reporter, hooks)
    (live,) = observations
    return result.crawl_file, live


@pytest.mark.usefixtures("temp_workspace")
def test_live_and_materialised_issues_agree(fixture_site: StartSite) -> None:
    server = fixture_site(_RULE_PAGES)
    crawl_file, (live_issues, live_affected) = _crawl_rule_pages(server.url("/rules/"))
    assert query(crawl_file, "SELECT state FROM crawl") == [("completed",)]
    stored_issues, stored_affected = _read_issues_and_affected_urls(crawl_file)
    assert stored_issues == live_issues
    assert stored_affected == live_affected

    ids = dict(query(crawl_file, "SELECT url, id FROM urls"))
    missing = ids[server.url("/rules/")]
    pears = ids[server.url("/rules/z-titled")]
    tea = ids[server.url("/rules/a-titled")]
    fixture_issues = [
        issue
        for issue in live_issues
        if issue.rule_id in {"title-missing", "title-too-long", "fixture-title-length"}
    ]
    assert fixture_issues == [
        Issue(
            rule_id="title-missing",
            category="titles",
            issue_type="issue",
            priority="high",
            affected_count=1,
        ),
        Issue(
            rule_id="fixture-title-length",
            category="titles",
            issue_type="opportunity",
            priority="low",
            affected_count=2,
        ),
    ]
    assert live_affected["title-missing"] == [AffectedUrl(url_id=missing, detail=None)]
    assert live_affected["title-too-long"] == []
    assert live_affected["fixture-title-length"] == [
        AffectedUrl(url_id=pears, detail={"length": 5}),
        AffectedUrl(url_id=tea, detail={"length": 3}),
    ]
