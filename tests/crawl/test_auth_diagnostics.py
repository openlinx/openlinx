"""Guard Auth diagnostic masking through real Crawl reporting and storage."""

import json
from functools import partial

import msgspec
import pytest
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.engine.hooks import Hooks, UrlResult, handler
from openlinx.crawl.pages.preparation import PageInput, extractor
from openlinx.output.reporter import Collected
from openlinx.store.page_records import PageRow
from openlinx.store.pages import write_pages
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.crawling import crawl_result
from tests.support.crawls import crawl_row, query
from tests.support.workspace import TempWorkspace


class FailureText(msgspec.Struct, frozen=True):
    text: str


def _raise_auth_handler(message: str, result: UrlResult) -> tuple[PageRow, ...]:
    raise ValueError(message)


def _raise_auth_extractor(
    tree: LexborHTMLParser, page: PageInput, config: FailureText
) -> FailureText:
    raise ValueError(config.text)


@pytest.mark.parametrize("hook", ["handler", "extractor"])
@pytest.mark.parametrize(
    ("auth", "password", "payload", "authorization"),
    [
        ("alice:s3cret", "s3cret", "YWxpY2U6czNjcmV0", "Basic YWxpY2U6czNjcmV0"),
        ("test:123£", "123£", "dGVzdDoxMjPCow==", "Basic dGVzdDoxMjPCow=="),
        (
            "алиса:пароль",
            "пароль",
            "0LDQu9C40YHQsDrQv9Cw0YDQvtC70Yw=",
            "Basic 0LDQu9C40YHQsDrQv9Cw0YDQvtC70Yw=",
        ),
        ("test:pa\u0308ss", "pa\u0308ss", "dGVzdDpwYcyIc3M=", "Basic dGVzdDpwYcyIc3M="),
    ],
    ids=["ascii", "pound", "cyrillic", "decomposed"],
)
def test_auth_diagnostics_hide_plaintext_and_encoded_credentials(
    temp_workspace: TempWorkspace,
    fixture_site: StartSite,
    hook: str,
    auth: str,
    password: str,
    payload: str,
    authorization: str,
) -> None:
    server = fixture_site(Site({"/": Page(body="Home")}))
    message = f"refused {auth} / {password} / {payload} / {authorization}; staging"
    hooks = (
        Hooks(handlers=(handler("auth", partial(_raise_auth_handler, message), write_pages),))
        if hook == "handler"
        else Hooks(extractors=(extractor("auth", _raise_auth_extractor, FailureText(message)),))
    )
    reporter = Collected()

    result = crawl_result(server.url("/"), hooks, reporter=reporter, auth=auth, retries=0)

    expected = "refused *** / *** / *** / ***; staging"
    expected_code = "handler_failed" if hook == "handler" else "parse_failed"
    for diagnostics in (
        [warning.to_json() for warning in reporter.warnings],
        [warning.to_json() for warning in result.warnings],
        json.loads(crawl_row(result.crawl_file)["warnings"]),
    ):
        assert [(item["code"], item["details"]["error"]) for item in diagnostics] == [
            (expected_code, expected)
        ]
        text = json.dumps(diagnostics, ensure_ascii=False)
        for secret in (auth, password, payload, authorization):
            assert secret not in text
    assert query(result.crawl_file, "SELECT fetch_state, status_code FROM urls") == [
        ("fetched", 200)
    ]
    assert [
        (request.path, request.headers.getall("Authorization", [])) for request in server.requests
    ] == [("/robots.txt", [authorization]), ("/", [authorization])]


def test_a_url_transport_failure_hides_plaintext_and_encoded_auth(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            {
                "/": Page(
                    body="Home",
                    headers=[
                        (
                            "X-Bad name",
                            "refused alice:s3cret / s3cret / YWxpY2U6czNjcmV0 / "
                            "Basic YWxpY2U6czNjcmV0; staging",
                        )
                    ],
                )
            }
        )
    )

    result = crawl_result(server.url("/"), auth="alice:s3cret", retries=0, network_wait=0)

    [(state, code, message, attempts)] = query(
        result.crawl_file,
        "SELECT fetch_state, fetch_error, fetch_error_message, attempt_count FROM urls "
        "WHERE url = ?",
        [server.url("/")],
    )
    assert (state, code, attempts) == ("error", "invalid_response", 1)
    assert "X-Bad name: refused *** / *** / *** / ***; staging" in message
    for secret in ("alice:s3cret", "s3cret", "YWxpY2U6czNjcmV0", "Basic YWxpY2U6czNjcmV0"):
        assert secret not in message
    assert [
        (request.path, request.headers.getall("Authorization", [])) for request in server.requests
    ] == [
        ("/robots.txt", ["Basic YWxpY2U6czNjcmV0"]),
        ("/", ["Basic YWxpY2U6czNjcmV0"]),
    ]
