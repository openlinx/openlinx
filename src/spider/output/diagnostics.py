"""Exit codes, and errors bound to them (design D5 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal

from spider import APP_NAME


class ExitCode(IntEnum):
    OK = 0
    FAILED = 1
    USAGE = 2
    CONFIG = 3
    NOT_FOUND = 4
    BUSY = 5
    INCOMPATIBLE = 6
    IO = 7
    NETWORK = 8
    INTERNAL = 70
    INTERRUPTED = 130


EXIT_CODE_DESCRIPTIONS: Mapping[ExitCode, str] = {
    ExitCode.OK: "success",
    ExitCode.FAILED: "the Command ran but could not do everything asked; the error says what",
    ExitCode.USAGE: (
        "the command line is wrong: an unknown Command, flag or name, or a missing or invalid value"
    ),
    ExitCode.CONFIG: f"{APP_NAME}.toml or a setting is invalid",
    ExitCode.NOT_FOUND: "a Workspace, Crawl or item named on the command line does not exist",
    ExitCode.BUSY: "another process holds the Crawl",
    ExitCode.INCOMPATIBLE: "the crawl file cannot be used by this version",
    ExitCode.IO: "reading or writing a file or folder failed",
    ExitCode.NETWORK: "the network or a required host cannot be reached",
    ExitCode.INTERNAL: "an unexpected failure, which is a bug in the tool",
    ExitCode.INTERRUPTED: "stopped with Ctrl+C",
}


@dataclass(frozen=True)
class Diagnostic:
    level: Literal["error", "warning", "info"]
    code: str
    message: str
    hint: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


class SpiderError(Exception):
    exit_code: ExitCode

    def __init__(
        self,
        code: str,
        message: str,
        hint: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.diagnostic = Diagnostic("error", code, message, hint, dict(details or {}))

    @property
    def code(self) -> str:
        return self.diagnostic.code


@dataclass(frozen=True)
class Outcome:
    """A result that describes a failed outcome: it is printed, then its error ends the run."""

    result: Any
    error: SpiderError


class FailedError(SpiderError):
    exit_code = ExitCode.FAILED


class UsageError(SpiderError):
    exit_code = ExitCode.USAGE


class NotFoundError(SpiderError):
    exit_code = ExitCode.NOT_FOUND


class FileSystemError(SpiderError):
    exit_code = ExitCode.IO


class ConfigError(SpiderError):
    exit_code = ExitCode.CONFIG
