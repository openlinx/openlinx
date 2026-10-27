"""The response_codes Rules (040-add-rules, rules; seam 2)."""

from spider.rules.registry import RULES
from spider.rules.response_codes import (
    INTERNAL_4XX,
    INTERNAL_5XX,
    INTERNAL_BLOCKED_BY_ROBOTS_TXT,
    INTERNAL_NO_RESPONSE,
)
from spider.store.issues import read_affected_urls
from spider.store.records import AffectedUrl
from tests.support.rules import (
    crawl_with_url,
    failed,
    kept_out_by_robots_txt,
    responded,
    unrecorded,
)
from tests.support.workspace import TempWorkspace


def test_client_error(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "https://example.test/gone", responded(404))

    assert read_affected_urls(crawl_file, INTERNAL_4XX.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 404})
    ]


def test_external_urls_are_not_internal_urls(temp_workspace: TempWorkspace) -> None:
    gone, _ = crawl_with_url(
        temp_workspace, "https://other.test/gone", responded(404), is_internal=False
    )
    disallowed, _ = crawl_with_url(
        temp_workspace,
        "https://other.test/private",
        responded(200, blocked_by_robots_txt=True),
        is_internal=False,
    )

    assert (
        read_affected_urls(gone, INTERNAL_4XX.id, RULES),
        read_affected_urls(disallowed, INTERNAL_BLOCKED_BY_ROBOTS_TXT.id, RULES),
    ) == ([], [])


def test_an_internal_url_outside_the_scope_is_an_internal_url(
    temp_workspace: TempWorkspace,
) -> None:
    # A Section Crawl requests the Internal URLs outside its folder that its Pages link to.
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/gone", responded(404), in_scope=False
    )

    assert read_affected_urls(crawl_file, INTERNAL_4XX.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 404})
    ]


def test_server_error(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "https://example.test/err", responded(503))

    assert read_affected_urls(crawl_file, INTERNAL_5XX.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 503})
    ]


def test_no_response(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/slow", failed("timeout")
    )

    assert read_affected_urls(crawl_file, INTERNAL_NO_RESPONSE.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"error": "timeout"})
    ]


def test_a_url_that_failed_to_be_recorded_is_no_issue(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_url(temp_workspace, "https://example.test/odd", unrecorded())

    assert read_affected_urls(crawl_file, INTERNAL_NO_RESPONSE.id, RULES) == []


def test_blocked_even_when_crawled_anyway(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace,
        "https://example.test/private/a",
        responded(200, blocked_by_robots_txt=True),
    )

    assert read_affected_urls(crawl_file, INTERNAL_BLOCKED_BY_ROBOTS_TXT.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_a_url_that_robots_txt_kept_from_being_requested_is_blocked(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/private/b", kept_out_by_robots_txt()
    )

    assert read_affected_urls(crawl_file, INTERNAL_BLOCKED_BY_ROBOTS_TXT.id, RULES) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]
