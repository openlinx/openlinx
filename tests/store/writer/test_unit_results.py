"""Verify which unit results the Writer can compare during replay."""

from collections.abc import Callable
from enum import Enum

import pytest
from sqlalchemy import Connection, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from openlinx.store.schema import seeds
from openlinx.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import crawl_without_seeds, insert_seed, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import replay_now

SEEDS = "SELECT position, url FROM seeds ORDER BY position"
COUNT = "SELECT count(*) FROM seeds"


def _inserted_cursor(connection: Connection) -> object:
    # Returns what execute returned, a CursorResult bound to this connection.
    return connection.execute(insert(seeds).values(position=1, url="https://example.com/a"))


def _inserted_cursors(connection: Connection) -> object:
    return [connection.execute(insert(seeds).values(position=1, url="https://example.com/a"))]


def _cursors_by_name(connection: Connection) -> object:
    return {"inserted": _inserted_cursor(connection)}


def _set_of_cursors(connection: Connection) -> object:
    return {_inserted_cursor(connection)}


@pytest.mark.parametrize(
    "unit",
    [_inserted_cursor, _inserted_cursors, _cursors_by_name, _set_of_cursors],
    ids=["cursor", "in a list", "a dict's value", "in a set"],
)
def test_a_unit_that_returns_a_cursor_is_refused(
    temp_workspace: TempWorkspace, unit: Callable[[Connection], object]
) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        with pytest.raises(TypeError) as refused:
            writer.run(unit)
        writer.run(insert_seed(2, "https://example.com/b"))

    assert (str(refused.value), query(crawl.path, SEEDS)) == (
        f"the unit {unit.__qualname__} returned a CursorResult, which compares by identity, so "
        "a replay cannot check it: return values, such as .all() rows or a record",
        [(2, "https://example.com/b")],
    )


class _Seeded(Enum):
    NEW = "new"
    KNOWN = "known"


def _seeded(connection: Connection) -> _Seeded:
    inserted = connection.execute(
        sqlite_insert(seeds)
        .values(position=1, url="https://example.com/a")
        .on_conflict_do_nothing()
    )
    return _Seeded.NEW if inserted.rowcount else _Seeded.KNOWN


def test_a_unit_that_returns_an_enumeration_member_is_kept(temp_workspace: TempWorkspace) -> None:
    crawl = crawl_without_seeds(temp_workspace)

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        first = writer.run(_seeded)
        # The replay compares the member with itself, which an Enum compares by identity.
        replay_now(writer)
        again = writer.run(_seeded)

    assert (first, again, query(crawl.path, COUNT)) == (_Seeded.NEW, _Seeded.KNOWN, [(1,)])
