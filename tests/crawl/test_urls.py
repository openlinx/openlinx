"""URL normalisation (020-add-crawl-core, crawling)."""

from spider.crawl.urls import normalize_url


def test_scheme_and_host_case_the_default_port_and_the_fragment_are_normalised() -> None:
    assert normalize_url("HTTP://Site.TEST:80/About#team") == "http://site.test/About"


def test_a_non_default_port_is_kept() -> None:
    assert normalize_url("https://site.test:8443/a") == "https://site.test:8443/a"
