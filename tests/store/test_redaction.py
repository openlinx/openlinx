"""Redacting secrets (015-add-crawl-store, crawl-store)."""

from typing import cast

import pytest
import typer

from openlinx.cli.options import secret_flags
from openlinx.cli.runner import OpenLinxGroup
from openlinx.services.crawling import CrawlRequest, plan_crawl
from openlinx.store.records import SecretNames
from openlinx.store.redaction import SecretValues, redact
from openlinx.store.writer import CrawlWriter
from tests.support.app import example_app
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace

# What the test app's example-settings Command declares secret.
EXAMPLE_SECRETS = SecretNames(
    flags=frozenset({"--token", "--api-key"}), settings=frozenset({"example.token"})
)


@pytest.mark.parametrize(
    ("values", "text", "expected"),
    [
        (("abc", "bcd"), "token=abcd", "token=***"),
        (("aba",), "token=ababa", "token=***"),
        (("abc", "def"), "token=abcdef", "token=******"),
        (("abcdef", "***x"), "token=abcdefx", "token=***x"),
        (("***tail",), "token=***tail", "token=***"),
        (("abcdef",), "token=abc", "token=abc"),
    ],
    ids=[
        "overlapping-secrets",
        "self-overlap",
        "adjacent",
        "generated-marker",
        "literal-marker",
        "prefix",
    ],
)
def test_secret_matches_are_found_in_the_original_text(
    values: tuple[str, ...], text: str, expected: str
) -> None:
    assert SecretValues(values).redact(text) == expected


@pytest.mark.parametrize(
    ("values", "text", "expected"),
    [
        (("abcdef",), "token=abc", "token=***"),
        (("abcdef",), "token=abcX", "token=abcX"),
        (("abcd", "cdef"), "token=abcd", "token=***"),
        (("cdef", "abcd"), "token=abcd", "token=***"),
        (("abcdef", "***tail"), "token=abcdeft", "token=***t"),
        (("***tail",), "token=***ta", "token=***"),
        (("ababac",), "token=ababab", "token=ab***"),
        (("ключ-🔑",), "token=ключ-", "token=***"),
        (("x",), "token=x", "token=***"),
        (("abcdef",), "", ""),
        ((), "token=abc", "token=abc"),
    ],
    ids=[
        "proper-prefix",
        "not-a-suffix",
        "full-overlaps-partial",
        "reverse-order",
        "generated-marker",
        "literal-marker",
        "prefix-fallback",
        "unicode",
        "one-character",
        "empty-text",
        "no-secrets",
    ],
)
def test_only_a_truncated_text_hides_terminal_secret_prefixes(
    values: tuple[str, ...], text: str, expected: str
) -> None:
    assert SecretValues(values).redact(text, truncated=True) == expected


def test_secret_option_with_a_separate_value() -> None:
    redacted = redact(["linx", "example-settings", "--token", "s3cret"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["linx", "example-settings", "--token", "***"]


def test_secret_option_with_a_joined_value() -> None:
    redacted = redact(["linx", "example-settings", "--api-key=s3cret"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["linx", "example-settings", "--api-key=***"]


def test_a_url_keeps_everything_but_its_password() -> None:
    redacted = redact(
        ["linx", "example-settings", "--token", "http://ann:s3cret@proxy.test:8080"],
        {},
        EXAMPLE_SECRETS,
    )

    assert redacted.command_argv == [
        "linx",
        "example-settings",
        "--token",
        "http://ann:***@proxy.test:8080",
    ]


def test_secret_setting() -> None:
    redacted = redact([], {"example": {"level": "high", "token": "s3cret"}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"level": "high", "token": "***"}}


def test_other_values_are_kept() -> None:
    redacted = redact(["linx", "example-settings", "--level", "high"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["linx", "example-settings", "--level", "high"]


def test_an_unset_secret_stays_null() -> None:
    redacted = redact([], {"example": {"level": "high", "token": None}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"level": "high", "token": None}}


def test_a_malformed_secret_url() -> None:
    redacted = redact(
        ["linx", "example-settings", "--token", "http://[ann:s3cret@proxy.test"],
        {},
        EXAMPLE_SECRETS,
    )

    assert redacted.command_argv == ["linx", "example-settings", "--token", "***"]


def test_a_secret_setting_that_is_not_a_string() -> None:
    redacted = redact([], {"example": {"token": 12345}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"token": "***"}}


def example_secret_names(temp_workspace: TempWorkspace) -> SecretNames:
    """As plan_crawl builds them from the test app's secret options, which its adapter reads."""
    group = cast(OpenLinxGroup, typer.main.get_group(example_app()))
    request = CrawlRequest(
        seed="http://site.test/",
        cwd=temp_workspace.root,
        home=temp_workspace.home,
        workspace=None,
        command_argv=["linx", "crawl", "http://site.test/"],
        flags={},
        secret_flags=secret_flags(group.commands["example-settings"], group.settings_tables),
    )
    return plan_crawl(request, group.settings_tables).new_crawl.secret_names


def test_the_secret_is_nowhere_in_the_file(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(
        temp_workspace,
        command_argv=["linx", "example-settings", "--token", "s3cret"],
        config={"example": {"token": "s3cret"}},
        secret_names=example_secret_names(temp_workspace),
    )
    # The scenario's closed writer: closing checkpoints the WAL into the file.
    with CrawlWriter(crawl.path, FakeClock()):
        pass
    files = [crawl.path, crawl.path.with_name(f"{crawl.path.name}-wal")]

    assert b"s3cret" not in b"".join(file.read_bytes() for file in files if file.exists())
