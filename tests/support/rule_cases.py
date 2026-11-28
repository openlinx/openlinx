"""Verify Page Rules through the live reader, the final pass and their saved SQL."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.rules.model import Threshold
from openlinx.rules.registry import RULES
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import read_affected_urls, read_issues
from openlinx.store.records import Issue, IssueType, Priority, RuleCategory
from tests.support.crawling import crawl_result
from tests.support.crawls import query

type PageDetails = Mapping[str, dict[str, str | int | None] | None]


@dataclass(frozen=True, slots=True, kw_only=True)
class PageRuleCase:
    """An expected Rule result keyed by complete Crawl URLs."""

    id: str
    issue_type: IssueType
    priority: Priority
    affected: PageDetails
    thresholds: tuple[Threshold, ...] = ()


def check_page_rule_cases(
    seed: str, category: RuleCategory, cases: Sequence[PageRuleCase], *, prepare: Pass | None = None
) -> None:
    """Crawl the fixture and assert the same literal results on both sides of the Issues pass."""
    ids = {case.id for case in cases}
    selected = [rule for rule in RULES if rule.id in ids]
    installed = [rule.id for rule in selected]
    expected_order = [case.id for case in cases]
    assert installed == expected_order, (installed, expected_order)

    reporter = Collected()
    observed: list[Path] = []
    expected_issues = [
        Issue(
            rule_id=case.id,
            category=category,
            issue_type=case.issue_type,
            priority=case.priority,
            affected_count=len(case.affected),
        )
        for case in cases
        if case.affected
    ]

    def check_results(file: Path) -> None:
        urls: dict[int, str] = dict(query(file, "SELECT id, url FROM urls"))
        issues = [issue for issue in read_issues(file, RULES) if issue.rule_id in ids]
        assert issues == expected_issues, (issues, expected_issues)
        for case in cases:
            affected = read_affected_urls(file, case.id, RULES)
            actual = sorted(
                ((urls[row.url_id], row.detail) for row in affected), key=lambda row: row[0]
            )
            expected = sorted(case.affected.items())
            assert actual == expected, (case.id, actual, expected)

    async def observe(context: PassContext) -> None:
        await context.writer.flush_async()
        (event,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(event["crawl_file"])
        assert query(file, "SELECT state, EXISTS(SELECT 1 FROM affected_urls) FROM crawl") == [
            ("running", 0)
        ]
        check_results(file)
        observed.append(file)

    defaults = default_hooks()
    passes: tuple[Pass, ...] = (Pass("observe-issues", observe), *defaults.passes)
    if prepare is not None:
        passes = (prepare, *passes)
    hooks = replace(defaults, passes=passes)
    result = crawl_result(seed, hooks, reporter=reporter)
    assert result.summary.state == "completed"
    file = result.crawl_file
    assert observed == [file]
    check_results(file)

    urls: dict[int, str] = dict(query(file, "SELECT id, url FROM urls"))
    for rule, case in zip(selected, cases, strict=True):
        assert rule.thresholds == case.thresholds
        [(kind, issue_type, priority, applies_to, enabled, thresholds, desc, why, fix, sql)] = (
            query(
                file,
                """SELECT category, issue_type, priority, applies_to, enabled, thresholds,
                      description, why_it_matters, how_to_fix, reproduce_sql
               FROM rules WHERE id = ?""",
                (case.id,),
            )
        )
        assert (kind, issue_type, priority, applies_to, enabled) == (
            category,
            case.issue_type,
            case.priority,
            "internal_pages",
            1,
        ), case.id
        assert json.loads(thresholds) == {
            threshold.name: threshold.default for threshold in case.thresholds
        }
        assert (desc, why, fix, sql) == (
            rule.description,
            rule.why_it_matters,
            rule.how_to_fix,
            rule.reproduce_sql,
        )
        assert all(value.strip() for value in (desc, why, fix, sql))
        actual = sorted(
            (
                (urls[url_id], None if detail is None else json.loads(detail))
                for url_id, detail in query(file, sql)
            ),
            key=lambda row: row[0],
        )
        expected = sorted(case.affected.items())
        assert actual == expected, (case.id, actual, expected)
