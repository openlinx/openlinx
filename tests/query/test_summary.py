"""Summarise committed Crawl rows through the Query Service."""

import gzip
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import msgspec
import pytest
from sqlalchemy import update

from openlinx.clock import SystemClock
from openlinx.crawl.urls import NormalizedUrl
from openlinx.query.summary import DepthCount, HealthScore, SummaryModel
from openlinx.rules.registry import RULES
from openlinx.services.query import QueryRequest, summary
from openlinx.store.crawls import record_state
from openlinx.store.records import ErroredUrl, FetchedUrl, Provenance, Reclassified, SkippedUrl
from openlinx.store.schema import crawl
from openlinx.store.urls import (
    reclassify_urls,
    record_error,
    record_fetched,
    record_seed,
    record_skipped,
    record_unwritten,
)
from openlinx.store.writer import CrawlWriter
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.cli import run_cli
from tests.support.clock import FakeClock
from tests.support.crawl_store import crawl_store
from tests.support.crawling import crawl_result
from tests.support.crawls import STARTED_AT, create_any_crawl, create_crawl_at, sha256_of
from tests.support.crawls import query as read_store
from tests.support.workspace import TempWorkspace
from tests.support.writer import executing


def test_whole_site_crawl(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(temp_workspace)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=5)))
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    before = sha256_of(crawl.path)

    info = summary(request).crawl

    assert info.id == crawl.id
    assert info.crawl_mode == "spider"
    assert info.seeds == ["https://example.com/"]
    assert info.seed_count == 1
    assert info.state == "completed"
    assert info.started_at == "2026-09-27T14:03:12.345Z"
    assert info.completed_at == "2026-09-27T14:03:17.345Z"
    assert info.stop_reason is None
    assert info.section_crawl is False
    assert info.link_metrics == "complete"
    assert sha256_of(crawl.path) == before


def test_stored_list_crawl_with_many_seeds(temp_workspace: TempWorkspace) -> None:
    create_any_crawl(
        temp_workspace,
        crawl_mode="list",
        seeds=[f"https://example.com/p{i}" for i in range(1, 26)],
    )
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    info = summary(request).crawl

    assert info.crawl_mode == "list"
    assert info.state == "running"
    assert info.completed_at is None
    assert info.seed_count == 25
    assert info.seeds == [
        "https://example.com/p1",
        "https://example.com/p2",
        "https://example.com/p3",
        "https://example.com/p4",
        "https://example.com/p5",
        "https://example.com/p6",
        "https://example.com/p7",
        "https://example.com/p8",
        "https://example.com/p9",
        "https://example.com/p10",
    ]


@pytest.fixture
def stopped_section_summary(temp_workspace: TempWorkspace) -> SummaryModel:
    crawl = create_any_crawl(temp_workspace, section_crawl=True)
    with CrawlWriter(crawl.path, FakeClock()) as writer:
        for index, duration in enumerate((50, 100, 150, 200, 300, 450, 800, 1200, 2500, 6000)):
            addr = NormalizedUrl(f"https://example.com/{index}")
            url_id = writer.run(record_seed(addr, is_internal=True, in_scope=True))
            writer.run(
                record_fetched(
                    FetchedUrl(
                        url_id=url_id,
                        provenance=Provenance(
                            crawl_depth=0,
                            discovered_via="seed",
                            found_on_url_id=None,
                        ),
                        status_code=200,
                        content_type=(
                            "text/html; charset=utf-8",
                            "Text/HTML\t; charset=utf-8",
                            "image/png",
                            None,
                        )[index % 4],
                        fetched_at=STARTED_AT,
                        response_time_ms=duration,
                        parsed=False,
                        attempt_count=1,
                        redirect=None,
                    )
                )
            )
        writer.run(record_state("stopped", STARTED_AT + timedelta(seconds=1), "interrupt"))
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    return summary(request)


def test_interrupted_crawl_metadata(stopped_section_summary: SummaryModel) -> None:
    crawl = stopped_section_summary.crawl
    assert (crawl.state, crawl.stop_reason, crawl.completed_at) == (
        "stopped",
        "interrupt",
        None,
    )


