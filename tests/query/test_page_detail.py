"""Read a single Page through the Query Service."""

import pytest

from openlinx.services.query import QueryRequest, page
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Redirect, Site
from tests.fixture_site.server import ServerHandle
from tests.support.cli import run_cli
from tests.support.crawl_store import crawl_store
from tests.support.crawling import crawl_result
from tests.support.crawls import sha256_of
from tests.support.workspace import TempWorkspace


def test_page_columns_and_issues(temp_workspace: TempWorkspace) -> None:
    address = "https://example.com/about"
    description = "Reference description for the recorded Page. " * 6
    html = f'<title>About</title><meta name="description" content="{description}">'
    crawl = crawl_store(temp_workspace, pages={address: html}, completed=False)
    before = sha256_of(crawl)
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = page(request, "HTTPS://EXAMPLE.COM/about#team")

    assert result["url"] == address
    assert result["columns"]["address"] == address
    assert result["columns"]["title_1"] == "About"
    assert result["columns"]["status_code"] == 200
    schema = run_cli("schema", "pages")
    assert schema.exit_code == 0, schema.stderr
    (table,) = schema.json()["items"]
    assert list(result["columns"]) == [column["name"] for column in table["columns"]]
    selected_issues = [
        (item["rule_id"], item["category"], item["issue_type"], item["priority"])
        for item in result["issues"]
        if item["rule_id"] in {"h1-missing", "meta-description-too-long"}
    ]
    assert selected_issues == [
        ("h1-missing", "headings", "warning", "medium"),
        ("meta-description-too-long", "meta_descriptions", "opportunity", "low"),
    ]
    assert result["segment"] is None
    assert result["redirect_chain"] == []
    assert result["html_stored"] is False
    assert "headers" not in result
    assert "html" not in result
    assert "encoding" not in result
    assert sha256_of(crawl) == before


@pytest.fixture
def redirected_site(temp_workspace: TempWorkspace, fixture_site: StartSite) -> ServerHandle:
    site = fixture_site(
        Site(
            {
                "/old": Redirect("/mid", status=301, content_type="text/html"),
                "/mid": Redirect("/new", status=302, content_type="text/html"),
                "/new": Page(
                    body="<title>New</title>",
                    headers=(
                        ("Link", "</a.css>; rel=preload"),
                        ("Set-Cookie", "session=abc123"),
                        ("Link", "</b.js>; rel=preload"),
                    ),
                ),
            }
        )
    )
    crawl = crawl_result(site.url("/old"))
    assert crawl.summary.state == "completed"
    return site


def test_redirect_chain(temp_workspace: TempWorkspace, redirected_site: ServerHandle) -> None:
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)
    url = redirected_site.url

    assert page(request, url("/old"))["redirect_chain"] == [
        {"url": url("/old"), "status_code": 301},
        {"url": url("/mid"), "status_code": 302},
        {"url": url("/new"), "status_code": 200},
    ]


def test_repeated_headers_keep_recorded_order(
    temp_workspace: TempWorkspace, redirected_site: ServerHandle
) -> None:
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = page(request, redirected_site.url("/new"), headers=True)

    headers = [header for header in result["headers"] if header["name"] in {"Link", "Set-Cookie"}]
    assert [header["name"] for header in headers] == ["Link", "Set-Cookie", "Link"]
    assert [header["value"] for header in headers if header["name"] == "Link"] == [
        "</a.css>; rel=preload",
        "</b.js>; rel=preload",
    ]


def test_response_cookie_values_are_redacted(redirected_site: ServerHandle) -> None:
    result = run_cli("page", redirected_site.url("/new"), "--headers")

    assert result.exit_code == 0, result.stderr
    cookies = [
        header["value"] for header in result.json()["headers"] if header["name"] == "Set-Cookie"
    ]
    assert cookies == ["session=***"]
    assert b"abc123" not in result.stdout


def test_issues_with_same_type_and_priority_follow_crawl_counts(
    temp_workspace: TempWorkspace,
) -> None:
    address = "https://example.com/a"
    crawl_store(
        temp_workspace,
        pages={
            address: '<link rel="canonical" href="/a"><link rel="canonical" href="/b"><h1>A</h1>',
            "https://example.com/b": "<h1>B</h1>",
        },
    )
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = page(request, address)

    assert [
        issue["rule_id"]
        for issue in result["issues"]
        if issue["rule_id"] in {"canonical-conflicting", "title-missing"}
    ] == ["title-missing", "canonical-conflicting"]


def test_unknown_url_suggests_a_nearby_page(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, pages={"https://example.com/about": "<title>About</title>"})

    missing = run_cli("page", "https://example.com/abuot")
    assert missing.exit_code == 4
    assert missing.stdout == b""
    assert missing.errors()[-1]["code"] == "url_not_found"
    assert missing.errors()[-1]["details"]["suggestions"][0] == "https://example.com/about"


def test_headers_not_stored(temp_workspace: TempWorkspace) -> None:
    crawl_store(temp_workspace, pages={"https://example.com/about": "<title>About</title>"})

    headers = run_cli("page", "https://example.com/about", "--headers")
    assert headers.exit_code == 4
    assert headers.stdout == b""
    assert headers.errors()[-1]["code"] == "headers_not_stored"
    assert headers.errors()[-1]["hint"]


def test_page_can_be_read_as_a_table(temp_workspace: TempWorkspace) -> None:
    address = "https://example.com/about"
    crawl_store(temp_workspace, pages={address: "<title>About</title>"})

    result = run_cli("page", address, "--format", "table")

    assert result.exit_code == 0, result.stderr
    rows = result.stdout.decode().splitlines()
    cells = ([cell.strip() for cell in row.split("┃")[1:-1]] for row in rows)
    assert ["key", "value"] in cells
    assert address.encode() in result.stdout


def test_section_link_counts(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    links = "".join(
        f'<a href="/blog/p{index}">Post {index}</a>' for index in (0, 1, 2, 3, 4, 5, 6, 7, 0, 1)
    )
    external = '<a href="https://example.com/news">News</a>'
    site = fixture_site(
        Site(
            {
                "/blog/": Page(body=links + external),
                "/blog/p0": Page(body='<a href="/blog/">Home</a><a href="/blog/">Index</a>'),
                "/blog/p1": Page(body='<a href="/blog/">Home</a>'),
                **{f"/blog/p{index}": Page(body="<p>Post</p>") for index in range(2, 8)},
            }
        )
    )
    crawled = crawl_result(site.url("/blog/"), scope="subfolder", check_external=False)
    assert crawled.summary.state == "completed"
    request = QueryRequest(cwd=temp_workspace.root, home=temp_workspace.home)

    result = page(request, site.url("/blog/"))

    assert result["link_counts"] == {
        "inlinks": 3,
        "unique_inlinks": 2,
        "outlinks": 10,
        "unique_outlinks": 8,
        "external_outlinks": 1,
        "partial": True,
    }
