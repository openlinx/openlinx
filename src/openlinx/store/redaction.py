"""Redact secret settings and credentials before recording Crawl data."""

from base64 import b64encode
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from yarl import URL

from openlinx.proxy_urls import proxy_url, split_absolute_url
from openlinx.store.records import SecretNames
from openlinx.workspace.tables import SecretPolicy, SecretSettings

REDACTED = "***"


@dataclass(frozen=True)
class Redacted:
    command_argv: list[str]
    config: dict[str, Any]


@dataclass(frozen=True)
class SecretValues:
    """The values of a Crawl's secret settings, for text that may quote one, such as a hook's
    error (023-fix-code-audit D3)."""

    values: tuple[str, ...] = ()

    def redact(self, text: str, *, truncated: bool = False) -> str:
        # Replacement markers can themselves match a secret: find spans before rendering.
        spans: list[tuple[int, int]] = []
        for value in self.values:
            if not value:
                continue
            start = text.find(value)
            while start != -1:
                spans.append((start, start + len(value)))
                start = text.find(value, start + 1)
            if truncated and (length := _secret_prefix_suffix(text, value)):
                spans.append((len(text) - length, len(text)))
        return _redact_spans(text, spans)


def _secret_prefix_suffix(text: str, secret: str) -> int:
    # Only a proper prefix could continue beyond the cut. KMP bounds both the copied
    # secret prefix and the work by the carried text, even for repetitive secrets.
    prefix = secret[: min(len(secret) - 1, len(text))]
    if not prefix:
        return 0
    fallback = [0] * len(prefix)
    matched = 0
    for index in range(1, len(prefix)):
        while matched and prefix[index] != prefix[matched]:
            matched = fallback[matched - 1]
        if prefix[index] == prefix[matched]:
            matched += 1
        fallback[index] = matched
    matched = 0
    for character in text:
        while matched and (matched == len(prefix) or character != prefix[matched]):
            matched = fallback[matched - 1]
        if character == prefix[matched]:
            matched += 1
    return matched


def _redact_spans(text: str, spans: list[tuple[int, int]]) -> str:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    pieces: list[str] = []
    previous = 0
    for start, end in merged:
        pieces.extend((text[previous:start], REDACTED))
        previous = end
    pieces.append(text[previous:])
    return "".join(pieces)


def secret_values(config: Mapping[str, Any], settings: SecretSettings) -> SecretValues:
    """From the config that the recorded one redacts, so both hide the same secrets."""
    found: set[str] = set()
    for path, policy in _setting_paths(settings):
        value = _setting_value(config, path)
        if policy == "header":
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                name, colon, content = entry.partition(":")
                if colon and not is_sensitive_header(name):
                    continue
                secret = content.strip(" \t") if colon else entry
                if secret:
                    found.add(secret)
        elif isinstance(value, list):
            # The config hides the whole list. A diagnostic may quote just one element.
            found.update(item for item in value if isinstance(item, str) and item)
        elif isinstance(value, str) and value:
            url = _secret_url(value, policy)
            found.update((value, url))
            auth = path == ("crawl", "auth")
            password = value.partition(":")[2] if auth else _password(url)
            if password:
                found.add(password)
                if (policy is True or policy in ("url", "proxy")) and (
                    decoded := _decoded_url_password(url)
                ):
                    found.add(decoded)
            if auth:
                # Match the exact UTF-8 wire bytes without re-raising invalid-input errors.
                try:
                    encoded = b64encode(value.encode("utf-8")).decode("ascii")
                except UnicodeEncodeError:
                    continue
                found.update((encoded, f"Basic {encoded}"))
    return SecretValues(tuple(sorted(found, key=len, reverse=True)))


def _setting_paths(
    settings: SecretSettings, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[tuple[str, ...], SecretPolicy]]:
    for key, policy in settings.items():
        if isinstance(policy, Mapping):
            yield from _setting_paths(policy, (*prefix, key))
        elif policy:
            # Callers can still supply flat policies as table.key. Nested keys can contain dots.
            yield (*prefix, key) if prefix else tuple(key.split(".", 1)), policy


def _setting_value(config: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = config
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _secret_url(value: str, policy: SecretPolicy) -> str:
    if policy == "proxy":
        return proxy_url(value) or value
    return value


def _password(value: str) -> str | None:
    try:
        return urlsplit(value).password
    except ValueError:
        return None


def _decoded_url_password(value: str) -> str | None:
    # The HTTP client decodes URL credentials. Errors may quote the decoded password alone.
    try:
        return URL(value).password
    except ValueError:
        # Keep the spelling collected from the input even if the client rejects the URL.
        return None


def redact(argv: Sequence[str], config: Mapping[str, Any], secrets: SecretNames) -> Redacted:
    return Redacted(
        _redact_argv(argv, secrets.flags),
        _redact_config(config, dict(_setting_paths(secrets.settings))),
    )


def _redact_argv(argv: Sequence[str], flags: Mapping[str, SecretPolicy]) -> list[str]:
    redacted = list(argv)
    value_policy: SecretPolicy | None = None
    for index, argument in enumerate(argv):
        # A split value may look like another option; consume it exactly once.
        if value_policy is not None:
            redacted[index] = _redact_value(argument, value_policy)
            value_policy = None
            continue
        flag, joined, value = argument.partition("=")
        if joined and flag in flags:
            redacted[index] = f"{flag}={_redact_value(value, flags[flag])}"
        elif argument in flags:
            value_policy = flags[argument]
    return redacted


def _redact_config(
    config: Mapping[str, Any],
    settings: Mapping[tuple[str, ...], SecretPolicy],
    prefix: tuple[str, ...] = (),
) -> dict[str, Any]:
    redacted = {}
    for key, value in config.items():
        path = (*prefix, key)
        if policy := settings.get(path):
            value = _redact_setting(value, policy)
        elif isinstance(value, Mapping):
            value = _redact_config(value, settings, path)
        redacted[key] = value
    return redacted


def _redact_setting(value: Any, policy: SecretPolicy) -> Any:
    # An unset secret stays None: there is nothing to hide, and *** would claim a value.
    if value is None or policy is False:
        return value
    if policy == "header" and isinstance(value, list):
        return [_redact_setting(item, policy) for item in value]
    return _redact_value(value, policy) if isinstance(value, str) else REDACTED


def is_sensitive_header(name: str) -> bool:
    lowered = name.casefold()
    return lowered == "cookie" or any(
        part in lowered for part in ("auth", "token", "secret", "key", "password")
    )


def _redact_value(value: str, policy: SecretPolicy) -> str:
    if policy is False:
        return value
    if policy == "whole":
        return REDACTED
    if policy == "header":
        name, colon, _ = value.partition(":")
        if not colon:
            return REDACTED
        return f"{name}: {REDACTED}" if is_sensitive_header(name) else value
    keep_url = policy in ("url", "proxy")
    try:
        parts = split_absolute_url(_secret_url(value, policy)) if keep_url else urlsplit(value)
    except ValueError:
        return REDACTED
    if parts is None:
        return REDACTED
    if parts.password is None:
        return value if keep_url else REDACTED
    host = parts.netloc.rpartition("@")[2]
    netloc = f"{parts.username}:{REDACTED}@{host}"
    if policy == "proxy":
        # The authority with userinfo can only occur after the scheme, if one was supplied.
        return value.replace(parts.netloc, netloc, 1)
    return urlunsplit(parts._replace(netloc=netloc))
