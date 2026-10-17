"""The Crawl's warning log: every warning kept once, counted ones with their count (020 D10)."""

from dataclasses import replace
from typing import Any, Protocol

from spider.crawl.urls import NormalizedUrl
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter


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
        # Each warning is written once per code and host (design D10).
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
        """Where the warning is kept: a warning already written for its code and host is
        kept once, and a count goes on it."""
        key = (diagnostic.code, diagnostic.details.get("host"))
        index = self._written.get(key)
        if index is None:
            index = self._written[key] = len(self._warnings)
            self._warnings.append(diagnostic)
            self._reporter.warn(diagnostic)
        return index

    def event(self, name: str, **data: Any) -> None:
        self._reporter.event(name, **data)
