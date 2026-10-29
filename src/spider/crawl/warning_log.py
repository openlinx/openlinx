"""The warning log: each warning kept once per what its code names (020-add-crawl-core D10)."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Protocol

from spider.crawl.urls import NormalizedUrl
from spider.output.codes import (
    HANDLER_FAILED,
    PARSE_FAILED,
    POSSIBLE_BLOCKING,
    RECORD_FAILED,
    ROBOTS_UNREACHABLE,
    SEED_BASE_MISMATCH,
    SEED_BLOCKED_BY_ROBOTS_TXT,
)
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter

# The detail that makes two warnings of a code one, or None for one per code; a code not
# named here is written each time it is given (design D10).
_KEPT_ONCE_PER: Mapping[str, str | None] = {
    ROBOTS_UNREACHABLE.code: "host",
    POSSIBLE_BLOCKING.code: "host",
    SEED_BLOCKED_BY_ROBOTS_TXT.code: "seed",
    SEED_BASE_MISMATCH.code: "seed",
    PARSE_FAILED.code: None,
    HANDLER_FAILED.code: None,
    RECORD_FAILED.code: None,
}


class CrawlReporter(Protocol):
    """A Reporter that also counts the counted warnings of D16."""

    def warn(self, diagnostic: Diagnostic) -> None: ...

    def event(self, name: str, **data: Any) -> None: ...

    def count(self, diagnostic: Diagnostic, url: NormalizedUrl) -> None: ...


class WarningLog:
    """The Crawl's Reporter: passes everything on, and keeps the warnings for the result."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter
        self._warnings: list[Diagnostic] = []
        self._written: dict[tuple[str, object], int] = {}
        # By code: where a counted warning is kept, and how many URLs it affected so far.
        self._counted: dict[str, tuple[int, int]] = {}

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        warnings = list(self._warnings)
        for index, count in self._counted.values():
            kept = warnings[index]
            warnings[index] = replace(kept, details={**kept.details, "count": count})
        return tuple(warnings)

    def warn(self, diagnostic: Diagnostic) -> None:
        self._write(diagnostic)

    def count(self, diagnostic: Diagnostic, url: NormalizedUrl) -> None:
        """Counts one more URL for a counted warning; only the first is written to stderr."""
        counted = self._counted.get(diagnostic.code)
        if counted is not None:
            index, count = counted
            self._counted[diagnostic.code] = (index, count + 1)
            return
        first = replace(diagnostic, details={**diagnostic.details, "count": 1, "first_url": url})
        self._counted[diagnostic.code] = (self._write(first), 1)

    def _write(self, diagnostic: Diagnostic) -> int:
        """Where the warning is kept: a warning already written for what its code names is
        kept once, and a count goes on it."""
        if diagnostic.code not in _KEPT_ONCE_PER:
            return self._keep(diagnostic)
        detail = _KEPT_ONCE_PER[diagnostic.code]
        key = (diagnostic.code, None if detail is None else diagnostic.details.get(detail))
        index = self._written.get(key)
        if index is None:
            index = self._written[key] = self._keep(diagnostic)
        return index

    def _keep(self, diagnostic: Diagnostic) -> int:
        self._warnings.append(diagnostic)
        self._reporter.warn(diagnostic)
        return len(self._warnings) - 1

    def event(self, name: str, **data: Any) -> None:
        self._reporter.event(name, **data)
