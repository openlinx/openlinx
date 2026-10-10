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
