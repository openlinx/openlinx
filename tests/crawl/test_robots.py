"""The robots.txt reader (020-add-crawl-core D6; seam 4)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.robots import read_robots_txt
from spider.naming import DEFAULT_ROBOTS_TOKEN

_LAST_RULE = b"\nDisallow: /x"
# The rule /x ends at the 512,000th byte; one byte more would make it /x$, which /xy passes.
_AT_THE_LIMIT = b"User-agent: *\n#" + b"-" * (512_000 - 15 - len(_LAST_RULE)) + _LAST_RULE + b"$"


def test_the_group_for_the_tools_token_applies() -> None:
    robots = read_robots_txt(
        b"User-agent: spider\nDisallow: /a\n\nUser-agent: *\nDisallow: /b", DEFAULT_ROBOTS_TOKEN
    )

    assert (robots.allows("http://site.test/a"), robots.allows("http://site.test/b")) == (
        False,
        True,
    )


def test_only_the_first_512000_bytes_of_robots_txt_are_read() -> None:
    robots = read_robots_txt(_AT_THE_LIMIT, DEFAULT_ROBOTS_TOKEN)

    assert (robots.allows("http://site.test/xy"), robots.allows("http://site.test/b")) == (
        False,
        True,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"# caf\xe9 \xff\nUser-agent: *\nDisallow: /a",
        b"\xef\xbb\xbfUser-agent: *\nDisallow: /a",
        b"User-agent: *\nDisallow: /\xe9\nDisallow: /a",
    ],
)
def test_robots_txt_is_read_as_utf_8_with_replacement(body: bytes) -> None:
    assert read_robots_txt(body, DEFAULT_ROBOTS_TOKEN).allows("http://site.test/a") is False


def test_another_token_can_be_chosen() -> None:
    robots = read_robots_txt(b"User-agent: Googlebot\nDisallow: /g", "Googlebot")

    assert robots.allows("http://site.test/g") is False


_PIECES = st.sampled_from(
    [
        "User-agent:",
        "Allow:",
        "Disallow:",
        "Crawl-delay:",
        "Request-rate:",
        "Visit-time:",
        "Sitemap:",
        "Host:",
        "spider",
        "*",
        "$",
        "%",
        "%zz",
        "%E9",
        "/",
        "#",
        ":",
        " ",
        "\n",
        "\r\n",
        "\r",
        "1e309",
        "-1",
        "nan",
        "1/0s",
        "0400-0845",
        "﻿",
        "é",
    ]
)
_TEXT = st.lists(_PIECES | st.text(max_size=5), max_size=40).map("".join)


@given(_TEXT.map(str.encode) | st.binary(), _TEXT, _TEXT | st.just(DEFAULT_ROBOTS_TOKEN))
def test_any_robots_txt_gives_a_decision(body: bytes, path: str, token: str) -> None:
    assert read_robots_txt(body, token).allows(f"http://site.test/{path}") in {True, False}
