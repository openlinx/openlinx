"""Keep request compression preferences separate from bounded response decoder support."""

import gzip
import json
from pathlib import Path

import pytest

from openlinx.naming import SETTINGS_FILE_NAME
from openlinx.output.diagnostics import OpenLinxError
from openlinx.services.crawling import CrawlRequest, plan_crawl
from tests.fixture_site.hosts import StartHosts
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Responses, Robots, Site, Status
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result, crawled
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


@pytest.mark.parametrize("source", ["flags", "settings"])
@pytest.mark.parametrize(
    "value",
    [
        "gzip;q=1.1",
        "br;q=0.1234",
        "gzip;level=1",
        "gzip,,br",
        ",gzip",
        "gzip,",
        "gzip;q=-0.1",
        "gzip;q=.5",
        "gzip;q=2",
        "gzip;q=00",
        "gzip;q=1.0000",
        "gzip;q=",
        "gzip;q =0.5",
        "gzip;q= 0.5",
        "gzip;q=0.5;q=0.4",
        "gzip;Q=NaN",
        "gzip br",
    ],
)
def test_invalid_negotiation_syntax_is_refused_before_network(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, value: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    headers = ["X-Token: abc123", f"Accept-Encoding: {value}"]
    flags = [part for header in headers for part in ("--header", header)]
    if source == "settings":
        (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
            f"[crawl]\nheader = {json.dumps(headers)}\n"
        )
        flags = []

    result = run_cli("crawl", server.url("/"), *flags)

    assert (result.exit_code, [error["code"] for error in result.errors()], server.requests) == (
        2 if source == "flags" else 3,
        ["invalid_value"] if source == "flags" else ["settings_invalid"],
        (),
    )
    assert b"abc123" not in result.stderr
    assert value.encode() not in result.stderr


@pytest.mark.parametrize(
    ("workspace", "flags", "internal", "recorded"),
    [
        ([], [], ["gzip, deflate, br, zstd"], []),
        ([], ["Accept-Encoding: identity"], ["identity"], ["Accept-Encoding: identity"]),
        ([], ["accept-encoding:gzip"], ["gzip"], ["accept-encoding:gzip"]),
        (
            [],
            ["Accept-Encoding: br;q=1, gzip;q=0.5, identity;q=0"],
            ["br;q=1, gzip;q=0.5, identity;q=0"],
            ["Accept-Encoding: br;q=1, gzip;q=0.5, identity;q=0"],
        ),
        ([], ["Accept-Encoding: *;q=0.5"], ["*;q=0.5"], ["Accept-Encoding: *;q=0.5"]),
        ([], ["Accept-Encoding: x-unknown"], ["x-unknown"], ["Accept-Encoding: x-unknown"]),
        ([], ["Accept-Encoding:"], [""], ["Accept-Encoding:"]),
        (["Accept-Encoding: identity"], [], ["identity"], ["Accept-Encoding: identity"]),
        (
            ["Accept-Encoding: identity"],
            ["Accept-Encoding: gzip"],
            ["gzip"],
            ["Accept-Encoding: gzip"],
        ),
        (
            [],
            ["Accept-Encoding: gzip", "accept-encoding: br;q=0.5"],
            ["gzip", "br;q=0.5"],
            ["Accept-Encoding: gzip", "accept-encoding: br;q=0.5"],
        ),
    ],
)
def test_accept_encoding_overrides_have_literal_internal_and_external_outcomes(
    temp_workspace: TempWorkspace,
    fixture_hosts: StartHosts,
    workspace: list[str],
    flags: list[str],
    internal: list[str],
    recorded: list[str],
) -> None:
    (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
        f"[crawl]\nheader = {json.dumps(workspace)}\n"
    )
    hosts = fixture_hosts(
        Site({"/": Page(body='<a href="http://other.test/page">Other</a>')}),
        Site({"/page": Page(body="Other")}),
    )

    if flags:
        result = crawl_result("http://site.test/", resolver=hosts.resolver, header=flags)
    else:
        result = crawl_result("http://site.test/", resolver=hosts.resolver)

    assert result.summary.state == "completed"
    assert {r.path for r in hosts.site.requests} == {"/robots.txt", "/"}
    assert [r.headers.getall("Accept-Encoding") for r in hosts.site.requests] == [
        internal,
        internal,
    ]
    assert {r.path for r in hosts.other.requests} == {"/robots.txt", "/page"}
    assert [r.headers.getall("Accept-Encoding") for r in hosts.other.requests] == [
        ["gzip, deflate, br, zstd"],
        ["gzip, deflate, br, zstd"],
    ]
    assert json.loads(crawl_row(result.crawl_file)["config"])["crawl"]["header"] == recorded


@pytest.mark.parametrize("source", ["flags", "settings"])
@pytest.mark.parametrize(
    ("value", "wire"),
    [
        ("gzip;q=0", "gzip;q=0"),
        ("gzip;q=0.", "gzip;q=0."),
        ("gzip;q=1.", "gzip;q=1."),
        ("gzip;q=1.000", "gzip;q=1.000"),
        ("gzip ;\tQ=0.123", "gzip ;\tQ=0.123"),
        (" \t", ""),
        ("GZIP,\tdeflate , br", "GZIP,\tdeflate , br"),
    ],
)
def test_valid_negotiation_edges_preserve_the_field_value(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, value: str, wire: str
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    header = f"aCcEpT-EnCoDiNg: {value}"
    flags = ["--header", header]
    if source == "settings":
        (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
            f"[crawl]\nheader = {json.dumps([header])}\n"
        )
        flags = []

    result = run_cli("crawl", server.url("/"), *flags)

    assert result.exit_code == 0
    assert [r.headers.getall("Accept-Encoding") for r in server.requests] == [[wire], [wire]]
    config = json.loads(crawl_row(Path(result.json()["crawl_file"]))["config"])
    assert config["crawl"]["header"] == [header]


@pytest.mark.parametrize("value", ["identity", "identity, gzip;q=0"])
def test_a_supported_response_is_decoded_despite_the_request_preference(
    temp_workspace: TempWorkspace, fixture_site: StartSite, tmp_path: Path, value: str
) -> None:
    (tmp_path / "app.js.gz").write_bytes(gzip.compress(b"hello", mtime=0))
    server = fixture_site(
        Site(
            root=tmp_path,
            routes={
                "/": Page(body='<script src="/app.js"></script>'),
                "/app.js": Page(
                    file="app.js.gz",
                    content_type="text/javascript",
                    headers=[("Content-Encoding", "gzip")],
                ),
            },
        )
    )

    crawl_file = crawled(server.url("/"), "--header", f"Accept-Encoding: {value}")

    assert query(
        crawl_file,
        "SELECT fetch_state, content_encoding, size_bytes, body_truncated FROM urls WHERE url = ?",
        [server.url("/app.js")],
    ) == [("fetched", "gzip", 5, 0)]
    assert [r.headers.getall("Accept-Encoding") for r in server.requests] == [
        [value],
        [value],
        [value],
    ]


def test_advertising_an_unsupported_coding_does_not_install_a_decoder(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(body='<a href="/unknown.html">Unknown</a>'),
                "/unknown.html": Page(
                    body="<title>Unknown coding</title>",
                    headers=[("Content-Encoding", "x-unknown")],
                ),
            }
        )
    )

    crawl_file = crawled(server.url("/"), "--header", "Accept-Encoding: x-unknown")

    assert query(
        crawl_file,
        "SELECT fetch_state, parsed, parse_error, size_bytes FROM urls WHERE url = ?",
        [server.url("/unknown.html")],
    ) == [("fetched", 0, "unsupported_encoding", None)]
    assert [r.headers.getall("Accept-Encoding") for r in server.requests] == [
        ["x-unknown"],
        ["x-unknown"],
        ["x-unknown"],
    ]


