"""URL normalisation (020-add-crawl-core, crawling)."""

from spider.crawl.urls import normalize_url


def test_scheme_and_host_case_the_default_port_and_the_fragment_are_normalised() -> None:
    assert normalize_url("HTTP://Site.TEST:80/About#team") == "http://site.test/About"


def test_a_non_default_port_is_kept() -> None:
    assert normalize_url("https://site.test:8443/a") == "https://site.test:8443/a"


def test_dot_segments_are_resolved() -> None:
    assert normalize_url("https://site.test/a/./b/../c") == "https://site.test/a/c"


def test_an_empty_path_becomes_a_slash() -> None:
    assert normalize_url("https://site.test") == "https://site.test/"


def test_percent_encodings_are_normalised() -> None:
    assert normalize_url("http://site.test/%7euser/a%2fb") == "http://site.test/~user/a%2Fb"


def test_characters_outside_ascii_are_percent_encoded() -> None:
    assert normalize_url("http://site.test/café?q=ü") == "http://site.test/caf%C3%A9?q=%C3%BC"
