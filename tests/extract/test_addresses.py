"""The display form of a URL (design D17 of 030-add-page-data; seam 4)."""

from hypothesis import given, reject
from hypothesis import strategies as st

from spider.crawl.urls import normalize_url
from spider.extract.addresses import display_address

# Escapes and characters whose display forms could meet: escaped ASCII, both letter cases,
# raw and escaped non-ASCII, the characters that stay encoded, and bytes that are no UTF-8.
_PIECES = st.sampled_from(
    [
        "a",
        "/",
        "%2F",
        "%2f",
        "%25",
        "%3F",
        "?",
        "ü",
        "%C3%BC",
        "%c3%bc",
        "\N{NO-BREAK SPACE}",
        "%C2%A0",
        "\N{RIGHT-TO-LEFT OVERRIDE}",
        "%E2%80%AE",
        "%C2%9B",
        "\N{COMBINING ACUTE ACCENT}",
        "%CC%81",
        "\N{FULLWIDTH SOLIDUS}",
        "%EF%BC%8F",
        "%FF",
        "%E2%82",
    ]
)
_URLS = st.builds(
    "https://{}/{}".format,
    st.sampled_from(
        ["site.test", "site.test:8080", "bücher.test", "xn--bcher-kva.test", "xn--zz.test"]
    ),
    st.lists(_PIECES, max_size=6).map("".join),
)


@given(_URLS)
def test_an_address_normalises_back_to_its_url(text: str) -> None:
    # So two distinct URLs never share an address, as the unique index pages_address needs.
    url = normalize_url(text)
    if not isinstance(url, str):
        reject()

    assert normalize_url(display_address(url)) == url
