"""Define the versioned Crawl summary shared by the CLI and reports."""

from typing import Literal

from msgspec import Struct

from openlinx.store.records import (
    CrawlMode,
    CrawlState,
    IssueType,
    Priority,
    RuleCategory,
    StopReason,
)

LinkMetrics = Literal["complete", "partial"]


class CrawlInfo(Struct, frozen=True, kw_only=True):
    """Recorded Crawl metadata and a preview of its Seeds."""

    id: str
    seeds: list[str]
    seed_count: int
    crawl_mode: CrawlMode
    state: CrawlState
    stop_reason: StopReason | None
    started_at: str
    completed_at: str | None
    section_crawl: bool
    link_metrics: LinkMetrics
    tool_version: str
    schema_version: int


class Totals(Struct, frozen=True, kw_only=True):
    """Crawl outcomes and the total size of the frontier."""

    encountered: int
    crawled: int
    urls: int
    internal_urls: int
    external_urls: int
    pages: int
    resources: int


class StatusClasses(Struct, frozen=True):
    internal: dict[str, int]
    external: dict[str, int]


class IndexabilityCount(Struct, frozen=True):
    status: str
    count: int


class Indexability(Struct, frozen=True):
    indexable: int
    non_indexable: int
    by_status: list[IndexabilityCount]


class ContentTypeCount(Struct, frozen=True):
    content_type: str | None
    count: int
    share_pct: float


class DepthCount(Struct, frozen=True):
    depth: int
    count: int


class CrawlDepth(Struct, frozen=True):
    partial: bool
    max: int | None
    distribution: list[DepthCount]


class TimeBucket(Struct, frozen=True):
    from_ms: int
    to_ms: int | None
    count: int


class ResponseTime(Struct, frozen=True, kw_only=True):
    """Response times in milliseconds, with nearest-rank percentiles."""

    count: int
    min: int | None
    mean: float | None
    p50: int | None
    p90: int | None
    p95: int | None
    p99: int | None
    max: int | None
    histogram: list[TimeBucket]


class HealthScore(Struct, frozen=True):
    score: int | None
    internal_pages: int | None
    affected_pages: int | None


class IssueBucket(Struct, frozen=True, kw_only=True):
    issue_type: IssueType
    priority: Priority
    issues: int
    affected_count: int


class TopIssue(Struct, frozen=True, kw_only=True):
    rule_id: str
    category: RuleCategory
    issue_type: IssueType
    priority: Priority
    affected_count: int
    description: str


class IssueSummary(Struct, frozen=True):
    total: int
    by_type_priority: list[IssueBucket]
    top: list[TopIssue]


class SummaryModel(Struct, frozen=True, kw_only=True):
    """The v1 summary JSON contract."""

    summary_version: Literal[1] = 1
    crawl: CrawlInfo
    segment: None = None
    totals: Totals
    status_classes: StatusClasses
    indexability: Indexability
    content_types: list[ContentTypeCount]
    crawl_depth: CrawlDepth
    response_time_ms: ResponseTime
    health_score: HealthScore
    issues: IssueSummary
    segments: list[None] = []
    unsegmented: None = None
