"""Exit codes and the list of diagnostic codes (design D5 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Literal

from spider.naming import SETTINGS_FILE_NAME

type Level = Literal["error", "warning", "info"]


class ExitCode(IntEnum):
    description: str

    def __new__(cls, value: int, description: str) -> "ExitCode":
        member = int.__new__(cls, value)
        member._value_ = value
        member.description = description
        return member

    OK = 0, "success"
    FAILED = 1, "the Command ran but could not do everything asked; the error says what"
    USAGE = (
        2,
        "the command line is wrong: an unknown Command, flag or name, "
        "or a missing or invalid value",
    )
    CONFIG = 3, f"{SETTINGS_FILE_NAME} or a setting is invalid"
    NOT_FOUND = 4, "a Workspace, Crawl or item named on the command line does not exist"
    BUSY = 5, "another process holds the Crawl"
    INCOMPATIBLE = 6, "the crawl file cannot be used by this version"
    IO = 7, "reading or writing a file or folder failed"
    NETWORK = 8, "the network or a required host cannot be reached"
    INTERNAL = 70, "an unexpected failure, which is a bug in the tool"
    INTERRUPTED = 130, "stopped with Ctrl+C"


@dataclass(frozen=True)
class DiagnosticCode:
    code: str
    level: Level
    exit_code: ExitCode | None
    description: str

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "exit_code": None if self.exit_code is None else self.exit_code.value,
            "description": self.description,
        }


# Codes are listed in the order they are declared, so related codes stay together.
DECLARED: list[DiagnosticCode] = []


def _declare(
    code: str, level: Level, exit_code: ExitCode | None, description: str
) -> DiagnosticCode:
    declared = DiagnosticCode(code, level, exit_code, description)
    DECLARED.append(declared)
    return declared


USAGE_ERROR = _declare(
    "usage_error",
    "error",
    ExitCode.USAGE,
    "An unknown Command or flag, a missing argument, or a global flag before the Command name.",
)
INVALID_VALUE = _declare(
    "invalid_value", "error", ExitCode.USAGE, "A flag or argument value that is not allowed."
)
UNKNOWN_FIELD = _declare(
    "unknown_field", "error", ExitCode.USAGE, "A --fields name the Command does not have."
)
INVALID_CURSOR = _declare(
    "invalid_cursor",
    "error",
    ExitCode.USAGE,
    "A --cursor made by a different request, or altered.",
)
SETTINGS_INVALID = _declare(
    "settings_invalid",
    "error",
    ExitCode.CONFIG,
    f"{SETTINGS_FILE_NAME} cannot be read or breaks the settings rules; "
    "details.errors lists each problem.",
)
WORKSPACE_NOT_FOUND = _declare(
    "workspace_not_found", "error", ExitCode.NOT_FOUND, "The --workspace folder does not exist."
)
WORKSPACE_NOT_WRITABLE = _declare(
    "workspace_not_writable",
    "error",
    ExitCode.IO,
    "The Workspace folder or its data folder cannot be created or written.",
)
NO_CRAWLS = _declare(
    "no_crawls", "error", ExitCode.NOT_FOUND, "The Workspace has no Crawl to read yet."
)
CRAWL_NOT_FOUND = _declare(
    "crawl_not_found", "error", ExitCode.NOT_FOUND, "No Crawl in the Workspace has the --crawl id."
)
CRAWL_FILE_INVALID = _declare(
    "crawl_file_invalid",
    "error",
    ExitCode.INCOMPATIBLE,
    "The selected file is not a readable crawl file; details.file names it.",
)
CRAWL_NOT_WRITABLE = _declare(
    "crawl_not_writable",
    "error",
    ExitCode.IO,
    "The crawl file cannot be written; details.file names it.",
)
INTERNAL_ERROR = _declare(
    "internal_error",
    "error",
    ExitCode.INTERNAL,
    "An unexpected failure, which is a bug; details.traceback holds the Python traceback.",
)
INTERRUPTED = _declare("interrupted", "error", ExitCode.INTERRUPTED, "Stopped with Ctrl+C.")
WORKSPACE_NESTED = _declare(
    "workspace_nested", "warning", None, "The new Workspace is inside another Workspace."
)
MORE_ITEMS = _declare(
    "more_items",
    "info",
    None,
    "More items exist than were printed; details.next_cursor gives the next page.",
)
