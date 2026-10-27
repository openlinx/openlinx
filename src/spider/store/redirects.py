"""The redirects of the urls table: the hop limit and loops, each read back from the file, so a
replayed unit gives the same result (022-add-fetch-policy D2)."""

from sqlalchemy import Connection, bindparam, select, update

from spider.store.records import DiscoveredVia
from spider.store.schema import urls

_FOUND_ON = select(urls.c.discovered_via, urls.c.found_on_url_id).where(
    urls.c.id == bindparam("url_id")
)
_REDIRECT_URL_ID = (
    update(urls)
    .where(urls.c.id == bindparam("url_id"))
    .values(redirect_url_id=bindparam("target_id"))
)
_REDIRECTS_TO = select(urls.c.redirect_url_id).where(urls.c.id == bindparam("url_id"))
_IN_LOOP = update(urls).where(urls.c.id == bindparam("url_id")).values(in_redirect_loop=True)


def chain_via(
    connection: Connection, via: DiscoveredVia, found_on: int | None, limit: int
) -> DiscoveredVia:
    """How the first URL of the chain that led to a URL was found."""
    return _chain_back(connection, via, found_on, limit)[1]


def past_the_hop_limit(connection: Connection, url_id: int, limit: int) -> bool:
    """Whether a redirect from the URL would be more than `limit` consecutive redirects."""
    via, found_on = connection.execute(_FOUND_ON, {"url_id": url_id}).one()
    return _chain_back(connection, via, found_on, limit)[0] >= limit


def link_redirect(connection: Connection, url_id: int, target_id: int, limit: int) -> None:
    """Records the URL's redirect to its target, and marks the loop it closes, if any."""
    connection.execute(_REDIRECT_URL_ID, {"url_id": url_id, "target_id": target_id})
    loop = _loop_through(connection, url_id, target_id, limit)
    if loop:
        connection.execute(_IN_LOOP, [{"url_id": looping} for looping in loop])


def _chain_back(
    connection: Connection, via: DiscoveredVia, found_on: int | None, limit: int
) -> tuple[int, DiscoveredVia]:
    # The consecutive redirects that led to a URL, read back from the file so a replayed unit
    # counts the same, and how its chain's first URL was found; at most `limit`
    # point reads, which no chain passes, since the target past the limit is never queued
    # (022-add-fetch-policy D2).
    hops = 0
    while via == "redirect" and found_on is not None and hops < limit:
        hops += 1
        via, found_on = connection.execute(_FOUND_ON, {"url_id": found_on}).one()
    return hops, via


def _loop_through(connection: Connection, url_id: int, target_id: int, limit: int) -> list[int]:
    # The redirect just stored can only close a loop that runs through it: walk forward from
    # its target, at most `limit` + 1 reads, back to the URL. A URL seen twice is a loop that
    # does not run through it, which ends the walk at once (022-add-fetch-policy D2).
    path = [url_id]
    for _ in range(limit + 1):
        if target_id == url_id:
            return path
        if target_id in path:
            break
        path.append(target_id)
        following = connection.execute(_REDIRECTS_TO, {"url_id": target_id}).scalar()
        if following is None:
            break
        target_id = following
    return []
