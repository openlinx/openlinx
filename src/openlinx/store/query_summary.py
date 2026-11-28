"""Summarise committed URL, Page and Issue rows in one read-only snapshot."""

from collections import Counter
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any, get_args

from sqlalchemy import Connection, case, func, literal, select

from openlinx.query.summary import (
    ContentTypeCount,
    CrawlDepth,
    CrawlInfo,
    DepthCount,
    HealthScore,
    Indexability,
    IndexabilityCount,
    IssueBucket,
    IssueSummary,
    ResponseTime,
    StatusClasses,
    SummaryModel,
    TimeBucket,
    TopIssue,
    Totals,
)
from openlinx.store.health import health_for_pages
from openlinx.store.issues import live_issue_affected_in
from openlinx.store.query import ordered_issues_in
from openlinx.store.reading import metadata_in
from openlinx.store.records import RESOURCE_LINK_TYPES, IssueType, Priority
from openlinx.store.rule_queries import RuleQuery
from openlinx.store.schema import links, pages, seeds, urls

_SEEDS = select(seeds.c.url).order_by(seeds.c.position).limit(10)
_SEED_COUNT = select(func.count()).select_from(seeds)
_INTERNAL = urls.c.is_internal == 1
_CRAWLED = urls.c.fetch_state.in_(("fetched", "error"))
_ROBOTS_BLOCKED = (urls.c.fetch_state == "skipped") & (
    urls.c.skip_reason == "blocked_by_robots_txt"
)
_OUTCOME = _CRAWLED | _ROBOTS_BLOCKED
_PAGE_COUNT = select(func.count()).select_from(pages)
_RESOURCES = (
    select(links.c.target_url_id)
    .where(
        links.c.type.in_(sorted(RESOURCE_LINK_TYPES)),
        ~select(pages.c.url_id).where(pages.c.url_id == links.c.target_url_id).exists(),
    )
    .distinct()
)
_RESOURCE_COUNT = select(func.count()).select_from(_RESOURCES.subquery())
_TOTALS = select(
    func.count(),
    func.count().filter(_CRAWLED),
    func.count().filter(_OUTCOME),
    func.count().filter(_OUTCOME, _INTERNAL),
    func.count().filter(_OUTCOME, ~_INTERNAL),
    _PAGE_COUNT.scalar_subquery(),
    _RESOURCE_COUNT.scalar_subquery(),
).select_from(urls)
_STATUS = urls.c.status_code
_RECORD_FAILED = urls.c.fetch_error == "record_failed"
_STATUS_RANGES = tuple(
    (f"{base // 100}xx", _STATUS.between(base, base + 99)) for base in (200, 300, 400, 500)
)
_STATUS_GROUPS = (
    *_STATUS_RANGES,
    ("other", _STATUS.is_not(None) & ~_STATUS.between(200, 599)),
    ("no_response", (urls.c.fetch_state == "error") & ~func.coalesce(_RECORD_FAILED, False)),
    ("record_failed", (urls.c.fetch_state == "error") & _RECORD_FAILED),
    ("blocked_by_robots_txt", _ROBOTS_BLOCKED),
)
_STATUS_CLASSES = select(
    urls.c.is_internal,
    *(func.count().filter(predicate) for _, predicate in _STATUS_GROUPS),
).group_by(urls.c.is_internal)
_INDEXABILITY = select(pages.c.indexability, pages.c.indexability_status, func.count()).group_by(
    pages.c.indexability, pages.c.indexability_status
)
_MEDIA_TYPE = func.lower(
    func.trim(
        func.substr(urls.c.content_type, 1, func.instr(urls.c.content_type + ";", ";") - 1),
        " \t",
    )
)
_INTERNAL_RESPONSE = _INTERNAL & _STATUS.is_not(None)
_CONTENT_TYPES = (
    select(_MEDIA_TYPE, func.count())
    .where(_INTERNAL_RESPONSE)
    .group_by(_MEDIA_TYPE)
    .order_by(_MEDIA_TYPE.is_(None), func.count().desc(), _MEDIA_TYPE)
)
_DEPTH = (
    select(urls.c.crawl_depth, func.count())
    .where(_INTERNAL, urls.c.crawl_depth.is_not(None))
    .group_by(urls.c.crawl_depth)
    .order_by(urls.c.crawl_depth)
)
_TIME = urls.c.response_time_ms
_TIMED = _INTERNAL_RESPONSE & _TIME.is_not(None)
_BOUNDS = (0, 100, 250, 500, 1000, 2000, 5000)
_HISTOGRAM = case(
    *((upper > _TIME, lower) for lower, upper in pairwise(_BOUNDS)),
    else_=literal(_BOUNDS[-1]),
)
_TIMINGS = select(func.count(), func.min(_TIME), func.avg(_TIME), func.max(_TIME)).where(_TIMED)
_BUCKET_COUNTS = select(_HISTOGRAM, func.count()).where(_TIMED).group_by(_HISTOGRAM)
_RANKED = (
    select(_TIME.label("duration"), func.row_number().over(order_by=_TIME).label("rank"))
    .where(_TIMED)
    .subquery()
)


def summary_in(
    connection: Connection, path: Path, catalogue: Sequence[RuleQuery], *, top: int
) -> SummaryModel:
    """Read the metadata and compute each summary section from the same snapshot."""
    metadata = metadata_in(connection)
    info = _crawl_info(connection, metadata)
    return SummaryModel(
        crawl=info,
        totals=_totals(connection),
        status_classes=_status_classes(connection),
        indexability=_indexability(connection),
        content_types=_content_types(connection),
        crawl_depth=_depth(connection, info.section_crawl),
        response_time_ms=_response_times(connection),
        health_score=_health(connection, metadata, catalogue),
        issues=_issues(ordered_issues_in(connection, path, catalogue), top),
    )


