"""The warnings a Crawl gives, with their texts and details; the warning log keeps each once
per what its code names (020-add-crawl-core D10)."""

from collections.abc import Iterable, Sequence

from spider.crawl.fetch.politeness import BLOCKING_RUN
from spider.crawl.references import DiscoveredLink
from spider.crawl.scope import ScopeRules, apex_seed_named_by_page
from spider.crawl.urls import NormalizedUrl, url_host, url_origin
from spider.naming import APP_NAME
from spider.output.codes import (
    HANDLER_FAILED,
    MAX_URLS_REACHED,
    NETWORK_PAUSED,
    PARSE_FAILED,
    POSSIBLE_BLOCKING,
    RECORD_FAILED,
    ROBOTS_REDIRECT_FAILED,
    ROBOTS_UNREACHABLE,
    SEED_BASE_MISMATCH,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from spider.output.diagnostics import Diagnostic
from spider.store.records import FetchError, ParseError


def url_limit_reached(crawl_id: str, limit: int) -> Diagnostic:
    return Diagnostic.of(
        MAX_URLS_REACHED,
        f"The Crawl reached its limit of {limit} URL requests, so it stopped with URLs left "
        "queued.",
        # The command itself, as an agent runs it: twice the limit is one higher value.
        hint=f"{APP_NAME} resume --crawl {crawl_id} --max-urls {2 * limit}",
        details={"max_urls": limit},
    )


def unreachable_robots_txt(
    url: NormalizedUrl, status_code: int | None, *, ignore_robots: bool
) -> Diagnostic:
    origin = url_origin(url)
    answered = f"The robots.txt of {origin} answered {status_code}"
    if ignore_robots:
        message = f"{answered}, so its URLs were requested without its rules."
        hint = "Run the Crawl again later to crawl the origin by its rules."
    else:
        message = f"{answered}, so none of its URLs was requested."
        hint = "Run the Crawl again later, or give --ignore-robots to crawl the origin anyway."
    return Diagnostic.of(
        ROBOTS_UNREACHABLE,
        message,
        hint=hint,
        details={"origin": origin, "host": url_host(url), "status_code": status_code},
    )


def robots_redirect_failure(
    url: NormalizedUrl, target: NormalizedUrl, fetch_error: FetchError
) -> Diagnostic:
    origin = url_origin(url)
    return Diagnostic.of(
        ROBOTS_REDIRECT_FAILED,
        f"The robots.txt of {origin} redirected to {target}, which got no HTTP response "
        f"({fetch_error}), so robots.txt counts as missing and every URL of the origin was "
        "allowed.",
        hint="Fix the robots.txt redirect of the origin, then run the Crawl again.",
        details={
            "origin": origin,
            "host": url_host(url),
            "target": target,
            "fetch_error": fetch_error,
        },
    )


def possible_blocking(host: str) -> Diagnostic:
    return Diagnostic.of(
        POSSIBLE_BLOCKING,
        f"{BLOCKING_RUN} responses in a row from {host} had status 403 or 429, so the "
        "host may be blocking the Crawl, which went on.",
        hint="Crawl the site again more slowly, with a lower --rate or --concurrency.",
        details={"host": host, "count": BLOCKING_RUN},
    )


def blocked_seed(seed: NormalizedUrl, robots_token: str) -> Diagnostic:
    return Diagnostic.of(
        SEED_BLOCKED_BY_ROBOTS_TXT,
        f"robots.txt disallows the Seed {seed} for the robots user-agent token "
        f"{robots_token}, so it was not requested and nothing was crawled from it.",
        hint="Give --ignore-robots to crawl it anyway, or --robots-user-agent with the "
        "token the site allows.",
        details={"seed": seed},
    )


def seed_base_mismatch(
    seed: NormalizedUrl, links: Iterable[DiscoveredLink], scope: ScopeRules
) -> Diagnostic | None:
    apex_seed = apex_seed_named_by_page(seed, links, scope)
    if apex_seed is None:
        return None
    return Diagnostic.of(
        SEED_BASE_MISMATCH,
        f"The Seed {seed} names its apex host as the site: its Page links there by its "
        "canonical or by most of its hyperlinks, so the Crawl may miss most of the site.",
        hint=f"Give {apex_seed} as the Seed to crawl the site its Page names.",
        details={"seed": seed, "apex_seed": apex_seed},
    )


def handler_failure(url: NormalizedUrl, failed: Sequence[tuple[str, BaseException]]) -> Diagnostic:
    names = [f"{name} ({type(error).__name__})" for name, error in failed]
    if len(names) == 1:
        message = f"The handler {names[0]} raised on {url}; the URL was recorded without its rows."
    else:
        listed = ", ".join(names[:-1]) + f" and {names[-1]}"
        message = f"The handlers {listed} raised on {url}; the URL was recorded without their rows."
    return Diagnostic.of(HANDLER_FAILED, message)


def parse_failure(url: NormalizedUrl, parse_error: ParseError, message: str | None) -> Diagnostic:
    if parse_error == "extractor_error":
        return Diagnostic.of(
            PARSE_FAILED,
            f"An extractor failed on {url} ({message}); the Page was recorded without its "
            "output, and its Links were followed.",
        )
    detail = parse_error if message is None else f"{parse_error}: {message}"
    return Diagnostic.of(
        PARSE_FAILED,
        f"Preparing {url} gave nothing ({detail}); it was recorded unparsed, with only the "
        "Links of its headers.",
    )


def network_paused(seed: NormalizedUrl) -> Diagnostic:
    return Diagnostic.of(
        NETWORK_PAUSED,
        "Internal requests in a row got no HTTP response, so the Crawl paused and probed its "
        f"Seed {seed} until it answered; the URLs whose requests failed are kept as errors, or "
        "requested again when the network itself was down.",
    )


def record_failure(url: NormalizedUrl, error: BaseException) -> Diagnostic:
    return Diagnostic.of(
        RECORD_FAILED,
        f"Recording {url} failed ({type(error).__name__}), so it was recorded as an error, "
        "without the URLs found on it and its handlers' rows.",
    )
