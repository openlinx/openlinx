"""Exit codes, and errors bound to them (design D5 of 010-add-workspace-and-cli-contract)."""

from collections.abc import Mapping
from enum import IntEnum
from typing import Any


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
    ExitCode.CONFIG: "spider.toml or a setting is invalid",
    ExitCode.NOT_FOUND: "a Workspace, Crawl or item named on the command line does not exist",
    ExitCode.BUSY: "another process holds the Crawl",
    ExitCode.INCOMPATIBLE: "the crawl file cannot be used by this version",
    ExitCode.IO: "reading or writing a file or folder failed",
    ExitCode.NETWORK: "the network or a required host cannot be reached",
    ExitCode.INTERNAL: "an unexpected failure, which is a bug in the tool",
    ExitCode.INTERRUPTED: "stopped with Ctrl+C",
}


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
        self.code = code
        self.message = message
        self.hint = hint
        self.details = dict(details or {})


class UsageError(SpiderError):
    exit_code = ExitCode.USAGE
