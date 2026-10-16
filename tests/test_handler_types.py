"""Guard: a handler and a writer of different row types fail mypy (020-add-crawl-core D9).

The check is mypy's, in the same run as the rest of the suite: strict mode reports an unused
ignore, so the ignore below fails the checks the day the mismatch is no longer caught.
"""

from dataclasses import dataclass

from sqlalchemy import Connection

from spider.crawl.hooks import Handler, UrlResult


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
    # The mismatch on purpose: no R is both a PageRow and a CookieRow.
    handler = Handler("pages", _page_rows, _write_cookie)  # type: ignore[misc]

    assert handler.name == "pages"
