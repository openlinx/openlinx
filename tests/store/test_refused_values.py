"""The file refuses bad values (design D2 and D3 of 018-add-schema-conventions, crawl-store)."""

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from spider.store.schema import crawl
from spider.store.writer import CrawlWriter
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl, query
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


def test_an_unknown_enumeration_value_is_refused(temp_workspace: TempWorkspace) -> None:
    created = create_any_crawl(temp_workspace)

    with (
        CrawlWriter(created.path, FakeClock()) as writer,
        pytest.raises(IntegrityError, match=r"CHECK constraint failed: crawl_state_values"),
    ):
        writer.run(executing(update(crawl).values(state="paused")))

    assert query(created.path, "SELECT state FROM crawl") == [("running",)]