def test_section_crawl_labels_partial_metrics(stopped_section_summary: SummaryModel) -> None:
    assert stopped_section_summary.crawl.section_crawl is True
    assert stopped_section_summary.crawl.link_metrics == "partial"
    assert stopped_section_summary.crawl_depth.partial is True


def test_content_types_are_grouped_by_normalised_media_type(
    stopped_section_summary: SummaryModel,
) -> None:
    content_types = stopped_section_summary.content_types
    assert [(c.content_type, c.count, c.share_pct) for c in content_types] == [
        ("text/html", 6, 60.0),
        ("image/png", 2, 20.0),
        (None, 2, 20.0),
    ]


def test_response_time_uses_nearest_rank_percentiles(stopped_section_summary: SummaryModel) -> None:
    time = stopped_section_summary.response_time_ms
    assert (time.count, time.min, time.mean, time.p50, time.p90, time.p95, time.p99, time.max) == (
        10,
        50,
        1175.0,
        300,
        2500,
        6000,
        6000,
        6000,
    )


def test_response_time_histogram(stopped_section_summary: SummaryModel) -> None:
    histogram = stopped_section_summary.response_time_ms.histogram
    assert [bucket.count for bucket in histogram] == [1, 3, 2, 1, 1, 1, 1]


def test_response_totals_count_every_fetched_seed(stopped_section_summary: SummaryModel) -> None:
    totals = stopped_section_summary.totals
    assert totals.encountered == totals.crawled == totals.urls == 10


def test_success_status_counts_every_fetched_seed(stopped_section_summary: SummaryModel) -> None:
    assert stopped_section_summary.status_classes.internal["2xx"] == 10


def test_crawl_depth_keeps_empty_internal_buckets(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    site = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/a">A</a><a href="/b">B</a>'),
                "/a": Page(body='<a href="/bridge">Bridge</a>'),
                "/b": Page(body="<title>B</title>"),
                "/bridge": Page(body='<a href="/c">C</a>'),
                "/c": Page(body="<title>C</title>"),
            }
        )
    )
    crawled = crawl_result(site.url("/"))
    assert crawled.summary.state == "completed"
    [(bridge_id,)] = read_store(
        crawled.crawl_file, "SELECT id FROM urls WHERE url = ?", (site.url("/bridge"),)
    )
    # An External URL at depth 2 does not fill the Internal URLs' depth bucket.
    with CrawlWriter(crawled.crawl_file, SystemClock()) as writer:
        writer.run(
            reclassify_urls([Reclassified(url_id=bridge_id, is_internal=False, in_scope=False)])
        )
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = summary(request).crawl_depth

    assert result.partial is False
    assert result.max == 3
    assert result.distribution == [
        DepthCount(0, 1),
        DepthCount(1, 2),
        DepthCount(2, 0),
        DepthCount(3, 1),
    ]


def test_summary_json_members_and_version(temp_workspace: TempWorkspace) -> None:
    create_any_crawl(temp_workspace)

    result = run_cli("summary")

    assert result.exit_code == 0, result.stderr
    assert set(result.json()) == {
        "summary_version",
        "crawl",
        "segment",
        "totals",
        "status_classes",
        "indexability",
        "content_types",
        "crawl_depth",
        "response_time_ms",
        "health_score",
        "issues",
        "segments",
        "unsegmented",
    }
    assert result.json()["summary_version"] == 1


def test_no_responses(temp_workspace: TempWorkspace) -> None:
    create_any_crawl(temp_workspace)
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = summary(request)

    assert msgspec.to_builtins(result.response_time_ms) == {
        "count": 0,
        "min": None,
        "mean": None,
        "p50": None,
        "p90": None,
        "p95": None,
        "p99": None,
        "max": None,
        "histogram": [
            {"from_ms": 0, "to_ms": 100, "count": 0},
            {"from_ms": 100, "to_ms": 250, "count": 0},
            {"from_ms": 250, "to_ms": 500, "count": 0},
            {"from_ms": 500, "to_ms": 1000, "count": 0},
            {"from_ms": 1000, "to_ms": 2000, "count": 0},
            {"from_ms": 2000, "to_ms": 5000, "count": 0},
            {"from_ms": 5000, "to_ms": None, "count": 0},
        ],
    }


