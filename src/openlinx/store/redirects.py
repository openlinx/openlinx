"""Resolve redirect loops and hop limits from stored rows so replay gives the same result."""

from collections.abc import Iterator

from sqlalchemy import Connection, bindparam, select, text, update

from openlinx.store.records import DiscoveredVia
from openlinx.store.schema import urls

_FOUND_ON = select(urls.c.discovered_via, urls.c.found_on_url_id).where(
    urls.c.id == bindparam("url_id")
)
_REDIRECT_URL_ID = (
    update(urls)
    .where(urls.c.id == bindparam("url_id"))
    .values(redirect_url_id=bindparam("target_id"))
)
_REDIRECTS_TO = select(urls.c.redirect_url_id).where(urls.c.id == bindparam("url_id"))
_FIRST_INCOMING = (
    select(urls.c.id)
    .where(urls.c.redirect_url_id == bindparam("url_id"))
    .order_by(urls.c.id)
    .limit(1)
)
_NEXT_INCOMING = _FIRST_INCOMING.where(urls.c.id > bindparam("after"))

_MARK_LOOP = text("""
    WITH RECURSIVE members(id) AS (
        SELECT :url_id
        UNION ALL
        SELECT urls.redirect_url_id
        FROM members JOIN urls ON urls.id = members.id
        WHERE urls.redirect_url_id != :url_id
    )
    UPDATE urls SET in_redirect_loop = 1 WHERE id IN (SELECT id FROM members)
""")


def chain_via(
    connection: Connection, via: DiscoveredVia, found_on: int | None, limit: int
) -> DiscoveredVia:
    """How the first URL of the chain that led to a URL was found."""
    return _chain_back(connection, via, found_on, limit)[1]


def past_the_hop_limit(connection: Connection, url_id: int, limit: int) -> bool:
    """Whether a redirect from the URL would be more than `limit` consecutive redirects."""
    via, found_on = connection.execute(_FOUND_ON, {"url_id": url_id}).one()
    return _chain_back(connection, via, found_on, limit)[0] >= limit


def link_redirect(connection: Connection, url_id: int, target_id: int) -> None:
    """Record the edge and mark the loop in the same writer unit."""
    closes_loop = _closes_loop(connection, url_id, target_id)
    connection.execute(_REDIRECT_URL_ID, {"url_id": url_id, "target_id": target_id})
    if closes_loop:
        connection.execute(_MARK_LOOP, {"url_id": url_id})


def _chain_back(
    connection: Connection, via: DiscoveredVia, found_on: int | None, limit: int
) -> tuple[int, DiscoveredVia]:
    # The consecutive redirects that led to a URL, read back from the file so a replayed unit
    # counts the same, and how its chain's first URL was found; at most `limit`
    # point reads, which no chain passes, since the target past the limit is never queued.
    hops = 0
    while via == "redirect" and found_on is not None and hops < limit:
        hops += 1
        via, found_on = connection.execute(_FOUND_ON, {"url_id": found_on}).one()
    return hops, via


def _closes_loop(connection: Connection, url_id: int, target_id: int) -> bool:
    # A new edge closes a loop exactly when its target already leads to its source. Alternate
    # between following targets and tracing incoming edges. For a non-loop edge, the work is
    # bounded by the smaller connected component. Charging each merge to that component
    # gives O(n log n) indexed reads, plus one walk and one write per member to mark a loop.
    incoming = _walk_incoming(connection, url_id)
    current = checkpoint = target_id
    interval = remaining = 1
    while current != url_id:
        following: int | None = connection.execute(_REDIRECTS_TO, {"url_id": current}).scalar()
        if following is None or next(incoming, None) is None:
            return False
        current = following
        # Exponentially spaced checkpoints detect a target-side cycle with no visited set.
        if current == checkpoint:
            return False
        remaining -= 1
        if remaining == 0:
            checkpoint = current
            interval *= 2
            remaining = interval
    return True


def _walk_incoming(connection: Connection, url_id: int) -> Iterator[int]:
    # Each URL has at most one outgoing edge, so it supplies its own parent on the way
    # back up. Each step uses indexed reads and carries no stack or set of visited URLs.
    current = url_id
    previous: int | None = None
    while True:
        if previous is None:
            child = connection.execute(_FIRST_INCOMING, {"url_id": current}).scalar()
        else:
            child = connection.execute(
                _NEXT_INCOMING, {"url_id": current, "after": previous}
            ).scalar()
        if child is not None:
            current, previous = child, None
        elif current == url_id:
            return
        else:
            parent: int = connection.execute(_REDIRECTS_TO, {"url_id": current}).scalar_one()
            current, previous = parent, current
        yield current
