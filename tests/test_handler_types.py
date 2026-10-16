"""Guard: a hook whose types disagree fails mypy where it is registered (020-add-crawl-core D9).

The check is mypy's, in the same run as the rest of the suite: strict mode reports an unused
ignore, so an ignore below fails the checks the day its mismatch is no longer caught.
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from spider.crawl.hooks import Hooks, UrlResult, handler


@dataclass(frozen=True, slots=True)
class PageRow:
    url_id: int


@dataclass(frozen=True, slots=True)
class CookieRow:
    url_id: int


def _page_rows(result: UrlResult) -> tuple[PageRow, ...]:
    return (PageRow(result.url_id),)


def _write_cookie(connection: Connection, row: CookieRow) -> None:
    del connection, row


def test_a_handler_and_a_writer_of_different_row_types_fail_mypy() -> None:
    # The mismatch on purpose, registered as default_hooks() registers: no R is both rows.
    hooks = Hooks(handlers=(handler("pages", _page_rows, _write_cookie),))  # type: ignore[misc]

    assert [registered.name for registered in hooks.handlers] == ["pages"]