def test_no_internal_pages(temp_workspace: TempWorkspace) -> None:
    create_any_crawl(temp_workspace)
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    assert summary(request).health_score == HealthScore(None, 0, 0)


def test_summary_table_has_named_sections(temp_workspace: TempWorkspace) -> None:
    create_any_crawl(temp_workspace)

    result = run_cli("summary", "--format", "table")

    assert result.exit_code == 0, result.stderr
    headings = {line.strip() for line in result.stdout.splitlines()}
    assert {b"Crawl", b"Health", b"Issues"} <= headings
    assert b"Health Score" in result.stdout


def test_latest_and_explicit_crawl(temp_workspace: TempWorkspace) -> None:
    older = create_crawl_at(temp_workspace, "2026-09-27T14:03:12.345Z", "aaaaaaaa")
    newer = create_crawl_at(temp_workspace, "2026-09-27T14:03:13.345Z", "bbbbbbbb")
    before = (sha256_of(older.path), sha256_of(newer.path))
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    assert summary(request).crawl.id == newer.id
    explicit = summary(replace(request, crawl=older.id))
    assert explicit.crawl.id == older.id
    assert explicit.crawl.state == "running"
    assert explicit.totals.encountered == 0
    assert (sha256_of(older.path), sha256_of(newer.path)) == before


def test_live_and_recorded_health_score(temp_workspace: TempWorkspace) -> None:
    pages = {
        f"https://example.com/p{index}": (
            (f"<title>Document {index}</title>" if index > 2 else "")
            + (f"<h1>Heading {index}</h1>" if index not in (3, 4, 5) else "")
            + f"<p>Reference document number {index}.</p>"
        )
        for index in range(1, 10)
    }
    path = crawl_store(temp_workspace, pages=pages, completed=False)
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    live = summary(request)
    assert live.health_score == HealthScore(80, 10, 2)
    assert {
        (item.rule_id, item.issue_type, item.affected_count)
        for item in summary(request, top=100).issues.top
    } >= {("title-missing", "issue", 2), ("h1-missing", "warning", 3)}

    table = run_cli("summary", "--format", "table")
    assert table.exit_code == 0, table.stderr
    assert any(b"Health Score" in line and b"80" in line for line in table.stdout.splitlines())
    with CrawlWriter(path, FakeClock()) as writer:
        # Supply the recorded fields directly to distinguish them from a live recount.
        writer.run(
            executing(
                update(crawl).values(
                    health_score=70,
                    health_internal_page_count=10,
                    health_affected_page_count=3,
                    health_calculated_at=STARTED_AT,
                )
            )
        )
        writer.run(record_state("completed", STARTED_AT + timedelta(seconds=20)))

    assert summary(request).health_score == HealthScore(70, 10, 3)


def test_running_crawl_summary_counts_committed_pages(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace,
        pages={f"https://example.com/{slug}": f"<title>{slug}</title>" for slug in ("a", "b", "c")},
        completed=False,
    )

    result = run_cli("summary")

    assert result.exit_code == 0, result.stderr
    assert result.json()["crawl"]["state"] == "running"
    assert result.json()["totals"]["pages"] == 4


def test_summary_does_not_report_unrecorded_health_as_zero(temp_workspace: TempWorkspace) -> None:
    fixture = (
        Path(__file__).resolve().parents[1] / "rules" / "fixtures" / "preview-delete.sqlite.gz"
    )
    file = temp_workspace.root / "preview.sqlite"
    file.write_bytes(gzip.decompress(fixture.read_bytes()))
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home, crawl=str(file))

    result = summary(request)

    assert (result.crawl.state, result.totals.pages) == ("stopped", 1)
    assert result.health_score == HealthScore(None, None, None)


