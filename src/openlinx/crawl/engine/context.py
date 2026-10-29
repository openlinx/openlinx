"""One context for a Crawl's dependencies (020-add-crawl-core D15)."""

import re
from dataclasses import dataclass

from openlinx.clock import Clock
from openlinx.crawl.engine.hooks import Hooks
from openlinx.crawl.engine.stop import StopSignal
from openlinx.crawl.engine.warning_log import WarningLog
from openlinx.crawl.fetch.fetcher import Fetcher
from openlinx.crawl.pages.preparation import PageExecutor
from openlinx.crawl.scope import ScopeRules
from openlinx.crawl.settings import CrawlSettings
from openlinx.store.records import CrawlFile
from openlinx.store.writer import CrawlWriter


@dataclass(frozen=True, kw_only=True)
class CrawlContext:
    crawl_file: CrawlFile
    settings: CrawlSettings
    scope: ScopeRules
    # --strip-params, compiled once: the Seed, the engine and page preparation share it.
    strip_params: re.Pattern[str] | None
    clock: Clock
    warnings: WarningLog
    writer: CrawlWriter
    fetcher: Fetcher
    pages: PageExecutor
    hooks: Hooks
    stop: StopSignal
