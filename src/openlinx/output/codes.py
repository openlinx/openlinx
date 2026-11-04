"""Exit codes and the list of diagnostic codes (design D5 of 010-add-workspace-and-cli-contract)."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Literal

from openlinx.naming import SETTINGS_FILE_NAME

type Level = Literal["error", "warning", "info"]
# How the warning log keeps a warning of the code: each one; once per the detail once_per
# names; counted, one entry whose count is the URLs it affected; pauses, one entry counting
# the network pauses; or for its run only, which a continue drops (design D10 of
# 020-add-crawl-core).
type Kept = Literal["each", "once", "counted", "pauses", "run"]


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
    INTERRUPTED = 130, "stopped by an interrupt, such as Ctrl+C"


@dataclass(frozen=True, kw_only=True)
class DiagnosticCode:
    code: str
    level: Level
    exit_code: ExitCode | None
    description: str
    kept: Kept = "each"
    once_per: str | None = None

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
    code: str,
    level: Level,
    exit_code: ExitCode | None,
    description: str,
    *,
    kept: Kept = "each",
    once_per: str | None = None,
) -> DiagnosticCode:
    if (kept == "once") != (once_per is not None):
        raise TypeError(f"{code}: a code kept once names its detail, and only it does")
    if any(declared.code == code for declared in DECLARED):
        raise TypeError(f"{code}: declared twice; declare a code once, in openlinx.output.codes")
    # An error without an exit code fails only when it is first raised, deep in its error path.
    if (level == "error") != (exit_code is not None):
        raise TypeError(f"{code}: an error code has an exit code, and only an error code does")
    declared = DiagnosticCode(
        code=code,
        level=level,
        exit_code=exit_code,
        description=description,
        kept=kept,
        once_per=once_per,
    )
    DECLARED.append(declared)
    return declared


USAGE_ERROR = _declare(
    "usage_error",
    "error",
    ExitCode.USAGE,
    "An unknown Command or flag, a missing argument, or a global flag before the Command name.",
)
INVALID_VALUE = _declare(
    "invalid_value",
    "error",
    ExitCode.USAGE,
    "A flag or argument value that is not allowed, or a value given with the settings that its "
    "setting refuses; details.key names the setting, when there is one.",
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
UNKNOWN_TABLE = _declare(
    "unknown_table",
    "error",
    ExitCode.USAGE,
    "A table name the public schema does not have; details.tables lists the tables.",
)
CRAWL_NOT_FOUND = _declare(
    "crawl_not_found",
    "error",
    ExitCode.NOT_FOUND,
    "No Crawl in the Workspace has the --crawl id, or no file exists at the --crawl path.",
)
CRAWL_BUSY = _declare(
    "crawl_busy",
    "error",
    ExitCode.BUSY,
    "Another connection held the crawl file for longer than a reader or the writer waits; "
    "details.file names it.",
)
CRAWL_FILE_INVALID = _declare(
    "crawl_file_invalid",
    "error",
    ExitCode.INCOMPATIBLE,
    "The selected file is not a readable crawl file, or a file selected by id or latest holds "
    "another id; details.file names it.",
)
CRAWL_SCHEMA_TOO_NEW = _declare(
    "crawl_schema_too_new",
    "error",
    ExitCode.INCOMPATIBLE,
    "The crawl file was made by a newer tool; details give both schema versions.",
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
INTERRUPTED = _declare(
    "interrupted",
    "error",
    ExitCode.INTERRUPTED,
    "Stopped by an interrupt: Ctrl+C, Ctrl+Break or a termination signal.",
)
INVALID_URL = _declare(
    "invalid_url",
    "error",
    ExitCode.USAGE,
    "A Seed that is not a valid http or https URL; details.reason says why.",
)
OPTION_CONFLICT = _declare(
    "option_conflict",
    "error",
    ExitCode.USAGE,
    "Two flags that cannot be given together, such as --subdomains with another --scope.",
)
SUBFOLDER_IS_ROOT = _declare(
    "subfolder_is_root",
    "error",
    ExitCode.USAGE,
    "--scope subfolder with a Seed whose folder is the root, such as a folder's URL without its "
    "trailing slash; details.suggested_seed holds the Seed with it, or null for a root Seed.",
)
INVALID_PATTERN = _declare(
    "invalid_pattern",
    "error",
    ExitCode.USAGE,
    "A URL pattern that is not a valid Python regular expression; details.pattern holds it.",
)
SEED_OUT_OF_SCOPE = _declare(
    "seed_out_of_scope",
    "error",
    ExitCode.USAGE,
    "The Seed is outside its own Scope: it matches an --exclude pattern, or no --include "
    "pattern; details.seed holds it.",
)
CRAWL_WRITE_FAILED = _declare(
    "crawl_write_failed",
    "error",
    ExitCode.IO,
    "Writing the crawl file failed during a Crawl, such as on a full disk; the Crawl ended "
    "failed, with write_failed, and details.error says what failed.",
)
SEED_UNREACHABLE = _declare(
    "seed_unreachable",
    "error",
    ExitCode.NETWORK,
    "The Seed's robots.txt or the Seed got no HTTP response, and its origin did not answer "
    "within --network-wait; the Crawl ended failed, and details.network_wait says how long it "
    "waited.",
)
SITE_UNREACHABLE = _declare(
    "site_unreachable",
    "error",
    ExitCode.NETWORK,
    "Internal requests in a row got no HTTP response, and the site did not answer within "
    "--network-wait; the Crawl ended failed, and details.network_wait says how long it waited.",
)
MAX_URLS_REACHED = _declare(
    "max_urls_reached",
    "warning",
    None,
    "The Crawl reached --max-urls and stopped with URLs left queued; the hint is the command "
    "that continues it with a higher limit.",
    kept="run",
)
SEED_BASE_MISMATCH = _declare(
    "seed_base_mismatch",
    "warning",
    None,
    "A www Seed whose Page names its apex host as the site; the hint gives the Seed on the apex "
    "host, and the Crawl went on in its Scope.",
    kept="once",
    once_per="seed",
)
SEED_BLOCKED_BY_ROBOTS_TXT = _declare(
    "seed_blocked_by_robots_txt",
    "warning",
    None,
    "robots.txt disallows the Seed for the robots user-agent token, so it was not requested; "
    "the hint names --ignore-robots, and details.seed holds the Seed.",
    kept="once",
    once_per="seed",
)
ROBOTS_UNREACHABLE = _declare(
    "robots_unreachable",
    "warning",
    None,
    "The robots.txt of an Internal origin answered with a server error or 429, so none of its "
    "URLs was requested, or under --ignore-robots all were, without its rules; the hint names "
    "--ignore-robots unless it was given, and details.origin, details.host and "
    "details.status_code say which.",
    kept="once",
    once_per="host",
)
ROBOTS_REDIRECT_FAILED = _declare(
    "robots_redirect_failed",
    "warning",
    None,
    "The robots.txt of an Internal origin redirected to a URL that got no HTTP response, so "
    "robots.txt counts as missing and every URL of the origin is allowed; details.origin, "
    "details.host, details.target and details.fetch_error say which.",
    kept="once",
    once_per="origin",
)
POSSIBLE_BLOCKING = _declare(
    "possible_blocking",
    "warning",
    None,
    "10 responses in a row from an Internal host had status 403 or 429, so it may be "
    "blocking the Crawl, which went on; the hint names --rate and --concurrency, and "
    "details.host says which host, and details.count is the length of the run that raises it.",
    kept="once",
    once_per="host",
)
PARSE_FAILED = _declare(
    "parse_failed",
    "warning",
    None,
    "A registered extractor raised an error, or a Page's preparation gave nothing "
    "(body_too_large, worker_crashed, parse_timeout), so a Page was recorded without its "
    "output; details.count says for how many URLs, details.first_url for which first, and "
    "for an extractor's error details.error its text and details.at its file and line when "
    "the extractor's own file raised it.",
    kept="counted",
)
HANDLER_FAILED = _declare(
    "handler_failed",
    "warning",
    None,
    "A per-response handler raised an error, so the URL was recorded without that handler's "
    "rows; details.count says for how many URLs, details.first_url for which first, "
    "details.error the error's text and details.at its file and line when the handler's own "
    "file raised it.",
    kept="counted",
)
NETWORK_PAUSED = _declare(
    "network_paused",
    "warning",
    None,
    "Internal requests in a row got no HTTP response, so the Crawl paused until a probe of its "
    "Seed answered; details.count says how many times it paused, details.total_seconds for how "
    "long in all.",
    kept="pauses",
)
RECORD_FAILED = _declare(
    "record_failed",
    "warning",
    None,
    "The unit that records a URL failed with an error of one row, so the URL was recorded as an "
    "error without the URLs found on it; details.count says for how many URLs, "
    "details.first_url for which first.",
    kept="counted",
)
WORKSPACE_NESTED = _declare(
    "workspace_nested", "warning", None, "The new Workspace is inside another Workspace."
)
STORE_WAL_UNAVAILABLE = _declare(
    "store_wal_unavailable",
    "warning",
    None,
    "The new crawl file uses a rollback journal, because WAL is unsafe or refused in its "
    "folder; details.path names the folder.",
)
MORE_ITEMS = _declare(
    "more_items",
    "info",
    None,
    "More items exist than were printed; details.next_cursor gives the next page.",
)
