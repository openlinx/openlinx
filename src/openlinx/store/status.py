"""Read the status of the selected Crawl in one Store snapshot."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, MultipleResultsFound, NoResultFound

from openlinx.store.crawls import crawl_summary
from openlinx.store.reading import invalid_crawl_file, reading_selected
from openlinx.store.records import CrawlFile, CrawlSummary, UrlCounts
from openlinx.store.schema import crawl
from openlinx.store.urls import url_counts

_COMPLETED_AT = select(crawl.c.completed_at)


@dataclass(frozen=True)
class CrawlStatus:
    summary: CrawlSummary
    completed_at: str | None
    counts: UrlCounts | None


def read_status(selected: CrawlFile) -> CrawlStatus:
    try:
        with reading_selected(selected) as connection:
            summary = crawl_summary()(connection)
            completed_at: str | None = connection.execute(_COMPLETED_AT).scalar_one()
            # A running Crawl will supply counts via its heartbeat, without scanning urls.
            counts = None if summary.state == "running" else url_counts()(connection)
    except (DBAPIError, NoResultFound, MultipleResultsFound) as error:
        raise invalid_crawl_file(selected.path) from error
    return CrawlStatus(summary, completed_at, counts)
