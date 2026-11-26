"""Check redirect-loop against the flags and edges stored by a real Crawl."""

from collections import Counter
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from openlinx.crawl.engine.hooks import Pass, PassContext
from openlinx.output.reporter import Collected
from openlinx.rules.registry import RULES
from openlinx.services.crawling import CrawlOverrides
from openlinx.services.hooks import default_hooks
from openlinx.store.connections import connect
from openlinx.store.issues import read_affected_urls, read_issues, read_url_issues
from openlinx.store.records import AffectedUrl, Issue, UrlIssue
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import query

_RULE_ID = "redirect-loop"


def _redirects(file: Path) -> list[tuple[str, int, int | None, str]]:
    return query(
        file,
        """SELECT source.url, source.status_code, source.in_redirect_loop, target.url
           FROM urls AS source JOIN urls AS target ON target.id = source.redirect_url_id
           ORDER BY source.url""",
    )


def _affected(file: Path) -> list[tuple[str, dict[str, int] | None]]:
    urls = dict(query(file, "SELECT id, url FROM urls"))
    return sorted(
        (urls[row.url_id], row.detail) for row in read_affected_urls(file, _RULE_ID, RULES)
    )


@pytest.mark.usefixtures("temp_workspace")
def test_loop(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/x">X</a>'),
                "/x": Redirect("/y", status=301),
                "/y": Redirect("/x", status=308),
            }
        )
    )
    x, y = server.url("/x"), server.url("/y")
    reporter = Collected()
    live_files: list[Path] = []

    async def observe_loop(_context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(started["crawl_file"])
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert _redirects(file) == [(x, 301, 1, y), (y, 308, 1, x)]
        assert query(file, "SELECT url_id FROM affected_urls WHERE rule_id = ?", (_RULE_ID,)) == []
        assert query(
            file,
            "SELECT category, issue_type, priority, applies_to, enabled, thresholds "
            "FROM rules WHERE id = ?",
            (_RULE_ID,),
        ) == [("response_codes", "issue", "high", "internal_urls", 1, "{}")]
        ids = dict(query(file, "SELECT url, id FROM urls"))
        x_id, y_id = ids[x], ids[y]
        assert read_affected_urls(file, _RULE_ID, RULES) == [
            AffectedUrl(url_id=x_id, detail={"hops": 2}),
            AffectedUrl(url_id=y_id, detail={"hops": 2}),
        ]
        assert [issue for issue in read_issues(file, RULES) if issue.rule_id == _RULE_ID] == [
            Issue(
                rule_id=_RULE_ID,
                category="response_codes",
                issue_type="issue",
                priority="high",
                affected_count=2,
            )
        ]
        for url_id in (x_id, y_id):
            assert [
                issue for issue in read_url_issues(file, url_id, RULES) if issue.rule_id == _RULE_ID
            ] == [UrlIssue(rule_id=_RULE_ID, url_id=url_id, detail={"hops": 2})]
        live_files.append(file)

    defaults = default_hooks()
    hooks = replace(defaults, passes=(Pass("observe-loop", observe_loop), *defaults.passes))
    result = crawl_result(server.url("/"), hooks, reporter=reporter)
    file = result.crawl_file
    assert live_files == [file]
    assert result.summary.state == "completed"
    assert _affected(file) == [(x, {"hops": 2}), (y, {"hops": 2})]

    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (_RULE_ID,))
    assert sorted(query(file, sql)) == query(
        file,
        "SELECT url_id, detail FROM affected_urls WHERE rule_id = ? ORDER BY url_id",
        (_RULE_ID,),
    )


@pytest.mark.usefixtures("temp_workspace")
def test_each_loop_has_its_own_size_and_excludes_incoming_redirects(
    fixture_site: StartSite,
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/tail">Tail</a><a href="/self-tail">Self tail</a>'),
                "/tail": Redirect("/entry"),
                "/entry": Redirect("/x"),
                "/x": Redirect("/y"),
                "/y": Redirect("/z"),
                "/z": Redirect("/x"),
                "/self-tail": Redirect("/self"),
                "/self": Redirect("/self"),
            }
        )
    )
    file = crawl_result(server.url("/")).crawl_file
    url = server.url
    assert _redirects(file) == [
        (url("/entry"), 301, 0, url("/x")),
        (url("/self"), 301, 1, url("/self")),
        (url("/self-tail"), 301, 0, url("/self")),
        (url("/tail"), 301, 0, url("/entry")),
        (url("/x"), 301, 1, url("/y")),
        (url("/y"), 301, 1, url("/z")),
        (url("/z"), 301, 1, url("/x")),
    ]
    assert _affected(file) == [
        (url("/self"), {"hops": 1}),
        (url("/x"), {"hops": 3}),
        (url("/y"), {"hops": 3}),
        (url("/z"), {"hops": 3}),
    ]


