"""An extractor's own config (020-add-crawl-core D9; seam 4)."""

import pickle
from datetime import UTC, datetime

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser

from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import Extractor, PageInput, PageSettings, prepare_page
from spider.crawl.scope import scope_rules
from spider.crawl.urls import NormalizedUrl

SITE = NormalizedUrl("http://site.test/")
_PAGE = FetchResult(
    status_code=200,
    headers=(("Content-Type", "text/html"),),
    body=b"<p>Hello</p>",
    fetched_at=datetime(2026, 10, 16, tzinfo=UTC),
    response_time_ms=1,
)


class Greeting(msgspec.Struct, frozen=True):
    text: str


class Greeted(msgspec.Struct, frozen=True):
    text: str


def _greet(tree: LexborHTMLParser, page: PageInput, config: Greeting) -> Greeted:
    return Greeted(config.text)


def test_an_extractor_gets_its_own_config() -> None:
    settings = PageSettings(
        scope=scope_rules(SITE),
        extractors=(Extractor("greeting", _greet, Greeting("hi")),),
        strip_params=None,
    )

    assert prepare_page(SITE, _PAGE, settings).outputs == (("greeting", Greeted("hi")),)


def test_an_extractor_and_its_config_survive_the_trip_to_a_worker_process() -> None:
    extractor = Extractor("greeting", _greet, Greeting("hi"))

    # Our own bytes, as 026's pool sends them, never data from outside.
    assert pickle.loads(pickle.dumps(extractor)) == extractor  # noqa: S301


class Mutable(msgspec.Struct):
    text: str


def _mutable(tree: LexborHTMLParser, page: PageInput, config: Mutable) -> Greeted:
    return Greeted(config.text)


def test_an_extractor_s_config_must_be_frozen() -> None:
    with pytest.raises(TypeError, match="frozen"):
        Extractor("mutable", _mutable, Mutable("hi"))