def test_issue_groups_and_top_order(temp_workspace: TempWorkspace) -> None:
    crawl_store(
        temp_workspace,
        example_issues=(
            ("rule-a", "warning", "high", 50),
            ("rule-b", "issue", "low", 3),
            ("rule-c", "issue", "high", 1),
            ("rule-d", "issue", "high", 9),
            ("rule-e", "opportunity", "low", 7),
        ),
    )
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    issues = summary(request, top=3).issues

    assert issues.total == 5
    assert [
        (cell.issue_type, cell.priority, cell.issues, cell.affected_count)
        for cell in issues.by_type_priority
    ] == [
        ("issue", "high", 2, 10),
        ("issue", "medium", 0, 0),
        ("issue", "low", 1, 3),
        ("warning", "high", 1, 50),
        ("warning", "medium", 0, 0),
        ("warning", "low", 0, 0),
        ("opportunity", "high", 0, 0),
        ("opportunity", "medium", 0, 0),
        ("opportunity", "low", 1, 7),
    ]
    assert [item.rule_id for item in issues.top] == ["rule-d", "rule-c", "rule-b"]
    assert summary(request, top=0).issues.top == []


def test_summary_contract_example() -> None:
    path = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "summary.md"
    example = path.read_text(encoding="utf-8").split("```json\n", 1)[1].split("```", 1)[0].strip()

    model = msgspec.json.decode(example, type=SummaryModel)

    assert model.health_score == HealthScore(0, 1, 1)
    assert model.response_time_ms.p50 == 100
    assert model.issues.top[0].rule_id == "title-missing"
    assert model.crawl.seeds == ["https://example.com/"]
    assert msgspec.to_builtins(model) == msgspec.json.decode(example)


