"""An extractor's own config (020-add-crawl-core D9; seam 4)."""

import json
import pickle
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult
from openlinx.crawl.pages.preparation import PageInput, PageSettings, extractor, prepare_page
from openlinx.crawl.scope import scope_rules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.services.hooks import default_hooks

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


def _nested() -> Callable[[LexborHTMLParser, PageInput, Greeting], Greeted]:
    def greet(tree: LexborHTMLParser, page: PageInput, config: Greeting) -> Greeted:
        return Greeted(config.text)

    return greet


@pytest.mark.parametrize(
    "extract",
    [_nested(), lambda tree, page, config: Greeted(config.text)],
    ids=["nested", "lambda"],
)
def test_an_extractor_whose_function_is_not_module_level_cannot_be_built(
    extract: Callable[[LexborHTMLParser, PageInput, Greeting], Greeted],
) -> None:
    with pytest.raises(
        TypeError,
        match="the function of the extractor greeting is not module-level: a parse worker "
        "process imports it by name; pass values through config",
    ):
        extractor("greeting", extract, Greeting("hi"))


def test_the_default_page_settings_pickle() -> None:
    settings = PageSettings(
        scope=scope_rules(SITE, include=(re.compile("/blog/"),)),
        extractors=default_hooks().extractors,
        strip_params=re.compile("^utm_"),
    )

    try:
        # Our own bytes, as 026's pool sends them, never data from outside.
        restored = pickle.loads(pickle.dumps(settings))  # noqa: S301
    except (pickle.PicklingError, AttributeError, TypeError) as error:
        pytest.fail(
            f"the page settings of default_hooks() reach a parse worker by pickle ({error}): "
            "build each extractor from a module-level function and a module-level config struct"
        )
    assert restored == settings, (
        "the page settings of default_hooks() unpickle unequal: give each extractor's config "
        "struct value equality"
    )


def _settings_from_the_body(tree: LexborHTMLParser, page: PageInput, config: None) -> Greeted:
    paragraph = tree.css_first("p")
    settings = json.loads(paragraph.text() if paragraph else "")
    return Greeted(settings["text"])


def test_an_error_raised_in_a_library_points_at_the_extractor_s_line() -> None:
    settings = PageSettings(
        scope=scope_rules(SITE),
        extractors=(extractor("settings", _settings_from_the_body, None),),
        strip_params=None,
    )

    ((at, error_type),) = [
        (failed.at, failed.error_type)
        for failed in prepare_page(SITE, _PAGE, settings).extractor_failures
    ]
    assert (at, error_type) == (
        f"tests/crawl/test_extractors.py:{_settings_from_the_body.__code__.co_firstlineno + 2}",
        "JSONDecodeError",
    )


class _Misformatted(Exception):
    """A library error whose message is formatted when it is printed, from too few args."""

    def __str__(self) -> str:
        return "%s at %s" % self.args  # noqa: UP031


def _misformatted(tree: LexborHTMLParser, page: PageInput, config: None) -> Greeted:
    raise _Misformatted("no body")


def test_an_error_that_cannot_be_printed_costs_only_the_extractor_s_output() -> None:
    settings = PageSettings(
        scope=scope_rules(SITE),
        extractors=(
            extractor("greeting", _greet, Greeting("hi")),
            extractor("misformatted", _misformatted, None),
        ),
        strip_params=None,
    )

    prepared = prepare_page(SITE, _PAGE, settings)

    assert (
        prepared.outputs,
        [(failed.hook, failed.text) for failed in prepared.extractor_failures],
    ) == (
        (("greeting", Greeted("hi")),),
        [("misformatted", "<_Misformatted that cannot be printed>")],
    )


def test_an_extractor_compiled_from_text_names_no_line() -> None:
    # As a rule language compiles its rules: a function with no module.
    namespace: dict[str, object] = {"Greeted": Greeted}
    source = "def rule(tree, page, config) -> Greeted:\n    raise ValueError('no title')\n"
    exec(compile(source, "<rule title>", "exec"), namespace)  # noqa: S102
    rule = cast(Callable[[LexborHTMLParser, PageInput, None], Greeted], namespace["rule"])
    settings = PageSettings(
        scope=scope_rules(SITE), extractors=(extractor("title", rule, None),), strip_params=None
    )

    ((failed,),) = [prepare_page(SITE, _PAGE, settings).extractor_failures]
    assert (failed.text, failed.at) == ("no title", None)
