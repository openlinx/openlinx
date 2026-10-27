"""The response_codes Rules (040-add-rules, rules; seam 2)."""

from spider.rules.response_codes import (
    INTERNAL_4XX,
    INTERNAL_5XX,
    INTERNAL_BLOCKED_BY_ROBOTS_TXT,
    INTERNAL_NO_RESPONSE,
)
from spider.store.records import AffectedUrl
from tests.support.rules import (
    crawl_with_url,
    evaluate_rule,
    failed,
    kept_out_by_robots_txt,
    responded,
    unrecorded,
)
from tests.support.workspace import TempWorkspace


def test_client_error(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "https://example.test/gone", responded(404))

    assert evaluate_rule(crawl_file, INTERNAL_4XX) == [
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
        evaluate_rule(gone, INTERNAL_4XX),
        evaluate_rule(disallowed, INTERNAL_BLOCKED_BY_ROBOTS_TXT),
    ) == ([], [])


def test_an_internal_url_outside_the_scope_is_an_internal_url(
    temp_workspace: TempWorkspace,
) -> None:
    # A Section Crawl requests the Internal URLs outside its folder that its Pages link to.
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/gone", responded(404), in_scope=False
    )

    assert evaluate_rule(crawl_file, INTERNAL_4XX) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 404})
    ]


def test_server_error(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "https://example.test/err", responded(503))

    assert evaluate_rule(crawl_file, INTERNAL_5XX) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 503})
    ]


def test_no_response(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/slow", failed("timeout")
    )

    assert evaluate_rule(crawl_file, INTERNAL_NO_RESPONSE) == [
        AffectedUrl(url_id=url_id, detail={"error": "timeout"})
    ]


def test_a_url_that_failed_to_be_recorded_is_no_issue(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_url(temp_workspace, "https://example.test/odd", unrecorded())

    assert evaluate_rule(crawl_file, INTERNAL_NO_RESPONSE) == []


def test_blocked_even_when_crawled_anyway(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace,
        "https://example.test/private/a",
        responded(200, blocked_by_robots_txt=True),
    )

    assert evaluate_rule(crawl_file, INTERNAL_BLOCKED_BY_ROBOTS_TXT) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]


def test_a_url_that_robots_txt_kept_from_being_requested_is_blocked(
    temp_workspace: TempWorkspace,
) -> None:
    crawl_file, url_id = crawl_with_url(
        temp_workspace, "https://example.test/private/b", kept_out_by_robots_txt()
    )

    assert evaluate_rule(crawl_file, INTERNAL_BLOCKED_BY_ROBOTS_TXT) == [
        AffectedUrl(url_id=url_id, detail=None)
    ]