@pytest.mark.parametrize("source", ["flags", "settings"])
@pytest.mark.parametrize(
    "headers",
    [
        ["Accept-Encoding:", "Accept-Encoding: gzip"],
        ["Accept-Encoding: gzip", "accept-encoding: \t"],
        ["Accept-Encoding:", "accept-encoding: \t"],
    ],
)
def test_repeated_accept_encoding_fields_cannot_include_an_empty_value(
    temp_workspace: TempWorkspace, fixture_site: StartSite, source: str, headers: list[str]
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    flags = [part for header in headers for part in ("--header", header)]
    if source == "settings":
        (temp_workspace.root / SETTINGS_FILE_NAME).write_text(
            f"[crawl]\nheader = {json.dumps(headers)}\n"
        )
        flags = []

    result = run_cli("crawl", server.url("/"), *flags)

    assert (result.exit_code, [error["code"] for error in result.errors()], server.requests) == (
        2 if source == "flags" else 3,
        ["invalid_value"] if source == "flags" else ["settings_invalid"],
        (),
    )


@pytest.mark.parametrize(
    "headers",
    [
        ["Accept-Encoding: gzip;q=1.1"],
        ["Accept-Encoding:", "Accept-Encoding: gzip"],
    ],
)
def test_service_inputs_refuse_invalid_accept_encoding_without_cli_evidence(
    temp_workspace: TempWorkspace, fixture_site: StartSite, headers: list[str]
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))

    with pytest.raises(OpenLinxError) as caught:
        plan_crawl(
            CrawlRequest(
                seed=server.url("/"),
                cwd=temp_workspace.root,
                home=temp_workspace.home,
                workspace=None,
                command_argv=["service-crawl"],
                flags={"crawl": {"header": headers}},
                secret_flags={},
            )
        )

    assert caught.value.code == "invalid_value"
    assert server.requests == ()


def test_accept_encoding_overrides_survive_robots_and_page_retries(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/robots.txt": Responses(
                    (Status(503, headers=[("Retry-After", "0")]), Robots("User-agent: *\n"))
                ),
                "/": Responses((Status(503, headers=[("Retry-After", "0")]), Page(body="Home"))),
            }
        )
    )

    crawl_file = crawled(
        server.url("/"),
        "--header",
        "Accept-Encoding: identity",
        "--header",
        "X-Env: staging",
        "--header",
        "X-Token: abc123",
        "--header",
        "x-env: audit",
        "--auth",
        "alice:s3cret",
        "--retries",
        "1",
    )

    assert [
        (request.path, request.headers.getall("Authorization", [])) for request in server.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
    assert [
        (
            r.path,
            r.headers.getall("Accept-Encoding", []),
            r.headers.getall("X-Env", []),
            r.headers.getall("X-Token", []),
        )
        for r in server.requests
    ] == [
        ("/robots.txt", ["identity"], ["staging", "audit"], ["abc123"]),
        ("/robots.txt", ["identity"], ["staging", "audit"], ["abc123"]),
        ("/", ["identity"], ["staging", "audit"], ["abc123"]),
        ("/", ["identity"], ["staging", "audit"], ["abc123"]),
    ]
    assert query(crawl_file, "SELECT fetch_state, attempt_count FROM urls") == [("fetched", 2)]
