"""URL normalisation (020-add-crawl-core, crawling)."""

from urllib.parse import urlsplit

import pytest
from hypothesis import given, reject
from hypothesis import strategies as st
from yarl import URL

from spider.crawl.urls import InvalidUrl, NormalizedUrl, normalize_url, strip_params_pattern

# Sharp cases first: UTS46 and IDNA 2003 differ on ß, ς and the joiners, and drop the ignorables.
_HOST_CHARACTERS = st.one_of(
    st.sampled_from("abXY09-._\u00df\u03c2\u0130\u200c\u200d\u00ad\u200b\uff21\u3002"),
    st.characters(exclude_categories=("Cc", "Cs"), exclude_characters=":/?#[]@\\%"),
)


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


def test_an_internationalised_host_becomes_ascii() -> None:
    assert normalize_url("http://bücher.test/") == "http://xn--bcher-kva.test/"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("http://faß.test/", NormalizedUrl("http://xn--fa-hia.test/")),
        ("http://My_Host.test/", NormalizedUrl("http://my_host.test/")),
        ("http://[2001:DB8:0:0::1]:8080/", NormalizedUrl("http://[2001:db8::1]:8080/")),
        ("http://exa mple.test/", InvalidUrl("invalid_host")),
        ("http://e\u200bvil.test/", InvalidUrl("invalid_host")),
    ],
)
def test_hosts_are_encoded_as_aiohttp_requests_them(
    text: str, expected: NormalizedUrl | InvalidUrl
) -> None:
    assert normalize_url(text) == expected


@given(st.text(_HOST_CHARACTERS, min_size=1, max_size=20))
def test_an_accepted_host_is_the_host_aiohttp_requests(host: str) -> None:
    result = normalize_url(f"http://{host}/")
    if isinstance(result, InvalidUrl):
        reject()

    # Host case carries no meaning; the built-in codec keeps the case of ASCII labels.
    assert urlsplit(result).netloc == (URL(f"http://{host}/").raw_host or "").lower()


def test_the_query_and_its_parameter_order_are_kept() -> None:
    assert normalize_url("http://site.test/p?b=2&a=1") == "http://site.test/p?b=2&a=1"


def test_a_trailing_slash_is_kept() -> None:
    results = (normalize_url("http://site.test/a"), normalize_url("http://site.test/a/"))

    assert results == ("http://site.test/a", "http://site.test/a/")


_TEXT = st.text(st.characters(exclude_categories=["Cs"], exclude_characters="/?#"), max_size=8)
_SEGMENTS = st.lists(st.one_of(st.sampled_from([".", "..", "", "%2e", "%7E", "%zz"]), _TEXT))
_URLS = st.builds(
    "{}://{}{}/{}{}{}".format,
    st.sampled_from(["http", "https", "HTTP"]),
    st.sampled_from(["site.test", "Site.TEST", "bücher.test", "faß.test", "127.0.0.1"]),
    st.sampled_from(["", ":80", ":443", ":8443"]),
    _SEGMENTS.map("/".join),
    st.one_of(st.just(""), _TEXT.map("?{}".format)),
    st.one_of(st.just(""), _TEXT.map("#{}".format)),
)


@given(_URLS)
def test_normalising_twice_changes_nothing(url: str) -> None:
    once = normalize_url(url)
    if isinstance(once, InvalidUrl):
        reject()

    assert normalize_url(once) == once


_ANY_CHARACTER = st.characters(exclude_categories=[])


@given(
    st.one_of(
        st.text(_ANY_CHARACTER),
        st.text(_ANY_CHARACTER).map("http://{}".format),
        st.text(_ANY_CHARACTER).map("https://site.test/{}".format),
    )
)
def test_normalising_any_text_gives_a_url_or_a_rejection(text: str) -> None:
    assert isinstance(normalize_url(text), (str, InvalidUrl))


def test_matching_parameters_are_removed() -> None:
    strip = strip_params_pattern(["utm_*,fbclid"])

    assert normalize_url("http://site.test/p?utm_source=x&id=7&fbclid=y", strip) == (
        "http://site.test/p?id=7"
    )
