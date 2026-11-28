"""Read a Page and its related rows within one Crawl snapshot."""

from collections.abc import Sequence
from difflib import get_close_matches
from pathlib import Path
from typing import Any

import orjson
from sqlalchemy import Connection, bindparam, select

from openlinx.crawl.urls import InvalidUrl, normalize_url
from openlinx.extract.addresses import display_address
from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import HEADERS_NOT_STORED, URL_NOT_FOUND
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.query import page_issues_in
from openlinx.store.rule_queries import RuleQuery
from openlinx.store.schema import crawl, pages, response_headers, urls

_PAGE = select(pages).join(urls, urls.c.id == pages.c.url_id).where(urls.c.url == bindparam("url"))
_NEIGHBOURS_BEFORE = (
    select(pages.c.address)
    .where(pages.c.address < bindparam("address"))
    .order_by(pages.c.address.desc())
    .limit(50)
)
_NEIGHBOURS_AFTER = (
    select(pages.c.address)
    .where(pages.c.address >= bindparam("address"))
    .order_by(pages.c.address)
    .limit(50)
)
_HOP = select(urls.c.url, urls.c.status_code, urls.c.redirect_url_id).where(
    urls.c.id == bindparam("id")
)
_HEADERS = select(response_headers.c.headers).where(response_headers.c.url_id == bindparam("id"))
_SECTION = select(crawl.c.section_crawl)
_LINK_COUNTS = ("inlinks", "unique_inlinks", "outlinks", "unique_outlinks", "external_outlinks")


def page_in(
    connection: Connection,
    path: Path,
    address: str,
    catalogue: Sequence[RuleQuery],
    *,
    headers: bool,
) -> dict[str, Any]:
    """Return the single Page document, matching the URL in the same form as the Crawler."""
    normalized = normalize_url(address)
    if isinstance(normalized, InvalidUrl):
        raise _missing(connection, address, address)
    row = connection.execute(_PAGE, {"url": normalized}).mappings().one_or_none()
    if row is None:
        raise _missing(connection, address, display_address(normalized))

    url_id = row["url_id"]
    columns = {str(name): value for name, value in row.items()}
    link_counts = {name: columns[name] for name in _LINK_COUNTS}
    link_counts["partial"] = bool(connection.scalar(_SECTION))
    result = {
        "url": columns["address"],
        "segment": None,
        "columns": columns,
        "issues": page_issues_in(connection, path, catalogue, url_id),
        "redirect_chain": _redirect_chain(connection, url_id),
        "link_counts": link_counts,
        "html_stored": False,
    }
    if headers:
        result["headers"] = _recorded_headers(connection, url_id, columns["address"])
    return result


def _missing(connection: Connection, given: str, address: str) -> OpenLinxError:
    neighbours = [
        *connection.scalars(_NEIGHBOURS_BEFORE, {"address": address}),
        *connection.scalars(_NEIGHBOURS_AFTER, {"address": address}),
    ]
    return OpenLinxError(
        URL_NOT_FOUND,
        f"The Crawl has no Page for {given!r}.",
        hint=f"Use {COMMAND_NAME} pages to list the recorded Page addresses.",
        details={"suggestions": get_close_matches(address, neighbours, n=5)},
    )


def _redirect_chain(connection: Connection, url_id: int) -> list[dict[str, str | int | None]]:
    first = connection.execute(_HOP, {"id": url_id}).one()
    target = first.redirect_url_id
    if target is None:
        return []
    chain = [{"url": first.url, "status_code": first.status_code}]
    seen = {url_id}
    while target is not None and target not in seen:
        seen.add(target)
        hop = connection.execute(_HOP, {"id": target}).one()
        chain.append({"url": hop.url, "status_code": hop.status_code})
        target = hop.redirect_url_id
    return chain


def _recorded_headers(connection: Connection, url_id: int, address: str) -> list[dict[str, str]]:
    raw = connection.scalar(_HEADERS, {"id": url_id})
    if raw is not None:
        headers = orjson.loads(raw)
        if headers:
            return [{"name": name, "value": value} for name, value in headers]
    raise OpenLinxError(
        HEADERS_NOT_STORED,
        f"The Crawl has no recorded response headers for {address!r}.",
        hint="Check the URL had an HTTP response in the selected Crawl.",
    )
