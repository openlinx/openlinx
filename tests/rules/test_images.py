"""Verify image Rules over measured Links and the outcomes of requests to their targets."""

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy import Connection

from openlinx.crawl.engine.hooks import UrlResult, handler
from openlinx.crawl.pages.preparation import PageInput, extractor
from openlinx.extract.page_links import PAGE_LINKS, PageLinks, extract_page_links
from openlinx.rules.registry import RULES
from openlinx.services.hooks import default_hooks
from openlinx.store.issues import read_affected_urls
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import LargeFile, Page, Redirect, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result
from tests.support.crawls import query
from tests.support.workspace import TempWorkspace


def _affected(file: Path, rule_id: str) -> list[tuple[str, object]]:
    urls = dict(query(file, "SELECT id, url FROM urls"))
    return sorted(
        (urls[row.url_id], row.detail) for row in read_affected_urls(file, rule_id, RULES)
    )


def _reproduce(file: Path, rule_id: str) -> list[tuple[str, object]]:
    urls = dict(query(file, "SELECT id, url FROM urls"))
    [(sql,)] = query(file, "SELECT reproduce_sql FROM rules WHERE id = ?", (rule_id,))
    return sorted((urls[url_id], json.loads(detail)) for url_id, detail in query(file, sql))


def _extract_links(tree: LexborHTMLParser, page: PageInput, config: None) -> PageLinks:
    if page.url.endswith("/unmeasured"):
        raise RuntimeError("Link extractor failed in the test scenario")
    return extract_page_links(tree, page, config)


@pytest.mark.usefixtures("temp_workspace")
def test_images_without_alt_text(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<a href="/shared.png"><img src="/shared.png" srcset="/retina.png 2x"></a>'
                    '<img src="/shared.png" alt=""><img src="/logo.png" alt="Logo">'
                    '<picture><source srcset="/other.png 2x"><img src="/logo.png" alt="Logo">'
                    '</picture><a href="/unmeasured">Unmeasured</a>'
                ),
                "/unmeasured": Page(body='<img src="/logo.png" alt="Logo">'),
            }
        )
    )
    defaults = default_hooks()
    link_extractor = extractor(PAGE_LINKS.name, _extract_links, None)
    hooks = replace(
        defaults,
        extractors=tuple(
            link_extractor if built.name == PAGE_LINKS.name else built
            for built in defaults.extractors
        ),
    )
    result = crawl_result(server.url("/"), hooks)
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert query(
        file,
        "SELECT target.url, links.element, links.attribute, links.alt_text "
        "FROM links JOIN urls AS source ON source.id = links.source_url_id "
        "JOIN urls AS target ON target.id = links.target_url_id "
        "WHERE source.url = ? AND links.type = 'image' ORDER BY links.ordinal",
        (server.url("/"),),
    ) == [
        (server.url("/shared.png"), "img", "src", None),
        (server.url("/retina.png"), "img", "srcset", None),
        (server.url("/shared.png"), "img", "src", ""),
        (server.url("/logo.png"), "img", "src", "Logo"),
        (server.url("/other.png"), "source", "srcset", None),
        (server.url("/logo.png"), "img", "src", "Logo"),
    ]
    assert query(
        file,
        "SELECT urls.parsed, urls.parse_error, links.alt_text, links.link_position "
        "FROM urls JOIN links ON links.source_url_id = urls.id WHERE urls.url = ?",
        (server.url("/unmeasured"),),
    ) == [(1, "extractor_error", None, None)]
    assert _affected(file, "image-missing-alt-text") == [
        (server.url("/"), {"missing_alt_attribute": 1, "empty_alt": 1})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_srcset_candidates_are_not_counted_twice(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<img src="/a.png" srcset="/a-2x.png 2x">'),
                "/a.png": Status(200, content_type="image/png"),
                "/a-2x.png": Status(200, content_type="image/png"),
            }
        )
    )
    result = crawl_result(server.url("/"))
    assert result.summary.state == "completed"
    assert sorted(request.path for request in server.requests if request.path.endswith(".png")) == [
        "/a-2x.png",
        "/a.png",
    ]
    assert _affected(result.crawl_file, "image-missing-alt-text") == [
        (server.url("/"), {"missing_alt_attribute": 1, "empty_alt": 0})
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_all_images_described(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<img src="/logo.png" alt="Logo">'),
                "/logo.png": Status(200, content_type="image/png"),
            }
        )
    )
    result = crawl_result(server.url("/"))
    assert result.summary.state == "completed"
    assert query(result.crawl_file, "SELECT alt_text FROM links WHERE type = 'image'") == [
        ("Logo",)
    ]
    assert _affected(result.crawl_file, "image-missing-alt-text") == []