def test_summary_of_reference_crawl(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    settings = temp_workspace.root / "openlinx.toml"
    settings.write_text(
        "".join(
            f"[rules.{rule.id}]\nenabled = false\n" for rule in RULES if rule.id != "title-missing"
        ),
        encoding="utf-8",
    )
    site = fixture_site(
        Site(
            {
                "/": Page(
                    body='<title>Home</title><a href="/about">About</a>'
                    '<a href="/gone">Gone</a><img src="/logo.png" alt="Logo">'
                    '<img src="/logo.png" alt="Wordmark">'
                ),
                "/about": Page(body='<meta name="robots" content="noindex"><h1>About</h1>'),
                "/gone": Status(404, content_type="text/plain"),
                "/logo.png": Status(200, content_type="image/png"),
            }
        )
    )
    crawled = crawl_result(site.url("/"))
    assert crawled.summary.state == "completed"
    before = sha256_of(crawled.crawl_file)

    result = run_cli("summary")
    assert result.exit_code == 0, result.stderr
    document = result.json()
    for key in ("id", "started_at", "completed_at", "tool_version"):
        del document["crawl"][key]
    del document["response_time_ms"]

    assert document == {
        "summary_version": 1,
        "crawl": {
            "seeds": [site.url("/")],
            "seed_count": 1,
            "crawl_mode": "spider",
            "state": "completed",
            "stop_reason": None,
            "section_crawl": False,
            "link_metrics": "complete",
            "schema_version": 1,
        },
        "segment": None,
        "totals": {
            "encountered": 4,
            "crawled": 4,
            "urls": 4,
            "internal_urls": 4,
            "external_urls": 0,
            "pages": 2,
            "resources": 1,
        },
        "status_classes": {
            "internal": {
                "2xx": 3,
                "3xx": 0,
                "4xx": 1,
                "5xx": 0,
                "other": 0,
                "no_response": 0,
                "record_failed": 0,
                "blocked_by_robots_txt": 0,
            },
            "external": {
                "2xx": 0,
                "3xx": 0,
                "4xx": 0,
                "5xx": 0,
                "other": 0,
                "no_response": 0,
                "record_failed": 0,
                "blocked_by_robots_txt": 0,
            },
        },
        "indexability": {
            "indexable": 1,
            "non_indexable": 1,
            "by_status": [{"status": "noindex", "count": 1}],
        },
        "content_types": [
            {"content_type": "text/html", "count": 2, "share_pct": 50.0},
            {"content_type": "image/png", "count": 1, "share_pct": 25.0},
            {"content_type": "text/plain", "count": 1, "share_pct": 25.0},
        ],
        "crawl_depth": {
            "partial": False,
            "max": 1,
            "distribution": [{"depth": 0, "count": 1}, {"depth": 1, "count": 3}],
        },
        "health_score": {"score": 50, "internal_pages": 2, "affected_pages": 1},
        "issues": {
            "total": 1,
            "by_type_priority": [
                {"issue_type": "issue", "priority": "high", "issues": 1, "affected_count": 1},
                {"issue_type": "issue", "priority": "medium", "issues": 0, "affected_count": 0},
                {"issue_type": "issue", "priority": "low", "issues": 0, "affected_count": 0},
                {"issue_type": "warning", "priority": "high", "issues": 0, "affected_count": 0},
                {"issue_type": "warning", "priority": "medium", "issues": 0, "affected_count": 0},
                {"issue_type": "warning", "priority": "low", "issues": 0, "affected_count": 0},
                {"issue_type": "opportunity", "priority": "high", "issues": 0, "affected_count": 0},
                {
                    "issue_type": "opportunity",
                    "priority": "medium",
                    "issues": 0,
                    "affected_count": 0,
                },
                {"issue_type": "opportunity", "priority": "low", "issues": 0, "affected_count": 0},
            ],
            "top": [
                {
                    "rule_id": "title-missing",
                    "category": "titles",
                    "issue_type": "issue",
                    "priority": "high",
                    "affected_count": 1,
                    "description": "A Page has no title, or its first title is empty.",
                },
            ],
        },
        "segments": [],
        "unsegmented": None,
    }
    assert sha256_of(crawled.crawl_file) == before


def test_status_classes_and_queued_outcomes(temp_workspace: TempWorkspace) -> None:
    file = create_any_crawl(temp_workspace).path
    root = Provenance(crawl_depth=0, discovered_via="seed", found_on_url_id=None)
    with CrawlWriter(file, FakeClock()) as writer:
        for index, status in enumerate((200, 200, 301, 404, 503, 999, 404)):
            is_internal = index != 6
            domain = "example.com" if is_internal else "example.net"
            url = NormalizedUrl(f"https://{domain}/response/{index}")
            url_id = writer.run(record_seed(url, is_internal=is_internal, in_scope=is_internal))
            writer.run(
                record_fetched(
                    FetchedUrl(
                        url_id=url_id,
                        provenance=root,
                        status_code=status,
                        content_type=None,
                        fetched_at=STARTED_AT,
                        response_time_ms=10,
                        parsed=False,
                        attempt_count=1,
                        redirect=None,
                    )
                )
            )
        timed_out, unwritten, blocked, _ = [
            writer.run(
                record_seed(
                    NormalizedUrl(f"https://example.com/{path}"), is_internal=True, in_scope=True
                )
            )
            for path in ("timed-out", "unwritten", "blocked", "queued")
        ]
        writer.run(
            record_error(
                ErroredUrl(
                    url_id=timed_out,
                    provenance=root,
                    fetch_error="timeout",
                    fetch_error_message="Request timed out.",
                    fetched_at=STARTED_AT,
                    attempt_count=1,
                )
            )
        )
        writer.run(
            record_unwritten(
                unwritten,
                "The writer could not record the response.",
                provenance=root,
                blocked_by_robots_txt=False,
                attempt_count=1,
            )
        )
        writer.run(
            record_skipped(
                SkippedUrl(
                    url_id=blocked,
                    provenance=root,
                    skip_reason="blocked_by_robots_txt",
                    blocked_by_robots_txt=True,
                )
            )
        )

    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    result = summary(request)

    assert result.status_classes.internal == {
        "2xx": 2,
        "3xx": 1,
        "4xx": 1,
        "5xx": 1,
        "other": 1,
        "no_response": 1,
        "record_failed": 1,
        "blocked_by_robots_txt": 1,
    }
    assert result.status_classes.external == {
        "2xx": 0,
        "3xx": 0,
        "4xx": 1,
        "5xx": 0,
        "other": 0,
        "no_response": 0,
        "record_failed": 0,
        "blocked_by_robots_txt": 0,
    }
    assert msgspec.to_builtins(result.totals) == {
        "encountered": 11,
        "crawled": 9,
        "urls": 10,
        "internal_urls": 9,
        "external_urls": 1,
        "pages": 0,
        "resources": 0,
    }
    assert result.response_time_ms.count == 6
