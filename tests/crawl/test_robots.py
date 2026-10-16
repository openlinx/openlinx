"""The robots.txt reader (020-add-crawl-core D6; seam 4)."""

import gc
from types import BuiltinFunctionType, FunctionType, ModuleType

import pytest
from hypothesis import given
from hypothesis import strategies as st

from spider.crawl.robots import (
    OriginRobots,
    RobotsTxt,
    read_robots_txt,
    robots_state,
    robots_txt_text,
)
from spider.naming import DEFAULT_ROBOTS_TOKEN


def _read(body: bytes, token: str = DEFAULT_ROBOTS_TOKEN) -> RobotsTxt:
    return read_robots_txt(robots_txt_text(body), token)


_LAST_RULE = b"\nDisallow: /x"
# The rule /x ends at the 512,000th byte.
_TO_THE_LIMIT = b"User-agent: *\n#" + b"-" * (512_000 - 15 - len(_LAST_RULE)) + _LAST_RULE


def test_the_group_for_the_tool_s_token_applies() -> None:
    robots = _read(b"User-agent: spider\nDisallow: /a\n\nUser-agent: *\nDisallow: /b")

    assert (robots.allows("http://site.test/a"), robots.allows("http://site.test/b")) == (
        False,
        True,
    )


@pytest.mark.parametrize("line_end", [b"\n", b"\r\n", b"\r"])
def test_only_the_first_512000_bytes_of_robots_txt_are_read(line_end: bytes) -> None:
    robots = _read(_TO_THE_LIMIT + line_end + b"Disallow: /b")

    assert (robots.allows("http://site.test/xy"), robots.allows("http://site.test/b")) == (
        False,
        True,
    )


def test_a_line_that_the_limit_cuts_is_dropped() -> None:
    # /x ends at the limit, so the cut rule would be the shorter prefix of /xyz.
    robots = _read(_TO_THE_LIMIT + b"yz")

    assert robots.allows("http://site.test/xy") is True


def _longest_text_reachable(root: object) -> int:
    """The longest str that root's own objects reach, past no class, module or function."""
    longest = 0
    seen: set[int] = set()
    stack = [root]
    while stack:
        item = stack.pop()
        if id(item) in seen or isinstance(
            item, type | ModuleType | FunctionType | BuiltinFunctionType
        ):
            continue
        seen.add(id(item))
        if isinstance(item, str):
            longest = max(longest, len(item))
        stack.extend(gc.get_referents(item))
    return longest


def test_an_origin_s_parsed_rules_keep_no_copy_of_its_text() -> None:
    body = b"User-agent: *\nDisallow: /private/\n#" + b"-" * 100_000
    robots = OriginRobots(state="ok", rules=_read(body), status_code=200)

    assert _longest_text_reachable(robots) < 1000


@pytest.mark.parametrize(
    "body",
    [
        b"# caf\xe9 \xff\nUser-agent: *\nDisallow: /a",
        b"\xef\xbb\xbfUser-agent: *\nDisallow: /a",
        b"User-agent: *\nDisallow: /\xe9\nDisallow: /a",
    ],
)
def test_robots_txt_is_read_as_utf_8_with_replacement(body: bytes) -> None:
    assert _read(body).allows("http://site.test/a") is False


def test_another_token_can_be_chosen() -> None:
    robots = _read(b"User-agent: Googlebot\nDisallow: /g", "Googlebot")

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
        "1e306",
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
    robots = _read(body, token)

    assert (
        robots.allows(f"http://site.test/{path}") in {True, False},
        robots.crawl_delay_ms is None or 0 <= robots.crawl_delay_ms < 2**63,
        all(isinstance(sitemap, str) for sitemap in robots.sitemaps),
    ) == (True, True, True)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Crawl-delay: 5", 5000),
        ("Crawl-delay: 0.5", 500),
        ("Crawl-delay: 1e306", 2**63 - 1),
        ("Crawl-delay: soon", None),
        ("Allow: /", None),
    ],
)
def test_the_crawl_delay_is_in_whole_milliseconds_that_fit_an_integer(
    line: str, expected: int | None
) -> None:
    robots = _read(f"User-agent: *\n{line}".encode())

    assert robots.crawl_delay_ms == expected


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (100, "unreachable"),
        (199, "unreachable"),
        (200, "ok"),
        (204, "ok"),
        (299, "ok"),
        (301, "missing"),
        (404, "missing"),
        (410, "missing"),
        (428, "missing"),
        (429, "unreachable"),
        (430, "missing"),
        (500, "unreachable"),
        (503, "unreachable"),
        (599, "unreachable"),
        (600, "unreachable"),
        (999, "unreachable"),
    ],
)
def test_the_final_robots_txt_response_gives_its_state(status_code: int, expected: str) -> None:
    assert robots_state(status_code) == expected
