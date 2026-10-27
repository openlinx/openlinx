"""The warnings a Crawl gives, with their texts and details (020-add-crawl-core D10)."""

from collections.abc import Iterable

from spider.crawl.engine.context import CrawlContext
from spider.crawl.fetch.politeness import BLOCKING_RUN
from spider.crawl.references import DiscoveredLink
from spider.crawl.scope import ScopeRules, apex_seed_named_by_page
from spider.crawl.urls import NormalizedUrl, url_host, url_origin
from spider.naming import APP_NAME
from spider.output.codes import (
    MAX_URLS_REACHED,
    POSSIBLE_BLOCKING,
    ROBOTS_UNREACHABLE,
    SEED_BASE_MISMATCH,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from spider.output.diagnostics import Diagnostic
from spider.store.records import ParseError


def warn_of_the_url_limit(context: CrawlContext, limit: int) -> None:
    context.reporter.warn(
        Diagnostic.of(
            MAX_URLS_REACHED,
            f"The Crawl reached its limit of {limit} URL requests, so it stopped with URLs left "
            "queued.",
            # The command itself, as an agent runs it: twice the limit is one higher value.
            hint=f"{APP_NAME} resume --crawl {context.crawl_file.id} --max-urls {2 * limit}",
            details={"max_urls": limit},
        )
    )


def warn_of_an_unreachable_robots_txt(
    context: CrawlContext, url: NormalizedUrl, status_code: int | None
) -> None:
    origin = url_origin(url)
    answered = f"The robots.txt of {origin} answered {status_code}"
    if context.settings.ignore_robots:
        message = f"{answered}, so its URLs were requested without its rules."
        hint = "Run the Crawl again later to crawl the origin by its rules."
    else:
        message = f"{answered}, so none of its URLs was requested."
        hint = "Run the Crawl again later, or give --ignore-robots to crawl the origin anyway."
    # Once per host, by the warning log: every URL of the origin comes here (design D10).
    context.reporter.warn(
        Diagnostic.of(
            ROBOTS_UNREACHABLE,
            message,
            hint=hint,
            details={"origin": origin, "host": url_host(url), "status_code": status_code},
        )
    )


def warn_of_possible_blocking(context: CrawlContext, host: str) -> None:
    # Once per host, by the warning log (design D10).
    context.reporter.warn(
        Diagnostic.of(
            POSSIBLE_BLOCKING,
            f"{BLOCKING_RUN} responses in a row from {host} had status 403 or 429, so the "
            "host may be blocking the Crawl, which went on.",
            hint="Crawl the site again more slowly, with a lower --rate or --concurrency.",
            details={"host": host, "count": BLOCKING_RUN},
        )
    )


def warn_of_a_blocked_seed(context: CrawlContext, seed: NormalizedUrl) -> None:
    context.reporter.warn(
        Diagnostic.of(
            SEED_BLOCKED_BY_ROBOTS_TXT,
            f"robots.txt disallows the Seed {seed} for the robots user-agent token "
            f"{context.settings.robots_user_agent}, so it was not requested and nothing was "
            "crawled from it.",
            hint="Give --ignore-robots to crawl it anyway, or --robots-user-agent with the "
            "token the site allows.",
            details={"seed": seed},
        )
    )


def warn_of_seed_base_mismatch(
    context: CrawlContext,
    seed: NormalizedUrl,
    links: Iterable[DiscoveredLink],
    scope: ScopeRules,
) -> None:
    apex_seed = apex_seed_named_by_page(seed, links, scope)
    if apex_seed is not None:
        context.reporter.warn(
            Diagnostic.of(
                SEED_BASE_MISMATCH,
                f"The Seed {seed} names its apex host as the site: its Page links there by its "
                "canonical or by most of its hyperlinks, so the Crawl may miss most of the site.",
                hint=f"Give {apex_seed} as the Seed to crawl the site its Page names.",
                details={"seed": seed, "apex_seed": apex_seed},
            )
        )


def parse_failure(url: NormalizedUrl, parse_error: ParseError, message: str | None) -> str:
    if parse_error == "extractor_error":
        return (
            f"An extractor failed on {url} ({message}); the Page was recorded without its "
            "output, and its Links were followed."
        )
    detail = parse_error if message is None else f"{parse_error}: {message}"
    return (
        f"Preparing {url} gave nothing ({detail}); it was recorded unparsed, with only the "
        "Links of its headers."
    )
