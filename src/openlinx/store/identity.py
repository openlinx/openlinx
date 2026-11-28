"""Keep the selected Crawl's filesystem and stored identities aligned."""

from pathlib import Path

from openlinx.output.codes import CRAWL_FILE_INVALID, CRAWL_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.records import CrawlFileIdentity


def identify_file(path: Path) -> CrawlFileIdentity:
    identity, _ = _identity_and_links(path)
    return identity


def _identity_and_links(path: Path) -> tuple[CrawlFileIdentity, int]:
    resolved = path.resolve(strict=True)
    status = resolved.stat()
    return CrawlFileIdentity(resolved, status.st_dev, status.st_ino), status.st_nlink


def verify_file_identity(
    path: Path, expected: CrawlFileIdentity | None, *, at: Path, single_link: bool = False
) -> CrawlFileIdentity:
    """Verify the target at `at` while naming the originally selected path in diagnostics."""
    try:
        actual, links = _identity_and_links(at)
    except OSError as error:
        raise _changed_file(path) from error
    if expected is not None and actual != expected:
        raise _changed_file(path)
    if single_link:
        check_single_link(path, links)
    return actual


def check_single_link(path: Path, links: int) -> None:
    """Refuse alternate filenames that would give SQLite different journal paths."""
    if links > 1:
        raise OpenLinxError(
            CRAWL_NOT_WRITABLE,
            f"The crawl file {path} has multiple hard links.",
            hint="Remove the extra hard links while the Crawl is closed.",
            details={"file": str(path)},
        )


def check_crawl_id(path: Path, expected: str, found: str) -> None:
    if found != expected:
        raise OpenLinxError(
            CRAWL_FILE_INVALID,
            f"The crawl file {path} holds the Crawl {found}, not {expected}.",
            hint=f"Give its path to read it as {found}.",
            details={"file": str(path), "expected_id": expected, "found_id": found},
        )


def _changed_file(path: Path) -> OpenLinxError:
    return OpenLinxError(
        CRAWL_NOT_WRITABLE,
        f"The selected crawl file {path} has changed or is unavailable.",
        hint="Select the crawl file again before continuing it.",
        details={"file": str(path)},
    )
