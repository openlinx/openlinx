"""Every Rule's Affected URLs are members of its population (040-add-rules D19; seam 2)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from spider.rules.model import Population, Rule
from spider.rules.registry import RULES
from spider.store.issues import read_affected_urls
from tests.support.crawls import query
from tests.support.rules import crawl_with_page, crawl_with_pages, crawl_with_url, failed, responded
from tests.support.workspace import TempWorkspace

MEMBERS: dict[Population, str] = {
    "internal_urls": "SELECT url_id FROM internal_urls",
    "analysed_pages": "SELECT url_id FROM analysed_pages",
    "indexable_pages": "SELECT url_id FROM indexable_pages",
}
# Rows outside every population. A Page that was not parsed holds NULL Page data, so only a
# Rule that read pages alone and took a NULL as missing would fire on it.
OUTSIDE: dict[str, Callable[[TempWorkspace], Path]] = {
    "external_4xx": lambda workspace: crawl_with_url(
        workspace, "https://elsewhere.test/gone", responded(404), is_internal=False
    )[0],
    "external_5xx": lambda workspace: crawl_with_url(
        workspace, "https://elsewhere.test/down", responded(503), is_internal=False
    )[0],
    "external_no_response": lambda workspace: crawl_with_url(
        workspace, "https://elsewhere.test/reset", failed("connection_refused"), is_internal=False
    )[0],
    "external_blocked": lambda workspace: crawl_with_url(
        workspace,
        "https://elsewhere.test/private",
        responded(200, blocked_by_robots_txt=True),
        is_internal=False,
    )[0],
    "external_http": lambda workspace: crawl_with_url(
        workspace, "http://elsewhere.test/a", responded(200), is_internal=False
    )[0],
    # A Page that was not parsed is recorded without its Page data: every column is NULL.
    "not_parsed": lambda workspace: crawl_with_page(workspace, parse_error="parse_timeout")[0],
    "not_parsed_twins": lambda workspace: crawl_with_pages(
        workspace, {}, {}, parse_error="parse_timeout"
    )[0],
}


@pytest.mark.parametrize("outside", OUTSIDE.values(), ids=OUTSIDE.keys())
@pytest.mark.parametrize("rule", RULES, ids=[rule.id for rule in RULES])
def test_a_rule_s_affected_urls_are_members_of_its_population(
    temp_workspace: TempWorkspace,
    rule: Rule,
    outside: Callable[[TempWorkspace], Path],
) -> None:
    crawl_file = outside(temp_workspace)
    members = {url_id for (url_id,) in query(crawl_file, MEMBERS[rule.population])}
    found = read_affected_urls(crawl_file, rule.id, RULES)

    assert {affected.url_id for affected in found} <= members