@pytest.mark.parametrize(
    ("max_kb", "expected"),
    [
        (None, [("/over.png", {"size_bytes": 102401})]),
        (101, []),
        (10**100, []),
    ],
)
def test_image_over_the_size_limit(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    max_kb: int | None,
    expected: list[tuple[str, dict[str, int]]],
) -> None:
    if max_kb is not None:
        (temp_workspace.root / "openlinx.toml").write_text(
            f"[rules.image-too-large]\nmax_kb = {max_kb}\n", encoding="utf-8"
        )
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body='<a href="/over.png"><img src="/over.png"></a>'
                    '<img src="/over.png"><a href="/unlinked.webp">File</a>'
                ),
                "/over.png": LargeFile(size=102401, content_type="image/png"),
                "/unlinked.webp": LargeFile(size=102401, content_type="image/webp"),
            }
        )
    )
    result = crawl_result(server.url("/"))
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert query(
        file, "SELECT url, size_bytes FROM urls WHERE url <> ? ORDER BY url", (server.url("/"),)
    ) == [
        (server.url("/over.png"), 102401),
        (server.url("/unlinked.webp"), 102401),
    ]
    assert _affected(file, "image-too-large") == [
        (server.url(path), detail) for path, detail in expected
    ]


@pytest.mark.usefixtures("temp_workspace")
def test_image_at_the_size_limit(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<img src="/at.png">'),
                "/at.png": LargeFile(size=102400, content_type="image/png"),
            }
        )
    )
    result = crawl_result(server.url("/"))
    assert result.summary.state == "completed"
    assert query(
        result.crawl_file, "SELECT size_bytes FROM urls WHERE url = ?", (server.url("/at.png"),)
    ) == [(102400,)]
    assert _affected(result.crawl_file, "image-too-large") == []


@pytest.fixture
def image_and_page_crawl(temp_workspace: TempWorkspace, fixture_hosts: StartHosts) -> Path:
    large_html = "<p>" + "x" * 102401 + "</p>"
    html_error = Status(404, body=large_html, content_type="Text/HTML; charset=utf-8")
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body='<img src="/large"><a href="/genuine.png">Image</a>'
                    '<img src="/missing.png"><img src="http://other.test/large">'
                    '<img src="/image-hop">'
                    '<a href="/bad">Bad Page</a><a href="/page-hop">Redirect</a>'
                    '<a href="/hub">Hub</a>'
                ),
                "/large": Page(body=large_html, content_type="TEXT/HTML; charset=utf-8"),
                "/genuine.png": LargeFile(size=102401, content_type="image/png"),
                "/missing.png": html_error,
                "/bad": html_error,
                "/image-hop": Redirect("/redirected-missing"),
                "/page-hop": Redirect("/redirected-bad"),
                "/redirected-missing": html_error,
                "/redirected-bad": html_error,
                "/hub": Page(body='<a href="/later">Later</a>'),
                "/later": Page(
                    body='<img src="/bad"><img src="/redirected-bad">'
                    '<img src="/redirected-missing"><img src="/genuine.png">'
                    '<a href="/missing.png">Missing image</a>'
                ),
            }
        ),
        Site(
            {
                "/large": Page(
                    body=large_html, content_type="Application/XHTML+XML \t; charset=utf-8"
                ),
            }
        ),
    )
    result = crawl_result("http://site.test/", resolver=hosts.resolver, check_external=True)
    assert result.summary.state == "completed"
    file = result.crawl_file
    assert query(
        file,
        """SELECT urls.url, urls.discovered_via, urls.status_code, urls.parsed, urls.size_bytes,
                  pages.url_id IS NOT NULL, parent.discovered_via, urls.attempt_count
           FROM urls JOIN links ON links.target_url_id = urls.id
           LEFT JOIN pages ON pages.url_id = urls.id
           LEFT JOIN urls AS parent ON parent.id = urls.found_on_url_id
           WHERE links.type = 'image' AND urls.status_code IN (200, 404)
           ORDER BY urls.url""",
    ) == [
        ("http://other.test/large", "image", 200, 0, 102408, 0, "seed", 1),
        ("http://site.test/bad", "hyperlink", 404, 0, 102408, 1, "seed", 1),
        ("http://site.test/genuine.png", "hyperlink", 200, 0, 102401, 0, "seed", 1),
        ("http://site.test/large", "image", 200, 1, 102408, 1, "seed", 1),
        ("http://site.test/missing.png", "image", 404, 0, 102408, 1, "seed", 1),
        ("http://site.test/redirected-bad", "redirect", 404, 0, 102408, 1, "hyperlink", 1),
        ("http://site.test/redirected-missing", "redirect", 404, 0, 102408, 1, "image", 1),
    ]
    assert query(
        file,
        """SELECT source.crawl_depth, links.type, target.url
           FROM links JOIN urls AS source ON source.id = links.source_url_id
           JOIN urls AS target ON target.id = links.target_url_id
           WHERE target.url IN ('http://site.test/bad', 'http://site.test/missing.png')
           ORDER BY target.url, source.crawl_depth""",
    ) == [
        (0, "hyperlink", "http://site.test/bad"),
        (2, "image", "http://site.test/bad"),
        (0, "image", "http://site.test/missing.png"),
        (2, "hyperlink", "http://site.test/missing.png"),
    ]
    return file


