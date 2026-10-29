"""An extractor's own config (020-add-crawl-core D9; seam 4)."""

import pickle
from datetime import UTC, datetime

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import PageInput, PageSettings, extractor, prepare_page
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl

SITE = NormalizedUrl("http://site.test/")
_PAGE = FetchResult(
    status_code=200,
    reason="OK",
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
        extractors=(extractor("greeting", _greet, Greeting("hi")),),
        strip_params=None,
    )

    assert prepare_page(SITE, _PAGE, settings).outputs == (("greeting", Greeted("hi")),)


def test_an_extractor_and_its_config_survive_the_trip_to_a_worker_process() -> None:
    greeting = extractor("greeting", _greet, Greeting("hi"))

    # Our own bytes, as 026's pool sends them, never data from outside.
    assert pickle.loads(pickle.dumps(greeting)) == greeting  # noqa: S301


class Mutable(msgspec.Struct):
    text: str


def _mutable(tree: LexborHTMLParser, page: PageInput, config: Mutable) -> Greeted:
    return Greeted(config.text)


def test_an_extractor_s_config_must_be_frozen() -> None:
    with pytest.raises(TypeError, match="frozen"):
        extractor("mutable", _mutable, Mutable("hi"))


def _from_a_dict(tree: LexborHTMLParser, page: PageInput, config: dict[str, str]) -> Greeted:
    return Greeted(config["text"])


def test_an_extractor_s_config_must_be_a_struct() -> None:
    with pytest.raises(TypeError, match="struct"):
        # A wrong call on purpose: mypy refuses it, and the check must refuse it at run time too.
        extractor("dict", _from_a_dict, {"text": "hi"})  # type: ignore[type-var]


def _headings(tree: LexborHTMLParser, page: PageInput, config: None) -> dict[str, str]:
    return {"h1": heading.text() if (heading := tree.css_first("h1")) else ""}


def test_an_extractor_whose_function_returns_no_struct_cannot_be_built() -> None:
    with pytest.raises(TypeError, match="struct"):
        # mypy refuses it too; the check refuses an extractor that mypy never saw.
        extractor("headings", _headings, None)  # type: ignore[type-var]
