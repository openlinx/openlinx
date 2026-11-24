"""Verify the fetch outcome and Page data recorded for every URL on the synthetic site."""

from pathlib import Path

from openlinx.store.reading import reading
from tests.fixture_site.synthetic.site import (
    OUTCOMES,
    PARSED,
    Fault,
    SyntheticSite,
    page_number,
    page_path,
)

# The fixture's checked Resources are non-HTML. Unfollowed Links have no response.
_SHARED_OUTCOMES = {
    "resource": ("fetched", None, None, 200, 0, None),
    "missing": ("fetched", None, None, 404, 0, None),
    "not_followed": ("skipped", None, "link_type_not_followed", None, 0, None),
}
_COUNT_KEYS = {"resource": "resources", "missing": "missing", "not_followed": "not_followed"}
_OUTCOME_FIELDS = (
    "fetch_state",
    "fetch_error",
    "skip_reason",
    "status_code",
    "parsed",
    "parse_error",
)


def accounted_urls(
    crawl_file: Path, site: SyntheticSite, origin: str
) -> tuple[dict[str, int], int]:
    """Check every recorded URL against the seeded fixture; return the verified counts."""
    counts = dict.fromkeys(("pages", *_COUNT_KEYS.values()), 0)
    # The pool sizes are bounded. urls.url is unique, so N canonical Pages prove full coverage
    # without retaining a URL per Page in the measuring process.
    page_rows = 0
    shared = {origin + pool.url(index): pool.kind for pool, index in site.shared_urls()}
    with reading(crawl_file) as connection:
        state: str = connection.exec_driver_sql("SELECT state FROM crawl").scalar_one()
        if state != "completed":
            raise ValueError(f"Crawl ended {state}, expected completed")
        rows = connection.exec_driver_sql(
            "SELECT urls.url, pages.url_id, urls.fetch_state, urls.fetch_error, urls.skip_reason, "
            "urls.status_code, urls.parsed, urls.parse_error FROM urls "
            "LEFT JOIN pages ON pages.url_id = urls.id"
        )
        for url, page_id, *outcome in rows:
            path = url.removeprefix(origin)
            number = page_number(path, site.pages)
            if number is not None and url == origin + page_path(number):
                fault = site.fault(number)
                # The site's injected 500 has an empty body and no content type.
                has_html = fault is not Fault.SERVER_ERROR
                expected = PARSED if fault is None else OUTCOMES[fault]
                wanted = tuple(expected[field] for field in _OUTCOME_FIELDS)
                key = "pages"
            else:
                kind = shared.pop(url, None)
                if kind is None:
                    raise ValueError(f"Unexpected URL in the crawl file: {url}")
                has_html = False
                wanted = _SHARED_OUTCOMES[kind]
                key = _COUNT_KEYS[kind]
            if (page_id is not None) != has_html:
                raise ValueError(f"Unexpected Page row presence for {url}: expected {has_html}")
            page_rows += int(page_id is not None)
            if tuple(outcome) != wanted:
                raise ValueError(
                    f"Unexpected outcome for {url}: got {tuple(outcome)}, expected {wanted}"
                )
            counts[key] += 1
    if counts["pages"] != site.pages:
        raise ValueError(
            f"Found {counts['pages']} of {site.pages} requested Pages in the crawl file"
        )
    if shared:
        raise ValueError(f"Missing {len(shared)} shared URLs, including {next(iter(shared))}")
    return {**counts, "total": sum(counts.values())}, page_rows
