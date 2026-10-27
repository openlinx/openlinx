"""A Seed's Redirect Chain, and the Scope while it is open (022-add-fetch-policy D3)."""

from spider.crawl.engine.context import CrawlContext
from spider.crawl.engine.crawl_warnings import seed_redirected_out_of_scope
from spider.crawl.pages.preparation import PageSettings
from spider.crawl.scope import ScopeDecision, ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.crawls import record_scope
from spider.store.records import QueuedUrl, Reclassified
from spider.store.urls import SeedChainUrls, reclassify_urls, seed_chain_urls


class SeedChain:
    """Open from the start of a run until the URL that the Seed's Redirect Chain ends on is
    decided. Until then a URL of the chain is decided with a provisional Scope, which also
    admits the hosts of the Seed's registrable domain: a www Seed's apex target would else be
    External and checked, never followed. No other URL is decided with it, since a chain is
    3xx responses and no Link exists before it ends."""

    def __init__(self, scope: ScopeRules, seed: NormalizedUrl) -> None:
        self.scope = scope
        self.seed = seed
        self._provisional = scope.admitting_the_domain_of(seed)
        self.is_open = True

    def holds(self, queued: QueuedUrl) -> bool:
        """Whether `queued` is a URL of the open chain: a chain is 3xx responses at depth 0."""
        return self.is_open and queued.crawl_depth == 0

    def decide(self, url: NormalizedUrl, *, in_chain: bool) -> ScopeDecision:
        rules = self._provisional if self.is_open and in_chain else self.scope
        return rules.decide(url)

    def close(
        self, chain: SeedChainUrls, *, responded: bool
    ) -> tuple[ScopeRules | None, list[Reclassified]]:
        """Closes the chain once, on the URL it ended on: the Scope it widens to, when the
        chain ended with a response on another host of the Seed's registrable domain, and
        each URL of the chain decided again against the Scope it ended in."""
        if not self.is_open:
            raise RuntimeError(f"the Seed's Redirect Chain is already closed, at {chain[-1][1]}")
        self.is_open = False
        final_url = chain[-1][1]
        widened = self.scope.widened_to(final_url) if responded else None
        if widened is not None:
            self.scope = widened
        decided = [(url_id, self.scope.decide(url)) for url_id, url in chain]
        return widened, [
            Reclassified(url_id=url_id, is_internal=d.is_internal, in_scope=d.in_scope)
            for url_id, d in decided
        ]


async def close_seed_chain(context: CrawlContext, chain: SeedChain, *, responded: bool) -> None:
    """Closes the Seed's Redirect Chain on the URL it ended on: its URLs are decided again
    against the Scope it ended in, which the Crawl records when it widened, and page
    preparation starts with that Scope (022-add-fetch-policy D3)."""
    urls = await context.writer.run_async(
        seed_chain_urls(chain.seed, context.settings.max_redirects)
    )
    final_url = urls[-1][1]
    if chain.scope.is_out_of_scope(final_url):
        context.reporter.warn(seed_redirected_out_of_scope(chain.seed, final_url))
    widened, decisions = chain.close(urls, responded=responded)
    await context.writer.run_async(reclassify_urls(decisions))
    if widened is not None:
        await context.writer.run_async(record_scope(widened.to_json()))
    await context.pages.start(
        PageSettings(
            scope=chain.scope,
            extractors=context.hooks.extractors,
            robots_token=context.settings.robots_user_agent,
            follow_nofollow=context.settings.follow_nofollow,
            strip_params=context.strip_params,
        )
    )
