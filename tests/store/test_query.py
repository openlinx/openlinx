"""The store's reads of the query Commands (050-add-query-and-segments D14; seam 2)."""

from spider.rules.registry import RULES
from spider.store.query import affected_url_page, ordered_issues, recorded_rule
from spider.store.reading import read_metadata, reading
from spider.store.records import IssueFilters
from tests.support.crawl_store import crawl_store
from tests.support.workspace import TempWorkspace


def test_the_store_hands_out_dicts_with_plain_str_keys(temp_workspace: TempWorkspace) -> None:
    crawl_file = crawl_store(
        temp_workspace, statuses={"https://example.com/gone": 404}, completed=True
    )

    with reading(crawl_file) as connection:
        read = [
            *ordered_issues(connection, RULES, IssueFilters()),
            *affected_url_page(connection, "internal-4xx", RULES, after=None, limit=10)[1],
            recorded_rule(connection, "internal-4xx"),
        ]
    read.append(read_metadata(crawl_file))

    # Compared by type: sqlalchemy's quoted_name equals the str it names, which orjson refuses.
    assert {type(key) for found in read for key in found} == {str}
