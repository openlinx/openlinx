"""The warning log: each warning kept once per what its code names (020-add-crawl-core D10)."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from spider.crawl.urls import NormalizedUrl
from spider.output.codes import DECLARED
from spider.output.diagnostics import Diagnostic
from spider.output.reporter import Reporter

# A code without a detail is written each time it is given (design D10).
_ONCE_PER: Mapping[str, str] = {
    code.code: code.once_per for code in DECLARED if code.once_per is not None
}


@dataclass(frozen=True, slots=True)
class _Pauses:
    """Where network_paused is kept, how many pauses and how many seconds in all (D10)."""

    index: int
    count: int
    seconds: float


class WarningLog:
    """The Crawl's Reporter: passes everything on, and keeps the warnings for the result."""

    def __init__(self, reporter: Reporter) -> None:
        self._reporter = reporter
        self._warnings: list[Diagnostic] = []
        self._written: dict[tuple[str, object], int] = {}
        # By code: where a counted warning is kept, and how many URLs it affected so far.
        self._counted: dict[str, tuple[int, int]] = {}
        self._pauses: _Pauses | None = None

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        warnings = list(self._warnings)
        for index, count in self._counted.values():
            kept = warnings[index]
            warnings[index] = replace(kept, details={**kept.details, "count": count})
        if (pauses := self._pauses) is not None:
            kept = warnings[pauses.index]
            details = {
                **kept.details,
                "count": pauses.count,
                "total_seconds": round(pauses.seconds, 3),
            }
            warnings[pauses.index] = replace(kept, details=details)
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

    def pause_began(self, diagnostic: Diagnostic) -> None:
        """Counts one more pause for network_paused, which counts pauses, not URLs; only the
        first is written to stderr, as it begins."""
        if self._pauses is not None:
            self._pauses = replace(self._pauses, count=self._pauses.count + 1)
            return
        details = {**diagnostic.details, "count": 1, "total_seconds": 0.0}
        first = replace(diagnostic, details=details)
        self._pauses = _Pauses(self._keep(first), 1, 0.0)

    def pause_ended(self, seconds: float) -> None:
        if self._pauses is None:
            raise RuntimeError("a network pause ended that never began")
        self._pauses = replace(self._pauses, seconds=self._pauses.seconds + seconds)

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
