"""The Crawl's warning log: every warning kept once, counted ones with their count (020 D10)."""

from dataclasses import replace
from typing import Any

from spider.crawl.urls import NormalizedUrl
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter


class WarningLog:
    """The Crawl's Reporter: passes everything on, and keeps the warnings for the result."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter
        self._warnings: list[Diagnostic] = []
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
        self._warnings.append(diagnostic)
        self._reporter.warn(diagnostic)

    def count(self, diagnostic: Diagnostic, url: NormalizedUrl) -> None:
        """Counts one more URL for a counted warning; only the first is written to stderr."""
        counted = self._counted.get(diagnostic.code)
        if counted is not None:
            index, count = counted
            self._counted[diagnostic.code] = (index, count + 1)
            return
        self._counted[diagnostic.code] = (len(self._warnings), 1)
        self.warn(replace(diagnostic, details={**diagnostic.details, "count": 1, "first_url": url}))

    def event(self, name: str, **data: Any) -> None:
        self._reporter.event(name, **data)
