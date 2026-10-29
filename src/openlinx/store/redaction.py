"""Redacting secrets before a Crawl records them (design D7 of 015-add-crawl-store)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from openlinx.store.records import SecretNames

REDACTED = "***"


@dataclass(frozen=True)
class Redacted:
    command_argv: list[str]
    config: dict[str, Any]


def redact(argv: Sequence[str], config: Mapping[str, Any], secrets: SecretNames) -> Redacted:
    return Redacted(_redact_argv(argv, secrets.flags), _redact_config(config, secrets.settings))


def _redact_argv(argv: Sequence[str], flags: frozenset[str]) -> list[str]:
    redacted = list(argv)
    for index, argument in enumerate(argv):
        flag, joined, value = argument.partition("=")
        if joined and flag in flags:
            redacted[index] = f"{flag}={_redact_value(value)}"
        elif index > 0 and argv[index - 1] in flags:
            redacted[index] = _redact_value(argument)
    return redacted


def _redact_config(config: Mapping[str, Any], settings: frozenset[str]) -> dict[str, Any]:
    return {
        table: {
            key: _redact_setting(value) if f"{table}.{key}" in settings else value
            for key, value in values.items()
        }
        for table, values in config.items()
    }


def _redact_setting(value: Any) -> Any:
    # An unset secret stays None: there is nothing to hide, and *** would claim a value.
    if value is None:
        return None
    return _redact_value(value) if isinstance(value, str) else REDACTED


def _redact_value(value: str) -> str:
    try:
        parts = urlsplit(value)
        password = parts.password
    except ValueError:
        # A malformed URL, such as an unclosed [ in its host: nothing of it is kept.
        return REDACTED
    if password is None:
        return REDACTED
    host = parts.netloc.rpartition("@")[2]
    return urlunsplit(parts._replace(netloc=f"{parts.username}:{REDACTED}@{host}"))
