"""URL normalisation (020-add-crawl-core, crawling)."""

import re
from urllib.parse import urlsplit

import pytest
from hypothesis import given, reject
from hypothesis import strategies as st
from yarl import URL

from spider.crawl.urls import (
    NORMAL_FORM,
    InvalidUrl,
    NormalizedUrl,
    normalize_url,
    parse_seed,
    strip_params_pattern,
)

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
        ("http://[v1.x]/", InvalidUrl("invalid_host")),
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


def test_removing_every_parameter_removes_the_query() -> None:
    strip = strip_params_pattern(["*"])

    assert normalize_url("http://site.test/p?a=1&b=2", strip) == "http://site.test/p"


def test_parameters_are_kept_by_default() -> None:
    assert normalize_url("http://site.test/p?utm_source=x") == "http://site.test/p?utm_source=x"


def test_a_bare_host_becomes_an_https_seed() -> None:
    assert parse_seed("site.test/shop") == "https://site.test/shop"


@given(st.text(_ANY_CHARACTER))
def test_the_seed_parser_accepts_any_text(text: str) -> None:
    assert isinstance(parse_seed(text), (str, InvalidUrl))


@pytest.mark.parametrize(
    "text", ["https://user:pass@site.test/", "https://user@site.test/", "http://@site.test/"]
)
def test_a_url_with_userinfo_is_rejected(text: str) -> None:
    assert normalize_url(text) == InvalidUrl("userinfo")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mailto:a@b.test", InvalidUrl("unsupported_scheme")),
        ("tel:+1-555-0100", InvalidUrl("unsupported_scheme")),
        ("javascript:alert(1)", InvalidUrl("unsupported_scheme")),
        ("ftp:x", InvalidUrl("unsupported_scheme")),
        ("localhost:8080", NormalizedUrl("https://localhost:8080/")),
        ("site.test:8080/x", NormalizedUrl("https://site.test:8080/x")),
    ],
)
def test_a_seed_has_a_scheme_unless_a_port_follows_its_colon(
    text: str, expected: NormalizedUrl | InvalidUrl
) -> None:
    assert parse_seed(text) == expected


@given(
    st.one_of(
        st.sampled_from(["http", "HTTPS", "mailto", "tel", "javascript", "data", "ftp", "x"]),
        st.from_regex(r"[A-Za-z][A-Za-z0-9+.\-]*", fullmatch=True),
    ),
    # The Seed is stripped first, so "80 " after the colon is a port too.
    st.text(_ANY_CHARACTER).filter(lambda rest: not re.match(r"[0-9]+(?:[/?#]|$)", rest.rstrip())),
)
def test_an_accepted_seed_keeps_the_scheme_its_text_names(scheme: str, rest: str) -> None:
    result = parse_seed(f"{scheme}:{rest}")

    assert isinstance(result, InvalidUrl) or urlsplit(result).scheme == scheme.lower()


def test_brackets_outside_the_host_are_percent_encoded() -> None:
    assert normalize_url("http://site.test/[x]?b=[1]") == "http://site.test/%5Bx%5D?b=%5B1%5D"


@given(st.lists(st.text(_ANY_CHARACTER)), st.text(_ANY_CHARACTER))
def test_normalising_with_any_strip_params_gives_a_url_or_a_rejection(
    values: list[str], text: str
) -> None:
    result = normalize_url(f"http://site.test/p?{text}", strip_params_pattern(values))

    assert isinstance(result, (str, InvalidUrl))


def test_a_stray_percent_is_encoded_before_escapes_are_decoded() -> None:
    assert normalize_url("http://site.test/%2%41") == "http://site.test/%252A"


@given(st.from_regex(NORMAL_FORM, fullmatch=True))
def test_a_url_in_normal_form_is_returned_as_it_is(url: str) -> None:
    # A fragment keeps the URL off the fast path, and the full normalisation drops it.
    assert normalize_url(f"{url}#f") == url


_NEAR_MISSES = st.builds(
    "{}://{}{}{}{}{}".format,
    st.sampled_from(["http", "https", "HTTP", "Https"]),
    st.sampled_from(
        [
            "site.test",
            "Site.test",
            "127.0.0.1",
            "127.01",
            "0127.0.0.1",
            "xn--bcher-kva.test",
            "XN--bcher-kva.test",
            "bücher.test",
            "site.test.",
        ]
    ),
    st.sampled_from(["", ":80", ":443", ":8080", ":080", ":99999"]),
    st.lists(
        st.one_of(
            st.sampled_from([".", "..", "", "a", "%41", "%7e", "%2F", "A b", "[x]", "café"]),
            st.text("abc-._~:@!$&'()*+,;=", max_size=4),
        ),
        min_size=1,
    ).map(lambda segments: "/" + "/".join(segments)),
    st.sampled_from(["", "?", "?a=1", "?a=%41", "?a=[1]", "?a=1/b?c"]),
    st.sampled_from(["", "#", "#x"]),
)


@given(_NEAR_MISSES)
def test_the_fast_path_agrees_with_the_full_normalisation(url: str) -> None:
    assert normalize_url(url) == normalize_url(f"{url}#f")
