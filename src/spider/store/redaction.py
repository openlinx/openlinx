"""Redacting secrets before a Crawl records them (design D7 of 015-add-crawl-store)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from spider.store.records import SecretNames

REDACTED = "***"


@dataclass(frozen=True)
class Redacted:
    command_argv: list[str]
    config: dict[str, Any]


def redact(argv: Sequence[str], config: Mapping[str, Any], secrets: SecretNames) -> Redacted:
    return Redacted(_redact_argv(argv, secrets.flags), dict(config))


def _redact_argv(argv: Sequence[str], flags: frozenset[str]) -> list[str]:
    redacted = list(argv)
    for index, argument in enumerate(argv):
        flag, joined, _ = argument.partition("=")
        if joined and flag in flags:
            redacted[index] = f"{flag}={REDACTED}"
        elif index > 0 and argv[index - 1] in flags:
            redacted[index] = REDACTED
    return redacted
