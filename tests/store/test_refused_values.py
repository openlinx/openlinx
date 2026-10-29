"""The file refuses bad values (018-add-schema-conventions, crawl-store)."""

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from openlinx.store.schema import crawl
from openlinx.store.writer import CrawlWriter
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


def test_a_flag_outside_0_and_1_is_refused(temp_workspace: TempWorkspace) -> None:
    created = create_any_crawl(temp_workspace)

    with (
        CrawlWriter(created.path, FakeClock()) as writer,
        pytest.raises(IntegrityError, match=r"CHECK constraint failed: crawl_section_crawl_flag"),
    ):
        writer.run(executing(update(crawl).values(section_crawl=2)))

    assert query(created.path, "SELECT section_crawl FROM crawl") == [(0,)]


def test_a_value_of_another_type_is_refused(temp_workspace: TempWorkspace) -> None:
    created = create_any_crawl(temp_workspace)

    with (
        CrawlWriter(created.path, FakeClock()) as writer,
        pytest.raises(IntegrityError, match=r"cannot store TEXT value in INTEGER column"),
    ):
        writer.run(executing(update(crawl).values(schema_version="first")))

    assert query(created.path, "SELECT schema_version FROM crawl") == [(1,)]
