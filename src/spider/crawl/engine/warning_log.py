"""The warning log: each warning kept once per what its code names (020-add-crawl-core D10)."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from spider.crawl.urls import NormalizedUrl
from spider.output.codes import DECLARED
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter

# A code without a detail is written each time it is given (design D10).
_ONCE_PER: Mapping[str, str] = {
    code.code: code.once_per for code in DECLARED if code.once_per is not None
}


class WarningLog:
    """The Crawl's Reporter: passes everything on, and keeps the warnings for the result."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter
        self._warnings: list[Diagnostic] = []
        self._written: dict[tuple[str, object], int] = {}
        # By code: where a counted warning is kept, and how many URLs it affected so far.
        self._counted: dict[str, tuple[int, int]] = {}
        # Where network_paused is kept, how many pauses and how many seconds in all (D10).
        self._pauses: tuple[int, int, float] | None = None

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        warnings = list(self._warnings)
        for index, count in self._counted.values():
            kept = warnings[index]
            warnings[index] = replace(kept, details={**kept.details, "count": count})
        if self._pauses is not None:
            index, count, seconds = self._pauses
            kept = warnings[index]
            details = {**kept.details, "count": count, "total_seconds": round(seconds, 3)}
            warnings[index] = replace(kept, details=details)
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
        self._counted[diagnostic.code] = (self._keep(first), 1)

    def count_pause(self, diagnostic: Diagnostic, seconds: float) -> None:
        """Counts one more pause of `seconds` for network_paused, which counts pauses, not
        URLs; only the first is written to stderr."""
        if self._pauses is not None:
            index, count, total = self._pauses
            self._pauses = (index, count + 1, total + seconds)
            return
        first = replace(
            diagnostic,
            details={**diagnostic.details, "count": 1, "total_seconds": round(seconds, 3)},
        )
        self._pauses = (self._keep(first), 1, seconds)

    def _write(self, diagnostic: Diagnostic) -> int:
        """Where the warning is kept: one already written for the detail its code names is
        kept once."""
        detail = _ONCE_PER.get(diagnostic.code)
        if detail is None:
            return self._keep(diagnostic)
        key = (diagnostic.code, diagnostic.details.get(detail))
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
