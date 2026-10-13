"""The engine: requests URLs and submits each one's unit (020-add-crawl-core D1, D2)."""

from spider.crawl.context import CrawlContext
from spider.crawl.fetcher import Request
from spider.crawl.urls import NormalizedUrl, url_host
from spider.store.urls import record_fetched, record_seed


async def run_crawl(context: CrawlContext, seed: NormalizedUrl) -> None:
    seed_id = await context.writer.run_async(record_seed(seed, url_host(seed)))
    response = await context.fetcher.fetch(Request(seed))
    # The URL's task ends here; its outcome arrives at the commit (design D2).
    await context.writer.submit_async(record_fetched(seed_id, response.status_code))
