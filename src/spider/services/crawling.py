"""The Crawl Service: a foreground Spider-mode Crawl (020-add-crawl-core D11, D15)."""

from collections.abc import Mapping
from dataclasses import dataclass

from spider.crawl.urls import InvalidUrl, InvalidUrlReason, NormalizedUrl, parse_seed
from spider.output.codes import INVALID_URL
from spider.output.diagnostics import SpiderError

_SEED_PROBLEMS: Mapping[InvalidUrlReason, str] = {
    "malformed": "is not a valid URL",
    "unsupported_scheme": "is not an http or https URL",
    "missing_host": "has no host",
    "invalid_host": "has a host that is not valid",
}


@dataclass(frozen=True)
class CrawlRequest:
    seed: str


@dataclass(frozen=True)
class CrawlPlan:
    seed: NormalizedUrl


def plan_crawl(request: CrawlRequest) -> CrawlPlan:
    """Validation and config resolution, before anything is created (design D11)."""
    seed = parse_seed(request.seed)
    if isinstance(seed, InvalidUrl):
        raise _invalid_seed(request.seed, seed.reason)
    return CrawlPlan(seed)


def _invalid_seed(text: str, reason: InvalidUrlReason) -> SpiderError:
    details = {"reason": reason}
    if reason == "userinfo":
        # Never echoed: the user name and password would reach logs (design D13).
        return SpiderError(
            INVALID_URL,
            "The Seed holds a user name or password, which a crawled URL must not hold.",
            hint="Give the URL without them; --auth, planned for v0.2, will send credentials.",
            details=details,
        )
    return SpiderError(
        INVALID_URL,
        f"The Seed {text} {_SEED_PROBLEMS[reason]}.",
        hint="Give an http or https URL, or a host such as site.test, which gets https://.",
        details=details,
    )
