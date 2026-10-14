"""The synthetic Page model against page preparation (design D6 of 026-add-parse-pool)."""

import multiprocessing
from collections.abc import Callable
from datetime import UTC, datetime

from spider.crawl.directives import RobotsDirectives
from spider.crawl.fetcher import FetchResult
from spider.crawl.pages import PageSettings, PreparedPage, prepare_page, response_links
from spider.crawl.scope import ScopeRules, scope_rules
from spider.crawl.urls import NormalizedUrl
from tests.fixture_site.routes import Bytes
from tests.fixture_site.synthetic.preparation import (
    END_WORKER_EXIT,
    END_WORKER_EXTRACTOR,
    Continued,
    prepared_page,
)
from tests.fixture_site.synthetic.site import (
    LOSES_LINKS,
    OUTCOMES,
    REFRESH_EVERY,
    Fault,
    SyntheticSite,
    page_path,
)

BASE = "http://127.0.0.1:8000"
PREPARED = (
    Fault.INVALID_UTF8,
    Fault.WRONG_CHARSET,
    Fault.UNKNOWN_CHARSET,
    Fault.MALFORMED_HTML,
    Fault.SLOW,
    Fault.NO_TITLE,
    Fault.NO_H1,
)
SITE = SyntheticSite(
    seed=11,
    pages=3_000,
    shares={
        **dict.fromkeys(PREPARED, 0.1),
        Fault.NESTED_DIVS: 0.05,
        Fault.ENDS_WORKER: 0.05,
        Fault.SERVER_ERROR: 0.05,
    },
)
SCOPE = scope_rules(NormalizedUrl(f"{BASE}/"))
SETTINGS = PageSettings(SCOPE)


def first(predicate: Callable[[int], bool]) -> int:
    return next(n for n in range(SITE.pages) if predicate(n))


def with_fault(fault: Fault) -> int:
    return first(lambda n: SITE.fault(n) is fault)


def samples() -> dict[str, int]:
    """A Page of every kind: the root, an inner Page, a leaf, both refreshes, each fault."""
    clean = {n for n in range(1, SITE.pages) if SITE.fault(n) is None}
    return {
        "root": 0,
        "inner": first(lambda n: n in clean and bool(SITE.children(n))),
        "leaf": first(lambda n: n in clean and not SITE.children(n)),
        "meta_refresh": first(lambda n: n in clean and n % REFRESH_EVERY == 1),
        "http_refresh": first(lambda n: n in clean and n % REFRESH_EVERY == 2),
        **{fault.value: with_fault(fault) for fault in PREPARED},
    }


def model_response(n: int) -> FetchResult:
    """What the benchmark's direct mode fetches: the headers without the body."""
    return FetchResult(
        status_code=200,
        headers=(("Content-Type", "text/html"), *SITE.response_headers(n)),
        body=b"",
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=0,
    )


def response(n: int) -> FetchResult:
    route = SITE.route(page_path(n))
    assert isinstance(route, Bytes)
    return FetchResult(
        status_code=200,
        headers=(("Content-Type", route.content_type or ""), *route.headers),
        body=route.data,
        fetched_at=datetime(2026, 10, 14, tzinfo=UTC),
        response_time_ms=0,
    )


def projected(
    n: int, response: FetchResult, page: PreparedPage
) -> tuple[list[tuple[object, ...]], RobotsDirectives]:
    # As the engine takes them: the response's header Links, then the document's.
    links: list[tuple[object, ...]] = [
        (link.target, link.type, link.element, link.attribute, link.declared_in, link.ordinal)
        for link in (*response_links(url(n), response, SCOPE), *page.document_links)
    ]
    return (links, page.directives)


def url(n: int) -> NormalizedUrl:
    return NormalizedUrl(BASE + page_path(n))


def test_the_page_model_is_what_preparing_the_page_gives() -> None:
    kinds = samples()

    prepared = {
        kind: projected(n, model_response(n), prepared_page(SITE, url(n), SETTINGS))
        for kind, n in kinds.items()
    }
    parsed = {
        kind: projected(n, response(n), prepare_page(url(n), response(n), SETTINGS))
        for kind, n in kinds.items()
    }

    assert prepared == parsed
    assert all(len(links) > 350 for links, _ in parsed.values())


def test_a_page_whose_links_are_lost_is_prepared_with_its_expected_failure() -> None:
    prepared = {
        fault: prepared_page(SITE, url(with_fault(fault)), SETTINGS)
        for fault in LOSES_LINKS
        # The others never reach preparation: their response is a 500 or a reset.
        if OUTCOMES[fault]["status_code"] == 200
    }

    assert {fault: (page.document_links, page.parse_error) for fault, page in prepared.items()} == {
        Fault.NESTED_DIVS: ((), OUTCOMES[Fault.NESTED_DIVS]["parse_error"]),
        Fault.ENDS_WORKER: ((), OUTCOMES[Fault.ENDS_WORKER]["parse_error"]),
    }


def _prepare_in_child(n: int, scope: ScopeRules) -> None:
    prepare_page(url(n), response(n), PageSettings(scope, (END_WORKER_EXTRACTOR,)))


def test_the_end_worker_extractor_ends_its_process_on_the_marked_page_only() -> None:
    marked = with_fault(Fault.ENDS_WORKER)
    spawn = multiprocessing.get_context("spawn")
    child = spawn.Process(target=_prepare_in_child, args=(marked, SCOPE))
    child.start()
    child.join(60)

    clean = prepare_page(url(0), response(0), PageSettings(SCOPE, (END_WORKER_EXTRACTOR,)))

    assert (child.exitcode, clean.outputs, clean.parse_error) == (
        END_WORKER_EXIT,
        ((END_WORKER_EXTRACTOR.name, Continued()),),
        None,
    )
