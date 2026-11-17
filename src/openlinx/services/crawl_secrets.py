"""Validate fresh secrets for a continue and restore recorded sensitive header slots."""

from collections import Counter
from urllib.parse import unquote, urlsplit

from openlinx.crawl.setting_rules import as_headers
from openlinx.output.codes import INVALID_VALUE, SECRETS_REQUIRED
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.redaction import REDACTED, is_sensitive_header


def check_fresh_proxy(proxy: str | None) -> None:
    """Refuse a malformed URL or a replay of a marker before opening resources."""
    if proxy is None:
        return
    try:
        parts = urlsplit(proxy)
        _ = parts.port
        if (
            parts.scheme
            and parts.hostname not in (None, REDACTED)
            and not any(ord(char) <= 32 for char in proxy)
            and unquote(parts.password or "") != REDACTED
        ):
            return
    except ValueError:
        pass
    raise OpenLinxError(
        INVALID_VALUE,
        "Invalid value for crawl.proxy: supply a valid proxy URL without redaction markers.",
        details={"key": "crawl.proxy"},
    )


def restored_headers(recorded: list[str], fresh: tuple[str, ...]) -> list[str]:
    """Match fresh values by case-insensitive name and occurrence, keeping recorded slots.

    Fresh entries cannot add headers or change harmless values. Empty values are explicit;
    the recording marker is reserved here even though it is a valid value for a new Crawl.
    """
    selected = as_headers(recorded)
    required = Counter(name.casefold() for name, _ in selected if is_sensitive_header(name))
    try:
        supplied = as_headers(list(fresh))
    except ValueError as error:
        raise _invalid_headers(str(error)) from error
    counts: Counter[str] = Counter()
    values: dict[tuple[str, int], str] = {}
    for name, value in supplied:
        key = name.casefold()
        if not is_sensitive_header(name) or counts[key] >= required[key] or value == REDACTED:
            raise _invalid_headers(
                "only fresh values for recorded sensitive occurrences are allowed"
            )
        values[key, counts[key]] = value
        counts[key] += 1
    if counts != required:
        raise OpenLinxError(
            SECRETS_REQUIRED,
            "Continuing this Crawl requires fresh sensitive header values.",
            hint="Supply fresh values through --header or crawl.header.",
        )
    restored: list[str] = []
    used: Counter[str] = Counter()
    for original, (name, _) in zip(recorded, selected, strict=True):
        if is_sensitive_header(name):
            key = name.casefold()
            restored.append(f"{name}: {values[key, used[key]]}")
            used[key] += 1
        else:
            restored.append(original)
    return restored


def _invalid_headers(reason: str) -> OpenLinxError:
    return OpenLinxError(
        INVALID_VALUE,
        f"Invalid value for crawl.header: {reason}.",
        hint="Supply fresh sensitive values matching the recorded header names and occurrences.",
        details={"key": "crawl.header"},
    )
