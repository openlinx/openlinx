"""The response_codes Rules (040-add-rules, rules; seam 2)."""

from spider.rules.response_codes import INTERNAL_4XX
from spider.store.issues import evaluate_rule
from spider.store.records import AffectedUrl
from tests.support.rules import crawl_with_url, responded
from tests.support.workspace import TempWorkspace


def test_client_error(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "https://example.test/gone", responded(404))

    assert evaluate_rule(crawl_file, INTERNAL_4XX) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 404})
    ]


def test_external_urls_are_not_internal_urls(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_url(
        temp_workspace, "https://other.test/gone", responded(404), is_internal=False
    )

    assert evaluate_rule(crawl_file, INTERNAL_4XX) == []
