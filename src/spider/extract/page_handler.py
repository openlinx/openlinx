"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

import msgspec

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import header_values
from spider.crawl.pages.preparation import is_html_type
from spider.crawl.pages.refresh import refresh_url
from spider.crawl.references import C0_OR_SPACE
from spider.extract.addresses import display_address, path_and_query
from spider.extract.cookies import cookie_row
from spider.extract.dates import internet_date
from spider.extract.page_data import PAGE_DATA, PageData
from spider.extract.status_phrases import STATUS_PHRASES
from spider.store.page_records import CookieRow, PageRow, RedirectType

# An HTTP Refresh comes before a meta refresh.
_REFRESH_TYPES: tuple[RedirectType, ...] = ("http_refresh", "meta_refresh")
# The rel tokens of a pagination Link, as 020 lowercases them.
_NEXT = frozenset({"next"})
_PREVIOUS = frozenset({"prev", "previous"})


def page_rows(result: UrlResult) -> Iterable[PageRow]:
    page = _page_response(result)
    if page is None:
        return ()
    response, content_type = page
    data = PAGE_DATA.output(result.outputs)
    address = display_address(result.url)
    url_path, url_query = path_and_query(address)
    return (
        PageRow(
            url_id=result.url_id,
            address=address,
            url_encoded_address=result.url,
            url_path=url_path,
            url_query=url_query,
            content_type=content_type,
            status_code=response.status_code,
            # The fetcher records "" for a status line without a phrase.
            status=response.reason or STATUS_PHRASES.get(response.status_code),
            response_time_ms=response.response_time_ms,
            last_modified=_last_modified(response.headers),
            **_redirect(result, data),
            set_cookie_count=len(header_values(response.headers, "Set-Cookie")),
            crawl_timestamp=response.fetched_at,
            **({} if data is None else msgspec.structs.asdict(data)),
            **_robots_columns(result, response),
            **_canonical_columns(result),
            **_pagination_columns(result),
        ),
    )


def cookie_rows(result: UrlResult) -> Iterable[CookieRow]:
    page = _page_response(result)
    if page is None:
        return ()
    response, _ = page
    return tuple(
        cookie_row(result.url_id, ordinal, value)
        for ordinal, value in enumerate(header_values(response.headers, "Set-Cookie"), 1)
    )


def _redirect(result: UrlResult, data: PageData | None) -> dict[str, Any]:
    # 020 reads the Refresh header of a 2xx response and the meta refresh of a prepared one;
    # a refresh of the Page itself, as a live page reloads, is no redirect.
    for link_type in _REFRESH_TYPES:
        refresh = next((link for link in result.links if link.type == link_type), None)
        if link_type == "meta_refresh" and not _first_meta_refresh_names_a_url(data):
            continue
        if refresh is not None and refresh.target != result.url:
            return {"redirect_url": refresh.target, "redirect_type": link_type}
    return {"redirect_url": None, "redirect_type": None}


def _first_meta_refresh_names_a_url(data: PageData | None) -> bool:
    # A browser acts on the first meta refresh only, so one without a URL, such as a reload,
    # stops a later one. Without the Page extractor's output, the first Link has to do.
    if data is None:
        return True
    return data.meta_refresh is not None and refresh_url(data.meta_refresh) is not None


def _canonical_columns(result: UrlResult) -> dict[str, Any]:
    if not result.parsed:
        return {}
    # A canonical <link> that the parser moved out of <head>, such as after an <img>, is no
    # declaration (design D4).
    declared = [
        link
        for link in result.links
        if link.type == "canonical" and link.declared_in in ("head", "http_header")
    ]
    html = [link for link in declared if link.declared_in == "head"]
    header = [link for link in declared if link.declared_in == "http_header"]
    targets = {link.target for link in declared}
    return {
        "canonical_url": next(iter(targets)) if len(targets) == 1 else None,
        "canonical_link_element_1": html[0].target if html else None,
        "canonical_link_element_2": html[1].target if len(html) > 1 else None,
        "http_canonical": header[0].target if header else None,
        "canonical_count": len(declared),
        # The URL parser removes leading C0 controls and spaces before it reads a scheme.
        "canonical_relative": any(
            not link.raw.lstrip(C0_OR_SPACE).lower().startswith(("http:", "https:"))
            for link in html
        ),
    }


def _pagination_columns(result: UrlResult) -> dict[str, Any]:
    if not result.parsed:
        return {}
    pages = [link for link in result.links if link.type == "pagination"]

    def first(header: bool, rels: frozenset[str]) -> str | None:
        return next(
            (
                link.target
                for link in pages
                if (link.declared_in == "http_header") == header and not rels.isdisjoint(link.rel)
            ),
            None,
        )

    return {
        "rel_next_1": first(False, _NEXT),
        "rel_prev_1": first(False, _PREVIOUS),
        "http_rel_next_1": first(True, _NEXT),
        "http_rel_prev_1": first(True, _PREVIOUS),
    }


def _robots_columns(result: UrlResult, response: UrlResponse) -> dict[str, Any]:
    # The parser's struct is named as the columns. A Page that was not parsed has the
    # directives of its headers alone, so its meta columns stay NULL (design D2).
    directives = msgspec.structs.asdict(response.directives)
    return {
        name: value
        for name, value in directives.items()
        if result.parsed or name.startswith("x_robots_tag")
    }


def _last_modified(headers: tuple[tuple[str, str], ...]) -> datetime | None:
    values = header_values(headers, "Last-Modified")
    return internet_date(values[0]) if values else None


def _page_response(result: UrlResult) -> tuple[UrlResponse, str] | None:
    # The status code does not matter: a 404 or a 301 with an HTML body is a Page (design D2).
    response = result.response
    if response is None or not (result.is_internal and result.in_scope):
        return None
    content_type = response.content_type
    if content_type is None or not is_html_type(content_type):
        return None
    return response, content_type
