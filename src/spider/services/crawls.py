"""Creating a Crawl, which the Crawl service builds on (design D9 of 015-add-crawl-store)."""

import secrets

from spider.clock import Clock
from spider.output.reporter import Reporter
from spider.store.ids import Choice
from spider.store.records import CrawlFile, NewCrawl


def create_crawl(
    request: NewCrawl, clock: Clock, reporter: Reporter, choice: Choice = secrets.choice
) -> CrawlFile:
    # Imported here: sqlalchemy stays off the CLI's startup path (design D9).
    from spider.store.crawls import create_crawl_file

    # Read once: the id and crawl.started_at must name the same instant.
    return create_crawl_file(request, clock.now(), choice)
