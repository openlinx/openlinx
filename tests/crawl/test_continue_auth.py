"""Require fresh Basic Auth before a continued Crawl opens writable resources."""

import json
from contextlib import nullcontext

import pytest

from openlinx.crawl.engine.hooks import Hooks, UrlResult, handler
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawling import CrawlOverrides
from openlinx.store.page_records import PageRow
from openlinx.store.pages import write_pages
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import continued, crawl_result
from tests.support.crawls import crawl_row, sha256_of
from tests.support.permissions import read_only_file
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("custom_user_agent", [False, True], ids=["dedicated-ua", "custom-ua"])
@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
def test_continue_refuses_a_recorded_password_without_a_fresh_value(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    custom_user_agent: bool,
    read_only: bool,
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(
        server.url("/"),
        auth="alice:s3cret",
        header=["User-Agent: Header/1"],
        user_agent=None if custom_user_agent else "Dedicated/1",
        max_urls=1,
        retries=0,
    )
    config = json.loads(crawl_row(stopped.crawl_file)["config"])
    assert stopped.summary.state == "stopped"
    assert config["crawl"]["auth"] == "***"
    assert config["request_policy"] == {"custom_user_agent": custom_user_agent}
    before = sha256_of(stopped.crawl_file)
    requests = server.requests
    files = {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()}
    reporter = Collected()

    with (
        read_only_file(stopped.crawl_file) if read_only else nullcontext(),
        pytest.raises(OpenLinxError) as caught,
    ):
        continued(stopped, CrawlOverrides(max_urls=None), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)
    assert caught.value.diagnostic.hint is not None
    assert "--auth" in caught.value.diagnostic.hint
    diagnostic = json.dumps(caught.value.diagnostic.to_json())
    assert all(secret not in diagnostic for secret in ("alice:s3cret", "s3cret", "***"))
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert {file.name: file.read_bytes() for file in stopped.crawl_file.parent.iterdir()} == files
    assert server.requests == requests


def test_fresh_auth_is_used_masked_and_required_again_on_continue(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/next">Next</a>'),
                "/next": Page(body='<a href="/last">Last</a>'),
            }
        )
    )
    stopped = crawl_result(
        server.url("/"),
        auth="alice:old123",
        header=["X-Env: staging", "X-Env: audit"],
        timeout=7,
        max_urls=1,
        concurrency=1,
        retries=0,
    )
    requests_before = len(server.requests)

    result = continued(stopped, CrawlOverrides(max_urls=2, auth="test:123£"))

    assert result.summary.state == "stopped"
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in server.requests[requests_before:]
    ] == [("/robots.txt", ["Basic dGVzdDoxMjPCow=="]), ("/next", ["Basic dGVzdDoxMjPCow=="])]
    config = json.loads(crawl_row(result.crawl_file)["config"])
    assert config["crawl"]["auth"] == "***"
    assert config["crawl"]["header"] == ["X-Env: staging", "X-Env: audit"]
    assert config["crawl"]["timeout"] == 7
    assert b"test:123" not in result.crawl_file.read_bytes()
    with pytest.raises(OpenLinxError) as caught:
        continued(result, CrawlOverrides(max_urls=None))
    assert (caught.value.code, caught.value.exit_code) == ("secrets_required", 2)


@pytest.mark.parametrize("auth", [None, ""], ids=["unset", "empty"])
@pytest.mark.parametrize("custom_user_agent", [False, True], ids=["dedicated-ua", "custom-ua"])
def test_disabled_auth_needs_no_fresh_value_on_continue(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    auth: str | None,
    custom_user_agent: bool,
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(
        server.url("/"),
        auth=auth,
        header=["User-Agent: Header/1"],
        user_agent=None if custom_user_agent else "Dedicated/1",
        max_urls=1,
        retries=0,
    )
    assert stopped.summary.state == "stopped"
    assert json.loads(crawl_row(stopped.crawl_file)["config"])["crawl"]["auth"] is None
    requests_before = len(server.requests)

    result = continued(stopped, CrawlOverrides(max_urls=None))

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in server.requests[requests_before:]
    ] == [("/robots.txt", []), ("/next", [])]
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["auth"] is None


@pytest.mark.parametrize("auth", [None, ""], ids=["null", "empty"])
def test_explicit_disabled_auth_replaces_recorded_credentials_on_continue(
    temp_workspace: TempWorkspace, fixture_site: StartSite, auth: str | None
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(server.url("/"), auth="alice:s3cret", max_urls=1, retries=0)
    requests_before = len(server.requests)

    result = continued(stopped, CrawlOverrides(max_urls=None, auth=auth))

    assert result.summary.state == "completed"
    assert [
        (request.path, request.headers.getall("Authorization", []))
        for request in server.requests[requests_before:]
    ] == [("/robots.txt", []), ("/next", [])]
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["auth"] is None


@pytest.mark.parametrize("auth", ["***", "missing-colon", "alice:bad\nvalue", "alice:\ud800"])
def test_invalid_fresh_auth_is_refused_without_quoting_it_or_opening_a_writer(
    temp_workspace: TempWorkspace, fixture_site: StartSite, auth: str
) -> None:
    server = fixture_site(Site({"/": Page(body='<a href="/next">Next</a>')}))
    stopped = crawl_result(server.url("/"), auth="alice:s3cret", max_urls=1, retries=0)
    before = sha256_of(stopped.crawl_file)
    requests = server.requests
    reporter = Collected()

    with read_only_file(stopped.crawl_file), pytest.raises(OpenLinxError) as caught:
        continued(stopped, CrawlOverrides(auth=auth), reporter=reporter)

    assert (caught.value.code, caught.value.exit_code, caught.value.diagnostic.details) == (
        "invalid_value",
        2,
        {"key": "crawl.auth"},
    )
    diagnostic = json.dumps(caught.value.diagnostic.to_json(), ensure_ascii=False)
    assert json.dumps(auth, ensure_ascii=False)[1:-1] not in diagnostic
    assert reporter.events == []
    assert sha256_of(stopped.crawl_file) == before
    assert server.requests == requests


def _refuse_fresh_auth(result: UrlResult) -> tuple[PageRow, ...]:
    raise ValueError(
        "refused test:123£ / 123£ / dGVzdDoxMjPCow== / Basic dGVzdDoxMjPCow==; staging"
    )


def test_fresh_auth_is_masked_in_continue_diagnostics(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site({"/": Page(body='<a href="/next">Next</a>'), "/next": Page(body="Next")})
    )
    stopped = crawl_result(server.url("/"), auth="alice:old123", max_urls=1, retries=0)
    reporter = Collected()
    hooks = Hooks(handlers=(handler("auth", _refuse_fresh_auth, write_pages),))

    result = continued(
        stopped, CrawlOverrides(max_urls=None, auth="test:123£"), hooks, reporter=reporter
    )

    assert result.summary.state == "completed"
    for diagnostics in (
        [warning.to_json() for warning in reporter.warnings],
        [warning.to_json() for warning in result.warnings],
        json.loads(crawl_row(result.crawl_file)["warnings"]),
    ):
        assert [(item["code"], item["details"]["error"]) for item in diagnostics] == [
            ("handler_failed", "refused *** / *** / *** / ***; staging")
        ]
        diagnostic = json.dumps(diagnostics, ensure_ascii=False)
        for secret in ("test:123£", "123£", "dGVzdDoxMjPCow==", "Basic dGVzdDoxMjPCow=="):
            assert secret not in diagnostic
