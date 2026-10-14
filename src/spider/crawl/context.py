"""One context for a Crawl's dependencies (020-add-crawl-core D15)."""

from dataclasses import dataclass

from spider.clock import Clock
from spider.crawl.fetcher import Fetcher
from spider.crawl.hooks import Hooks
from spider.crawl.pages import PageExecutor
from spider.crawl.scope import ScopeRules
from spider.crawl.stop import StopSignal
from spider.crawl.warning_log import WarningLog
from spider.store.records import CrawlFile
from spider.store.writer import CrawlWriter


@dataclass(frozen=True, kw_only=True)
class CrawlContext:
    crawl_file: CrawlFile
    scope: ScopeRules
    clock: Clock
    reporter: WarningLog
    writer: CrawlWriter
    fetcher: Fetcher
    pages: PageExecutor
    hooks: Hooks
    stop: StopSignal
