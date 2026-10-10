"""Redacting secrets (015-add-crawl-store, crawl-store)."""

from spider.store.records import SecretNames
from spider.store.redaction import redact

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
