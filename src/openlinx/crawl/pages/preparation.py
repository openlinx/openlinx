"""Page preparation: one pure function of a response, behind an executor (020-add-crawl-core D9)."""

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Protocol, get_type_hints

import msgspec
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.fetch.fetcher import FetchResult, header_values
from openlinx.crawl.hook_errors import HookError, hook_error
from openlinx.crawl.pages.decoding import decode_html
from openlinx.crawl.pages.directives import (
    NO_DIRECTIVES,
    RobotsDirectives,
    meta_robots_contents,
    robots_directives,
)
from openlinx.crawl.pages.headers import header_links
from openlinx.crawl.pages.links import base_url, links_in_tree, parse_html
from openlinx.crawl.references import DiscoveredLink
from openlinx.crawl.scope import ScopeRules
from openlinx.crawl.urls import NormalizedUrl
from openlinx.naming import DEFAULT_ROBOTS_TOKEN
from openlinx.store.records import ParseError

_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})


def is_html_type(content_type: str | None) -> bool:
    """The one rule of an HTML response, which 030's Page predicate imports (design D5)."""
    media_type = (content_type or "").partition(";")[0]
    return media_type.strip().lower() in _HTML_TYPES


class PageInput(msgspec.Struct, frozen=True, kw_only=True):
    """What an extractor gets besides the tree; built in the process that parses the Page."""

    url: NormalizedUrl
    status_code: int
    # As received: in order, in their letter case, repeated names kept.
    headers: tuple[tuple[str, str], ...]
    # Of the decoded document, in characters.
    length: int
    links: tuple[DiscoveredLink, ...]
    directives: RobotsDirectives
    # A reference to the snapshot the process holds, never a copy.
    settings: "PageSettings"


@dataclass(frozen=True, slots=True)
class Extractor[C: msgspec.Struct | None, O: msgspec.Struct]:
    """Pure and module-level, so that a 026 worker imports it by name; its config, a struct
    with frozen fields resolved where the hooks are built, travels with it in the settings
    snapshot (design D9)."""

    name: str
    extract: Callable[[LexborHTMLParser, PageInput, C], O]
    config: C
    # Read from the function's return annotation, so a handler gets the output it declares.
    output_type: type[O] = field(init=False)

    def output(self, outputs: Mapping[str, msgspec.Struct]) -> O | None:
        """This extractor's output among a UrlResult's, or None where it failed."""
        output = outputs.get(self.name)
        return output if isinstance(output, self.output_type) else None

    def __post_init__(self) -> None:
        # A callable without a qualname, such as a partial of a module-level function, pickles
        # by reference (023-fix-code-audit D2).
        qualname = getattr(self.extract, "__qualname__", "")
        if "<locals>" in qualname or qualname.endswith("<lambda>"):
            raise TypeError(
                f"the function of the extractor {self.name} is not module-level: a parse worker "
                "process imports it by name; pass values through config"
            )
        object.__setattr__(self, "output_type", _output_type(self.name, self.extract))
        config: object = self.config
        # Shared by every Page of the Crawl and by every 026 worker. The check is shallow: a field
        # may still hold a mutable value.
        if config is not None and not (
            isinstance(config, msgspec.Struct) and config.__struct_config__.frozen
        ):
            raise TypeError(
                f"the config of the extractor {self.name} is not a struct with frozen fields"
            )


def _output_type(name: str, extract: Callable[..., object]) -> type[Any]:
    returned = get_type_hints(extract).get("return")
    if not (isinstance(returned, type) and issubclass(returned, msgspec.Struct)):
        raise TypeError(f"the function of the extractor {name} returns no msgspec struct")
    return returned


def extractor[C: msgspec.Struct | None, O: msgspec.Struct](
    name: str, extract: Callable[[LexborHTMLParser, PageInput, C], O], config: C
) -> Extractor[Any, O]:
    """The one way to build an extractor: mypy checks C here, where the extractor is registered,
    since an Extractor built in place inside Hooks(...) takes C as Any (design D9)."""
    return Extractor(name, extract, config)


@dataclass(frozen=True, slots=True, kw_only=True)
class PageSettings:
    """The settings snapshot: built once per Crawl, and given to each 026 worker once."""

    scope: ScopeRules
    extractors: tuple[Extractor[Any, Any], ...] = ()
    robots_token: str = DEFAULT_ROBOTS_TOKEN
    follow_nofollow: bool = False
    strip_params: re.Pattern[str] | None