def test_image_size_excludes_html_responses(image_and_page_crawl: Path) -> None:
    expected: list[tuple[str, object]] = [("http://site.test/genuine.png", {"size_bytes": 102401})]
    assert _affected(image_and_page_crawl, "image-too-large") == expected
    assert _reproduce(image_and_page_crawl, "image-too-large") == expected


def test_html_404_for_an_image_target_in_either_link_order(image_and_page_crawl: Path) -> None:
    expected: list[tuple[str, object]] = [
        ("http://site.test/bad", {"status_code": 404}),
        ("http://site.test/missing.png", {"status_code": 404}),
        ("http://site.test/redirected-bad", {"status_code": 404}),
        ("http://site.test/redirected-missing", {"status_code": 404}),
    ]
    assert _affected(image_and_page_crawl, "image-broken") == expected
    assert _reproduce(image_and_page_crawl, "image-broken") == expected


@pytest.mark.parametrize(
    ("first_link", "shorter_link", "dispatched_via", "stored_via"),
    [
        ('<a href="/x">X</a>', '<img src="/x">', "hyperlink", "image"),
        ('<img src="/x">', '<a href="/x">X</a>', "image", "hyperlink"),
    ],
)
@pytest.mark.usefixtures("temp_workspace")
def test_an_image_request_keeps_its_result_when_provenance_changes(
    fixture_site: StartSite,
    first_link: str,
    shorter_link: str,
    dispatched_via: str,
    stored_via: str,
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<img src="/late"><a href="/a">A</a>'),
                "/a": Page(body='<a href="/b">B</a>'),
                "/b": Page(body=first_link),
                "/late": Page(body=shorter_link, after="/x"),
                "/x": Status(404, body="<p>Missing</p>", delay=2.0),
            }
        )
    )
    dispatched: list[tuple[int, str, int]] = []

    def observe(result: UrlResult) -> tuple[()]:
        if result.url == server.url("/x") and result.response is not None:
            dispatched.append(
                (result.crawl_depth, result.discovered_via, result.response.status_code)
            )
        return ()

    defaults = default_hooks()
    hooks = replace(
        defaults,
        handlers=(*defaults.handlers, handler("observe_dispatch", observe, lambda *_: None)),
    )
    result = crawl_result(server.url("/"), hooks)
    assert result.summary.state == "completed"
    assert dispatched == [(3, dispatched_via, 404)]
    assert [request.path for request in server.requests].count("/x") == 1
    file = result.crawl_file
    assert query(
        file,
        """SELECT target.crawl_depth, target.discovered_via, target.status_code,
                  target.attempt_count, parent.url
           FROM urls AS target JOIN urls AS parent ON parent.id = target.found_on_url_id
           WHERE target.url = ?""",
        (server.url("/x"),),
    ) == [(2, stored_via, 404, 1, server.url("/late"))]
    expected: list[tuple[str, object]] = [(server.url("/x"), {"status_code": 404})]
    assert _affected(file, "image-broken") == expected
    assert _reproduce(file, "image-broken") == expected


def _reject_one_response(result: UrlResult) -> tuple[int, ...]:
    return (result.url_id,) if result.url.endswith("/write-failure.png") and result.response else ()


def _reject_image_rows(_connection: Connection, ids: Sequence[int]) -> None:
    raise ValueError(f"Test could not record the image {ids[0]}")


