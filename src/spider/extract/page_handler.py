"""The Page handler: the rows of a URL that is a Page (030-add-page-data D1, D2)."""

from collections.abc import Iterable
from datetime import datetime
from typing import Literal, TypedDict

import msgspec

from spider.crawl.engine.hooks import UrlResponse, UrlResult
from spider.crawl.fetch.fetcher import header_values
from spider.crawl.pages.directives import RobotsDirectives
from spider.crawl.pages.preparation import is_html_type
from spider.crawl.pages.refresh import refresh_url
from spider.crawl.references import C0_OR_SPACE, DiscoveredLink
from spider.extract.addresses import display_address, path_and_query
from spider.extract.cookies import cookie_row
from spider.extract.dates import internet_date
from spider.extract.page_data import PAGE_DATA, PageData
from spider.extract.status_phrases import STATUS_PHRASES
from spider.store.page_records import CookieRow, IndexabilityStatus, PageRow, RedirectType
from spider.store.records import DeclaredIn, LinkType

# Both a Link type and a redirect type. An HTTP Refresh comes before a meta refresh.
type _Refresh = Literal["http_refresh", "meta_refresh"]
_REFRESH_TYPES: tuple[_Refresh, ...] = ("http_refresh", "meta_refresh")
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
    robots = _robots_columns(result, response.directives)
    canonical = _canonical_columns(result)
    reason = _non_indexable_reason(result, response.status_code, robots, canonical)
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
            indexability="indexable" if reason is None else "non_indexable",
            indexability_status=reason,
            response_time_ms=response.response_time_ms,
            last_modified=_last_modified(response.headers),
            **_redirect(result, data),
            set_cookie_count=len(header_values(response.headers, "Set-Cookie")),
            crawl_timestamp=response.fetched_at,
            **({} if data is None else msgspec.structs.asdict(data)),
            **robots,
            **canonical,
            **_linked_page_columns(result),
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


class _RedirectColumns(TypedDict):
    redirect_url: str | None
    redirect_type: RedirectType | None


# Each of the next three families is NULL for a Page that was not analysed (design D2), so
# its keys are absent then.
class _RobotsColumns(TypedDict, total=False):
    meta_robots: str | None
    meta_robots_noindex: bool
    meta_robots_nofollow: bool
    x_robots_tag: str | None
    x_robots_tag_noindex: bool
    x_robots_tag_nofollow: bool


class _CanonicalColumns(TypedDict, total=False):
    canonical_url: str | None
    canonical_link_element_1: str | None
    canonical_link_element_2: str | None
    http_canonical: str | None
    canonical_count: int
    canonical_relative: bool


class _LinkedPageColumns(TypedDict, total=False):
    rel_next_1: str | None
    rel_prev_1: str | None
    http_rel_next_1: str | None
    http_rel_prev_1: str | None
    amphtml_link_element: str | None
    mobile_alternate_link: str | None


def _redirect(result: UrlResult, data: PageData | None) -> _RedirectColumns:
    # 020 reads the Refresh header of a 2xx response and the meta refresh of a prepared one;
    # a refresh of the Page itself, as a live page reloads, is no redirect.
    for link_type in _REFRESH_TYPES:
        if link_type == "meta_refresh" and not _first_meta_refresh_names_a_url(data):
            continue
        refresh = _first_link(result.links, link_type)
        if refresh is not None and refresh.target != result.url:
            return {"redirect_url": refresh.target, "redirect_type": link_type}
    return {"redirect_url": None, "redirect_type": None}


def _first_meta_refresh_names_a_url(data: PageData | None) -> bool:
    # A browser acts on the first meta refresh only, so one without a URL, such as a reload,
    # stops a later one. Without the Page extractor's output, the first Link has to do.
    if data is None:
        return True
    return data.meta_refresh is not None and refresh_url(data.meta_refresh) is not None


