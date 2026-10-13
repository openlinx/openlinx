"""One context for a Crawl's dependencies (020-add-crawl-core D15)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from spider.clock import Clock
from spider.crawl.fetcher import Fetcher
from spider.output.reporter import Reporter
from spider.store.records import CrawlFile

if TYPE_CHECKING:
    from spider.store.writer import CrawlWriter


@dataclass(frozen=True, kw_only=True)
class CrawlContext:
    crawl_file: CrawlFile
    clock: Clock
    reporter: Reporter
    writer: "CrawlWriter"
    fetcher: Fetcher
