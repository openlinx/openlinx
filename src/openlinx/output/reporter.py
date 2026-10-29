"""How services report warnings and progress (design D3 of 010-add-workspace-and-cli-contract)."""

from typing import Any, Protocol

from openlinx.clock import Clock
from openlinx.output.diagnostics import Diagnostic
from openlinx.output.events import event_line
from openlinx.output.writer import Output


class Reporter(Protocol):
    def warn(self, diagnostic: Diagnostic) -> None: ...

    def event(self, name: str, **data: Any) -> None: ...


class CliReporter:
    def __init__(self, output: Output, clock: Clock) -> None:
        self._output = output
        self._clock = clock

    def warn(self, diagnostic: Diagnostic) -> None:
        self._output.diagnostic(diagnostic)

    def event(self, name: str, **data: Any) -> None:
        self._output.stderr_line(event_line(name, data, self._clock.now()))


class Collected:
    def __init__(self) -> None:
        self.warnings: list[Diagnostic] = []
        self.events: list[tuple[str, dict[str, Any]]] = []

    def warn(self, diagnostic: Diagnostic) -> None:
        self.warnings.append(diagnostic)

    def event(self, name: str, **data: Any) -> None:
        self.events.append((name, data))