def _non_indexable_reason(
    result: UrlResult,
    status_code: int,
    robots: _RobotsColumns,
    canonical: _CanonicalColumns,
) -> IndexabilityStatus | None:
    # The order a search engine meets them in (design D3). robots.txt can disallow a Page
    # that was fetched anyway, under --ignore-robots.
    if result.blocked_by_robots_txt:
        return "blocked_by_robots_txt"
    if 300 <= status_code < 400:
        return "redirected"
    # A bot-block code such as 999 withholds the Page from crawlers as a 4xx does.
    if 400 <= status_code < 500 or status_code >= 600:
        return "client_error"
    if 500 <= status_code < 600:
        return "server_error"
    if robots.get("meta_robots_noindex") or robots["x_robots_tag_noindex"]:
        return "noindex"
    # Both are normalised URLs, so a self-referencing canonical equals the URL.
    canonical_url = canonical.get("canonical_url")
    if canonical_url is not None and canonical_url != result.url:
        return "canonicalised"
    return None


def _robots_columns(result: UrlResult, directives: RobotsDirectives) -> _RobotsColumns:
    columns: _RobotsColumns = {
        "x_robots_tag": directives.x_robots_tag,
        "x_robots_tag_noindex": directives.x_robots_tag_noindex,
        "x_robots_tag_nofollow": directives.x_robots_tag_nofollow,
    }
    # A Page that was not parsed has the directives of its headers alone.
    if result.parsed:
        columns["meta_robots"] = directives.meta_robots
        columns["meta_robots_noindex"] = directives.meta_robots_noindex
        columns["meta_robots_nofollow"] = directives.meta_robots_nofollow
    return columns


def _canonical_columns(result: UrlResult) -> _CanonicalColumns:
    if not result.parsed:
        return {}
    # A canonical <link> that the parser moved out of <head>, such as after an <img>, is no
    # declaration (design D4).
    html = _links(result.links, "canonical", "head")
    header = _links(result.links, "canonical", "http_header")
    targets = {link.target for link in (*html, *header)}
    return {
        "canonical_url": next(iter(targets)) if len(targets) == 1 else None,
        "canonical_link_element_1": html[0].target if html else None,
        "canonical_link_element_2": html[1].target if len(html) > 1 else None,
        "http_canonical": header[0].target if header else None,
        "canonical_count": len(html) + len(header),
        # The URL parser removes leading C0 controls and spaces before it reads a scheme.
        "canonical_relative": any(
            not link.raw.lstrip(C0_OR_SPACE).lower().startswith(("http:", "https:"))
            for link in html
        ),
    }


def _linked_page_columns(result: UrlResult) -> _LinkedPageColumns:
    if not result.parsed:
        return {}
    pages = [link for link in result.links if link.type == "pagination"]
    html = [link for link in pages if link.declared_in != "http_header"]
    header = [link for link in pages if link.declared_in == "http_header"]
    amphtml = _first_link(result.links, "amphtml")
    mobile = _first_link(result.links, "mobile_alternate")
    return {
        "rel_next_1": _first_target(html, _NEXT),
        "rel_prev_1": _first_target(html, _PREVIOUS),
        "http_rel_next_1": _first_target(header, _NEXT),
        "http_rel_prev_1": _first_target(header, _PREVIOUS),
        "amphtml_link_element": None if amphtml is None else amphtml.target,
        "mobile_alternate_link": None if mobile is None else mobile.target,
    }


def _first_link(links: Iterable[DiscoveredLink], link_type: LinkType) -> DiscoveredLink | None:
    return next((link for link in links if link.type == link_type), None)


def _links(
    links: Iterable[DiscoveredLink], link_type: LinkType, declared_in: DeclaredIn
) -> list[DiscoveredLink]:
    return [link for link in links if link.type == link_type and link.declared_in == declared_in]


def _first_target(links: list[DiscoveredLink], rels: frozenset[str]) -> str | None:
    return next((link.target for link in links if not rels.isdisjoint(link.rel)), None)


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
