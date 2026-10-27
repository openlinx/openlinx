"""The security Rule (040-add-rules, rules; seam 2)."""

from spider.rules.registry import RULES
from spider.rules.security import HTTP_URL
from spider.store.issues import read_affected_urls
from spider.store.records import AffectedUrl
from tests.support.rules import crawl_with_url, responded
from tests.support.workspace import TempWorkspace


def test_content_served_over_http(temp_workspace: TempWorkspace) -> None:
    crawl_file, url_id = crawl_with_url(temp_workspace, "http://example.test/a", responded(200))

    assert read_affected_urls(crawl_file, HTTP_URL.id, RULES) == [
        AffectedUrl(url_id=url_id, detail={"status_code": 200})
    ]


def test_http_url_that_redirects_to_https(temp_workspace: TempWorkspace) -> None:
    crawl_file, _ = crawl_with_url(temp_workspace, "http://example.test/b", responded(301))

    assert read_affected_urls(crawl_file, HTTP_URL.id, RULES) == []
