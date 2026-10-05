"""The transactional writer (015-add-crawl-store, crawl-store)."""

from collections.abc import Callable

from sqlalchemy import Connection, func, insert, select

from spider.store.schema import seeds
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace


def insert_seed(position: int, url: str) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        connection.execute(insert(seeds).values(position=position, url=url))

    return unit


def count_seeds(connection: Connection) -> int:
    return connection.execute(select(func.count()).select_from(seeds)).scalar_one()


def test_a_unit_sees_the_units_before_it(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace, seeds=[])

    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(insert_seed(1, "https://example.com/a"))
        count = writer.run(count_seeds)

    assert count == 1