class PreparedPage(msgspec.Struct, frozen=True, kw_only=True):
    # Numbered after the Links of the response's headers, which the engine reads itself.
    html_links: tuple[DiscoveredLink, ...] = ()
    directives: RobotsDirectives = NO_DIRECTIVES
    # By extractor name, without the outputs of extractors that failed.
    outputs: tuple[tuple[str, msgspec.Struct], ...] = ()
    extractor_errors: tuple[HookError, ...] = ()
    parse_error: ParseError | None = None
    parse_error_message: str | None = None

    @property
    def parsed(self) -> bool:
        # Only an extractor's failure leaves a Page that something came out of (design D16).
        return self.parse_error in (None, "extractor_error")


def response_directives(
    response: FetchResult, token: str, meta_contents: Iterable[str] = ()
) -> RobotsDirectives:
    return robots_directives(meta_contents, header_values(response.headers, "X-Robots-Tag"), token)


def prepare_page(url: NormalizedUrl, response: FetchResult, settings: PageSettings) -> PreparedPage:
    """Decodes and parses once; the link extractor and later extractors share the tree."""
    decoded = decode_html(response.body, response.header("Content-Type"))
    tree = parse_html(decoded.text)
    is_internal = partial(_is_internal, settings.scope)
    directives = response_directives(response, settings.robots_token, meta_robots_contents(tree))
    # The header Links come first, as 030's ordinals count them (design D5).
    from_headers = response_links(url, response, settings.scope, settings.strip_params)
    from_html = tuple(
        links_in_tree(
            tree,
            base=base_url(tree, url, decoded.encoding),
            encoding=decoded.encoding,
            is_internal=is_internal,
            strip_params=settings.strip_params,
            page_nofollow=directives.nofollow,
            follow_nofollow=settings.follow_nofollow,
            first_ordinal=len(from_headers) + 1,
        )
    )
    page = PageInput(
        url=url,
        status_code=response.status_code,
        headers=response.headers,
        length=len(decoded.text),
        links=from_headers + from_html,
        directives=directives,
        settings=settings,
    )
    outputs: list[tuple[str, msgspec.Struct]] = []
    failures: list[HookError] = []
    for extractor in settings.extractors:
        try:
            output = extractor.extract(tree, page, extractor.config)
            # As declared: a handler reads it by its type, and only a msgspec struct crosses
            # 026's process boundary as it is.
            if not isinstance(output, extractor.output_type):
                raise TypeError(f"{extractor.name} returned {type(output).__name__}")
            outputs.append((extractor.name, output))
        # An extractor is later changes' code: its failure costs only its output (design D16).
        except Exception as error:
            failures.append(hook_error(extractor.name, extractor.extract, error))
    return PreparedPage(
        html_links=from_html,
        directives=directives,
        outputs=tuple(outputs),
        extractor_errors=tuple(failures),
        parse_error="extractor_error" if failures else None,
        # A public column of every Page: the text of one error belongs to the warning.
        parse_error_message="; ".join(f"{failed.hook}: {failed.error_type}" for failed in failures)
        or None,
    )


def response_links(
    url: NormalizedUrl,
    response: FetchResult,
    scope: ScopeRules,
    strip_params: re.Pattern[str] | None,
) -> tuple[DiscoveredLink, ...]:
    """The engine reads them whatever became of the preparation, which reads them for
    `PageInput`, so both number them alike (design D9)."""
    return tuple(
        header_links(
            response.headers,
            url,
            is_internal=partial(_is_internal, scope),
            strip_params=strip_params,
        )
    )


def _is_internal(scope: ScopeRules, url: NormalizedUrl) -> bool:
    return scope.decide(url).is_internal


class PageExecutor(Protocol):
    # Read-only, so a plain attribute or a property both make a PageExecutor.
    @property
    def backlog(self) -> int:
        """How many Pages it may hold beyond the requests in flight (design D7)."""

    @property
    def workers(self) -> int:
        """The processes that prepare Pages besides the crawl process (crawl_started)."""

    async def start(self, settings: PageSettings) -> None:
        """Once, with the snapshot of the final Scope, before the first prepare (design D9)."""

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage: ...

    async def close(self) -> None: ...


class InProcessExecutor:
    """Prepares Pages on the event loop's thread; 026 puts a process pool behind the seam."""

    backlog = 0
    workers = 0

    def __init__(self) -> None:
        self._settings: PageSettings | None = None

    async def start(self, settings: PageSettings) -> None:
        self._settings = settings

    async def prepare(self, url: NormalizedUrl, response: FetchResult) -> PreparedPage:
        if self._settings is None:
            raise RuntimeError("the page executor prepares a Page before it is started")
        return prepare_page(url, response, self._settings)

    async def close(self) -> None:
        pass