@pytest.mark.usefixtures("temp_workspace")
@pytest.mark.parametrize("resume", [False, True], ids=["fresh", "continue"])
def test_a_recorded_loop_can_exceed_the_http_hop_limit(
    fixture_site: StartSite, resume: bool
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<a href="/x">X</a><a href="/y">Y</a><a href="/z">Z</a>'
                    '<a href="/tail">Tail</a><a href="/old">Old</a>'
                ),
                "/x": Redirect("/y"),
                "/y": Redirect("/z"),
                "/z": Redirect("/x"),
                "/tail": Redirect("/x"),
                "/old": Redirect("/middle"),
                "/middle": Redirect("/unrequested"),
                "/unrequested": Redirect("/x"),
            }
        )
    )
    url = server.url
    x, y, z = url("/x"), url("/y"), url("/z")
    edges = [
        (url("/middle"), 301, 0, url("/unrequested")),
        (url("/old"), 301, 0, url("/middle")),
        (url("/tail"), 301, 0, x),
        (x, 301, 1, y),
        (y, 301, 1, z),
        (z, 301, 1, x),
    ]
    affected = [(x, {"hops": 3}), (y, {"hops": 3}), (z, {"hops": 3})]
    reporter = Collected()
    observed: list[Path] = []

    async def observe_loop(_context: PassContext) -> None:
        (started,) = (data for name, data in reporter.events if name == "crawl_started")
        file = Path(started["crawl_file"])
        assert query(file, "SELECT state FROM crawl") == [("running",)]
        assert query(file, "SELECT url_id FROM affected_urls WHERE rule_id = ?", (_RULE_ID,)) == []
        assert _redirects(file) == edges
        assert _affected(file) == affected
        assert [
            issue.affected_count for issue in read_issues(file, RULES) if issue.rule_id == _RULE_ID
        ] == [3]
        [(url_id,)] = query(file, "SELECT id FROM urls WHERE url = ?", (z,))
        assert [
            issue for issue in read_url_issues(file, url_id, RULES) if issue.rule_id == _RULE_ID
        ] == [UrlIssue(rule_id=_RULE_ID, url_id=url_id, detail={"hops": 3})]
        observed.append(file)

    defaults = default_hooks()
    hooks = replace(defaults, passes=(Pass("observe-long-loop", observe_loop), *defaults.passes))
    if resume:
        stopped = crawl_result(url("/"), max_redirects=1, max_urls=3, concurrency=1)
        assert stopped.summary.stop_reason == "max_urls"
        assert _redirects(stopped.crawl_file) == [(x, 301, 0, y), (y, 301, 0, z)]
        assert _affected(stopped.crawl_file) == []
        result = continued(stopped, CrawlOverrides(max_urls=None), hooks, reporter=reporter)
    else:
        result = crawl_result(url("/"), hooks, max_redirects=1, concurrency=1, reporter=reporter)

    file = result.crawl_file
    assert observed == [file]
    assert result.summary.state == "completed"
    assert _redirects(file) == edges
    assert _affected(file) == affected
    assert query(
        file,
        "SELECT url, fetch_state, skip_reason, in_redirect_loop FROM urls "
        "WHERE url IN (?, ?) ORDER BY url",
        (url("/"), url("/unrequested")),
    ) == [
        (url("/"), "fetched", None, None),
        (url("/unrequested"), "skipped", "max_redirects", None),
    ]
    assert Counter(
        request.path for request in server.requests if request.path != "/robots.txt"
    ) == {"/": 1, "/x": 1, "/y": 1, "/z": 1, "/tail": 1, "/old": 1, "/middle": 1}


@pytest.mark.usefixtures("temp_workspace")
def test_an_unmarked_cycle_does_not_fire(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/x">X</a><a href="/y">Y</a><a href="/z">Z</a>'),
                "/x": Redirect("/y"),
                "/y": Redirect("/z"),
                "/z": Redirect("/x"),
            }
        )
    )
    file = crawl_result(server.url("/"), max_redirects=1).crawl_file
    # A completed Store from an older Crawl can contain the edges without the flags.
    with closing(connect(file)) as connection, connection:
        connection.execute("UPDATE urls SET in_redirect_loop = 0 WHERE redirect_url_id IS NOT NULL")
        connection.execute("DELETE FROM affected_urls WHERE rule_id = ?", (_RULE_ID,))
    url = server.url
    assert _redirects(file) == [
        (url("/x"), 301, 0, url("/y")),
        (url("/y"), 301, 0, url("/z")),
        (url("/z"), 301, 0, url("/x")),
    ]
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (_RULE_ID,))
    assert query(file, sql) == []
    assert _affected(file) == []


@pytest.mark.usefixtures("temp_workspace")
def test_external_members_count_towards_size_with_only_internal_urls_affected(
    fixture_hosts: StartHosts,
) -> None:
    internal, external = "http://site.test/x", "http://other.test/y"
    hosts = fixture_hosts(
        Site({"/section/": Page(body='<a href="/x">X</a>'), "/x": Redirect(external)}),
        Site({"/y": Redirect(internal)}),
    )
    file = crawl_result(
        "http://site.test/section/", resolver=hosts.resolver, scope="subfolder"
    ).crawl_file
    assert query(
        file,
        """SELECT source.url, source.is_internal, source.in_scope, source.fetch_state,
                  source.in_redirect_loop, target.url
           FROM urls AS source JOIN urls AS target ON target.id = source.redirect_url_id
           ORDER BY source.url""",
    ) == [
        (external, 0, 0, "fetched", 1, internal),
        (internal, 1, 0, "fetched", 1, external),
    ]
    assert _affected(file) == [(internal, {"hops": 2})]