def _crawl_info(connection: Connection, metadata: dict[str, Any]) -> CrawlInfo:
    section = bool(metadata["section_crawl"])
    return CrawlInfo(
        id=metadata["id"],
        seeds=list(connection.scalars(_SEEDS)),
        seed_count=connection.execute(_SEED_COUNT).scalar_one(),
        crawl_mode=metadata["crawl_mode"],
        state=metadata["state"],
        stop_reason=metadata["stop_reason"],
        started_at=metadata["started_at"],
        completed_at=metadata["completed_at"],
        section_crawl=section,
        link_metrics="partial" if section else "complete",
        tool_version=metadata["tool_version"],
        schema_version=metadata["schema_version"],
    )


def _totals(connection: Connection) -> Totals:
    encountered, crawled, outcomes, internal, external, page_count, resource_count = (
        connection.execute(_TOTALS).one()
    )
    return Totals(
        encountered=encountered,
        crawled=crawled,
        urls=outcomes,
        internal_urls=internal,
        external_urls=external,
        pages=page_count,
        resources=resource_count,
    )


def _status_classes(connection: Connection) -> StatusClasses:
    keys = tuple(name for name, _ in _STATUS_GROUPS)
    empty = dict.fromkeys(keys, 0)
    counts = {
        bool(internal): dict(zip(keys, values, strict=True))
        for internal, *values in connection.execute(_STATUS_CLASSES)
    }
    return StatusClasses(counts.get(True, empty.copy()), counts.get(False, empty.copy()))


def _indexability(connection: Connection) -> Indexability:
    rows = connection.execute(_INDEXABILITY).all()
    non_indexable = [(status, count) for kind, status, count in rows if kind == "non_indexable"]
    by_status = [IndexabilityCount(status, count) for status, count in non_indexable if status]
    by_status.sort(key=lambda item: (-item.count, item.status))
    return Indexability(
        sum(count for kind, _, count in rows if kind == "indexable"),
        sum(count for _, count in non_indexable),
        by_status,
    )


def _content_types(connection: Connection) -> list[ContentTypeCount]:
    rows = connection.execute(_CONTENT_TYPES).all()
    total = sum(count for _, count in rows)
    return [ContentTypeCount(kind, count, round(100 * count / total, 2)) for kind, count in rows]


def _depth(connection: Connection, partial: bool) -> CrawlDepth:
    counts: dict[int, int] = dict(connection.execute(_DEPTH).all())
    if not counts:
        return CrawlDepth(partial, None, [])
    maximum = max(counts)
    return CrawlDepth(
        partial, maximum, [DepthCount(depth, counts.get(depth, 0)) for depth in range(maximum + 1)]
    )


def _response_times(connection: Connection) -> ResponseTime:
    count, minimum, mean, maximum = connection.execute(_TIMINGS).one()
    buckets: dict[int, int] = dict(connection.execute(_BUCKET_COUNTS).all())
    histogram = [
        TimeBucket(lower, upper, buckets.get(lower, 0))
        for lower, upper in zip(_BOUNDS, (*_BOUNDS[1:], None), strict=True)
    ]
    # Use integer arithmetic for ceil(percentile * count / 100).
    ranks = [(percentile * count + 99) // 100 for percentile in (50, 90, 95, 99)]
    times: dict[int, int] = {}
    if count:
        ranked = connection.execute(
            select(_RANKED.c.rank, _RANKED.c.duration).where(_RANKED.c.rank.in_(ranks))
        )
        times = dict(ranked.all())
    p50, p90, p95, p99 = (times.get(rank) for rank in ranks)
    return ResponseTime(
        count=count,
        min=minimum,
        mean=round(mean, 1) if mean is not None else None,
        p50=p50,
        p90=p90,
        p95=p95,
        p99=p99,
        max=maximum,
        histogram=histogram,
    )


def _health(
    connection: Connection, metadata: dict[str, Any], catalogue: Sequence[RuleQuery]
) -> HealthScore:
    if metadata["state"] in ("completed", "stopped"):
        return HealthScore(
            metadata.get("health_score"),
            metadata.get("health_internal_page_count"),
            metadata.get("health_affected_page_count"),
        )
    internal_ids = select(pages.c.url_id).join(urls, urls.c.id == pages.c.url_id).where(_INTERNAL)
    health = health_for_pages(
        connection, page_ids=internal_ids, affected=live_issue_affected_in(connection, catalogue)
    )
    return HealthScore(health.score, health.internal_pages, health.affected_pages)


def _issues(ordered: list[dict[str, Any]], top: int) -> IssueSummary:
    counts: Counter[tuple[IssueType, Priority]] = Counter()
    affected: Counter[tuple[IssueType, Priority]] = Counter()
    for issue in ordered:
        key = (issue["issue_type"], issue["priority"])
        counts[key] += 1
        affected[key] += issue["affected_count"]
    cells = [
        IssueBucket(
            issue_type=kind,
            priority=priority,
            issues=counts[kind, priority],
            affected_count=affected[kind, priority],
        )
        for kind in get_args(IssueType.__value__)
        for priority in get_args(Priority.__value__)
    ]
    return IssueSummary(len(ordered), cells, [TopIssue(**issue) for issue in ordered[:top]])
