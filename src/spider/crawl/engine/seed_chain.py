"""A Seed's Redirect Chain, and the Scope while it is open (022-add-fetch-policy D3)."""

from spider.crawl.scope import ScopeDecision, ScopeRules
from spider.crawl.urls import NormalizedUrl
from spider.store.records import QueuedUrl
from spider.store.urls import SeedChainUrls


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
    ) -> tuple[ScopeRules | None, list[tuple[int, bool, bool]]]:
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
        return widened, [(url_id, d.is_internal, d.in_scope) for url_id, d in decided]
