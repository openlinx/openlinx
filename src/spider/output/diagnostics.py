"""Diagnostics, and errors bound to their code (design D5 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from spider.output.codes import DiagnosticCode, Level


@dataclass(frozen=True)
class Diagnostic:
    level: Level
    code: str
    message: str
    hint: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        code: DiagnosticCode,
        message: str,
        hint: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> "Diagnostic":
        return cls(code.level, code.code, message, hint, dict(details or {}))

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "details": dict(self.details),
        }


class SpiderError(Exception):
    def __init__(
        self,
        code: DiagnosticCode,
        message: str,
        hint: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if code.exit_code is None:
            raise TypeError(f"{code.code} is a {code.level}, not an error.")
        super().__init__(message)
        self.exit_code = code.exit_code
        self.diagnostic = Diagnostic.of(code, message, hint, details)

    @property
    def code(self) -> str:
        return self.diagnostic.code


@dataclass(frozen=True)
class Outcome:
    """A result that describes a failed outcome: it is printed, then its error ends the run."""

    result: Any
    error: SpiderError
