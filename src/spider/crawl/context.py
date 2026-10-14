"""One context for a Crawl's dependencies (020-add-crawl-core D15)."""

import re
from dataclasses import dataclass

from spider.clock import Clock
from spider.crawl.fetcher import Fetcher
from spider.crawl.hooks import Hooks
from spider.crawl.pages import PageExecutor
from spider.crawl.scope import ScopeRules
from spider.crawl.settings import CrawlSettings
from spider.crawl.stop import StopSignal
from spider.crawl.warning_log import CrawlReporter
from spider.store.records import CrawlFile
from spider.store.writer import CrawlWriter


@dataclass(frozen=True, kw_only=True)
class CrawlContext:
    crawl_file: CrawlFile
    settings: CrawlSettings
    scope: ScopeRules
    # --strip-params, compiled once: the Seed, the engine and page preparation share it.
    strip_params: re.Pattern[str] | None
    clock: Clock
    reporter: CrawlReporter
    writer: CrawlWriter
    fetcher: Fetcher
    pages: PageExecutor
    hooks: Hooks
    stop: StopSignal
