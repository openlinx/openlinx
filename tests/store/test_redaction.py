"""Redacting secrets (015-add-crawl-store, crawl-store)."""

from typing import cast

import typer

from spider.cli.options import secret_names
from spider.cli.runner import SpiderGroup
from spider.store.records import SecretNames
from spider.store.redaction import redact
from spider.store.writer import CrawlWriter
from tests.support.app import example_app
from tests.support.clock import FakeClock
from tests.support.crawls import create_any_crawl
from tests.support.workspace import TempWorkspace

# What the test app's example-settings Command declares secret.
EXAMPLE_SECRETS = SecretNames(
    flags=frozenset({"--token", "--api-key"}), settings=frozenset({"example.token"})
)


def test_secret_option_with_a_separate_value() -> None:
    redacted = redact(["spider", "example-settings", "--token", "s3cret"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["spider", "example-settings", "--token", "***"]


def test_secret_option_with_a_joined_value() -> None:
    redacted = redact(["spider", "example-settings", "--api-key=s3cret"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["spider", "example-settings", "--api-key=***"]


def test_a_url_keeps_everything_but_its_password() -> None:
    redacted = redact(
        ["spider", "example-settings", "--token", "http://ann:s3cret@proxy.test:8080"],
        {},
        EXAMPLE_SECRETS,
    )

    assert redacted.command_argv == [
        "spider",
        "example-settings",
        "--token",
        "http://ann:***@proxy.test:8080",
    ]


def test_secret_setting() -> None:
    redacted = redact([], {"example": {"level": "high", "token": "s3cret"}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"level": "high", "token": "***"}}


def test_other_values_are_kept() -> None:
    redacted = redact(["spider", "example-settings", "--level", "high"], {}, EXAMPLE_SECRETS)

    assert redacted.command_argv == ["spider", "example-settings", "--level", "high"]


def test_an_unset_secret_stays_null() -> None:
    redacted = redact([], {"example": {"level": "high", "token": None}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"level": "high", "token": None}}


def test_a_malformed_secret_url() -> None:
    redacted = redact(
        ["spider", "example-settings", "--token", "http://[ann:s3cret@proxy.test"],
        {},
        EXAMPLE_SECRETS,
    )

    assert redacted.command_argv == ["spider", "example-settings", "--token", "***"]


def test_a_secret_setting_that_is_not_a_string() -> None:
    redacted = redact([], {"example": {"token": 12345}}, EXAMPLE_SECRETS)

    assert redacted.config == {"example": {"token": "***"}}


def example_secret_names() -> SecretNames:
    """Read from the test app's declarations, as the adapter that creates a Crawl reads its own."""
    group = cast(SpiderGroup, typer.main.get_group(example_app()))
    return secret_names(group.commands["example-settings"], group.settings_tables)


def test_the_secret_is_nowhere_in_the_file(temp_workspace: TempWorkspace) -> None:
    crawl = create_any_crawl(
        temp_workspace,
        command_argv=["spider", "example-settings", "--token", "s3cret"],
        config={"example": {"token": "s3cret"}},
        secret_names=example_secret_names(),
    )
    with CrawlWriter(crawl.path, FakeClock()):
        pass
    files = [crawl.path, crawl.path.with_name(f"{crawl.path.name}-wal")]

    assert b"s3cret" not in b"".join(file.read_bytes() for file in files if file.exists())
