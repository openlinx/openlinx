"""Exercise declared secret forms through Crawl creation and real metadata recording."""

import json

import pytest

from openlinx.store.records import SecretNames
from openlinx.workspace.tables import SecretPolicy
from tests.support.crawls import crawl_row, create_any_crawl
from tests.support.workspace import TempWorkspace


def test_harmless_headers_survive_recording_beside_secrets(temp_workspace: TempWorkspace) -> None:
    headers = ["X-Env: staging", "x-ToKeN: abc123", "X-Env: audit"]
    crawl = create_any_crawl(
        temp_workspace,
        command_argv=[
            "linx",
            "crawl",
            "http://site.test/",
            "--header",
            "X-Env: staging",
            "--header",
            "x-ToKeN: abc123",
            "--header",
            "X-Env: audit",
        ],
        config={"crawl": {"header": headers}},
        secret_names=SecretNames(flags={"--header": "header"}, settings={"crawl.header": "header"}),
    )
    row = crawl_row(crawl.path)

    assert json.loads(row["config"]) == {
        "crawl": {"header": ["X-Env: staging", "x-ToKeN: ***", "X-Env: audit"]}
    }
    assert json.loads(row["command_argv"]) == [
        "linx",
        "crawl",
        "http://site.test/",
        "--header",
        "X-Env: staging",
        "--header",
        "x-ToKeN: ***",
        "--header",
        "X-Env: audit",
    ]
    assert headers == ["X-Env: staging", "x-ToKeN: abc123", "X-Env: audit"]
    assert b"abc123" not in crawl.path.read_bytes()


def test_a_cookie_header_keeps_its_name_and_hides_its_value(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(
        temp_workspace,
        command_argv=["linx", "crawl", "http://site.test/", "--header", "Cookie: session=abc123"],
        config={"crawl": {"header": ["Cookie: session=abc123"]}},
        secret_names=SecretNames(flags={"--header": "header"}, settings={"crawl.header": "header"}),
    )
    row = crawl_row(crawl.path)

    assert json.loads(row["config"]) == {"crawl": {"header": ["Cookie: ***"]}}
    assert json.loads(row["command_argv"]) == [
        "linx",
        "crawl",
        "http://site.test/",
        "--header",
        "Cookie: ***",
    ]
    assert b"abc123" not in crawl.path.read_bytes()


@pytest.mark.parametrize(
    ("policy", "value", "expected"),
    [
        ("whole", "http://ann:s3cret@proxy.test:8080", "***"),
        ("whole", "alice:s3cret", "***"),
        (
            "url",
            "http://proxy.test:8080/path?mode=a#here",
            "http://proxy.test:8080/path?mode=a#here",
        ),
        ("url", "http://ann:s3cret@proxy.test:8080/path", "http://ann:***@proxy.test:8080/path"),
        ("url", "http://ann@proxy.test:8080", "http://ann@proxy.test:8080"),
        ("url", "http://[ann:s3cret@proxy.test", "***"),
        ("url", "not-a-url", "***"),
        ("url", "http://proxy.test:bad", "***"),
        ("url", "http://proxy.test:99999", "***"),
        ("url", "http:///missing-host", "***"),
        ("url", "http://bad host:8080", "***"),
        (True, "http://ann:s3cret@proxy.test:8080", "http://ann:***@proxy.test:8080"),
        (True, "http://proxy.test:8080", "***"),
        (False, "http://proxy.test:8080", "http://proxy.test:8080"),
        ("header", "aUtHoRiZaTiOn: Bearer abc123", "aUtHoRiZaTiOn: ***"),
        ("header", "Proxy-Authorization: Basic dTpwdw==", "Proxy-Authorization: ***"),
        ("header", "X-Secret: abc123", "X-Secret: ***"),
        ("header", "X-Api-Key: abc123", "X-Api-Key: ***"),
        ("header", "X-Password: abc123", "X-Password: ***"),
        ("header", "cOoKiE: sid=abc123", "cOoKiE: ***"),
        ("header", "X-Env:staging", "X-Env:staging"),
        ("header", "NoColon", "***"),
    ],
)
def test_declared_secret_forms_record_their_literal_shape(
    temp_workspace: TempWorkspace, policy: SecretPolicy, value: str, expected: str
) -> None:
    crawl = create_any_crawl(
        temp_workspace,
        command_argv=["linx", "crawl", "--value", value, f"--value={value}"],
        config={"example": {"value": value}},
        secret_names=SecretNames(flags={"--value": policy}, settings={"example.value": policy}),
    )
    row = crawl_row(crawl.path)

    assert json.loads(row["command_argv"]) == [
        "linx",
        "crawl",
        "--value",
        expected,
        f"--value={expected}",
    ]
    assert json.loads(row["config"]) == {"example": {"value": expected}}


@pytest.mark.parametrize("policy", [True, "whole", "header", "url"])
def test_unset_secret_forms_remain_unset(
    temp_workspace: TempWorkspace, policy: SecretPolicy
) -> None:
    crawl = create_any_crawl(
        temp_workspace,
        config={"example": {"value": None}},
        secret_names=SecretNames(settings={"example.value": policy}),
    )

    assert json.loads(crawl_row(crawl.path)["config"]) == {"example": {"value": None}}