@pytest.mark.parametrize("check_external", [True, False])
@pytest.mark.usefixtures("temp_workspace")
def test_broken_external_image(fixture_hosts: StartHosts, check_external: bool) -> None:
    targets = ("missing", "unavailable", "timeout", "outside-status")
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body="".join(f'<img src="http://other.test/{name}.png">' for name in targets)
                    + '<a href="http://other.test/link-only.png">Not an image Link</a>'
                )
            }
        ),
        Site(
            {
                "/missing.png": Status(404, body="No file"),
                "/unavailable.png": Status(599),
                "/timeout.png": Status(200, hang=True),
                "/outside-status.png": Status(600),
                "/link-only.png": Status(404, content_type="image/png"),
            }
        ),
    )
    result = crawl_result(
        "http://site.test/",
        resolver=hosts.resolver,
        check_external=check_external,
        retries=0,
        timeout=1,
    )
    file = result.crawl_file

    assert result.summary.state == "completed"
    states = query(
        file,
        "SELECT url, fetch_state, status_code, fetch_error, attempt_count FROM urls "
        "WHERE is_internal = 0 ORDER BY url",
    )
    requests = sorted(request.path for request in hosts.other.requests)
    if check_external:
        assert requests == [
            "/link-only.png",
            "/missing.png",
            "/outside-status.png",
            "/robots.txt",
            "/timeout.png",
            "/unavailable.png",
        ]
        assert states == [
            ("http://other.test/link-only.png", "fetched", 404, None, 1),
            ("http://other.test/missing.png", "fetched", 404, None, 1),
            ("http://other.test/outside-status.png", "fetched", 600, None, 1),
            ("http://other.test/timeout.png", "error", None, "timeout", 1),
            ("http://other.test/unavailable.png", "fetched", 599, None, 1),
        ]
        expected: list[tuple[str, object]] = [
            ("http://other.test/missing.png", {"status_code": 404}),
            ("http://other.test/timeout.png", {"error": "timeout"}),
            ("http://other.test/unavailable.png", {"status_code": 599}),
        ]
    else:
        assert requests == []
        assert states == [
            (f"http://other.test/{target}.png", "skipped", None, None, 0)
            for target in sorted((*targets, "link-only"))
        ]
        expected = []
    assert _affected(file, "image-broken") == expected


@pytest.mark.usefixtures("temp_workspace")
def test_an_image_that_failed_to_be_recorded_is_not_broken(fixture_site: StartSite) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<img src="/write-failure.png">'),
                "/write-failure.png": Status(404),
            }
        )
    )
    defaults = default_hooks()
    broken_writer = handler("reject_image", _reject_one_response, _reject_image_rows)
    hooks = replace(defaults, handlers=(*defaults.handlers, broken_writer))
    result = crawl_result(server.url("/"), hooks)
    assert result.summary.state == "completed"
    assert [request.path for request in server.requests].count("/write-failure.png") == 1
    assert query(
        result.crawl_file,
        "SELECT fetch_state, status_code, fetch_error, attempt_count FROM urls WHERE url = ?",
        (server.url("/write-failure.png"),),
    ) == [("error", None, "record_failed", 1)]
    assert [(warning.code, warning.details.get("count")) for warning in result.warnings] == [
        ("record_failed", 1)
    ]
    assert _affected(result.crawl_file, "image-broken") == []


@pytest.mark.usefixtures("temp_workspace")
def test_a_robots_txt_failure_before_an_image_request_does_not_count(
    fixture_hosts: StartHosts,
) -> None:
    hosts = fixture_hosts(
        Site(
            {
                "/": Page(
                    body='<img src="/broken.png"><img src="http://other.test/unrequested.png">'
                ),
                "/broken.png": Status(404),
            }
        ),
        Site(
            {
                "/robots.txt": Robots("User-agent: *\nAllow: /\n", hang=True),
                "/unrequested.png": Status(404),
            }
        ),
    )
    result = crawl_result(
        "http://site.test/", resolver=hosts.resolver, check_external=True, retries=0, timeout=1
    )
    file = result.crawl_file

    assert result.summary.state == "completed"
    assert [request.path for request in hosts.other.requests] == ["/robots.txt"]
    assert query(
        file, "SELECT attempt_count, fetch_state, fetch_error FROM urls WHERE is_internal = 0"
    ) == [(0, "error", "timeout")]
    assert _affected(file, "image-broken") == [
        ("http://site.test/broken.png", {"status_code": 404})
    ]


def test_image_rule_catalogue_order(temp_workspace: TempWorkspace) -> None:
    result = run_cli("rules", "list", "--limit", "50")
    assert result.exit_code == 0, result.stderr
    assert [
        (item["id"], item["issue_type"], item["priority"], item["applies_to"], item["thresholds"])
        for item in result.json()["items"]
        if item["category"] == "images"
    ] == [
        ("image-missing-alt-text", "opportunity", "low", "internal_pages", {}),
        (
            "image-too-large",
            "opportunity",
            "medium",
            "resources",
            {"max_kb": {"value": 100, "default": 100, "unit": "kilobytes"}},
        ),
        ("image-broken", "issue", "medium", "resources", {}),
    ]
