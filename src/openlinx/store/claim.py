"""An OS claim outlives every writer of a Crawl (060-add-crawl-control D12)."""

import errno
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import CRAWL_LOCKED, CRAWL_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.identity import check_single_link, verify_file_identity
from openlinx.store.records import CrawlFile

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


_WINERROR_CANT_RESOLVE_FILENAME = 1921


@contextmanager
def claim_writer(crawl_file: CrawlFile, *, exclusive: bool = False) -> Iterator[Path]:
    crawl_path = crawl_file.path
    try:
        if not exclusive:
            # A claim probe can precede file creation.
            try:
                crawl_path = crawl_path.resolve()
            except RuntimeError as error:
                # Python 3.12 raises a plain RuntimeError for a symlink loop.
                context = error.__context__
                if type(error) is not RuntimeError or not isinstance(context, OSError):
                    raise
                if (
                    context.errno != errno.ELOOP
                    and getattr(context, "winerror", None) != _WINERROR_CANT_RESOLVE_FILENAME
                ):
                    raise
                raise _unwritable_claim(crawl_file) from error
            # On newer Python versions, non-strict resolve leaves a loop for stat to reject.
            with suppress(FileNotFoundError):
                check_single_link(crawl_file.path, crawl_path.stat().st_nlink)
            if crawl_file.identity is not None:
                verify_file_identity(crawl_file.path, crawl_file.identity, at=crawl_path)
        lock_path = crawl_path.with_name(f"{crawl_file.id}.lock")
        lock = lock_path.open("x+b" if exclusive else "a+b")
    except OSError as error:
        if exclusive:
            raise
        raise _unwritable_claim(crawl_file) from error
    with _claim_cleanup(crawl_file, "close", lock.close):
        try:
            lock.seek(0)
        except OSError as error:
            if exclusive:
                raise
            raise _unwritable_claim(crawl_file, "position") from error
        fd = lock.fileno()
        try:
            if sys.platform == "win32":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                if exclusive:
                    raise
                raise _unwritable_claim(crawl_file, "acquire") from error
            raise OpenLinxError(
                CRAWL_LOCKED,
                f"Another process holds the writer claim for Crawl {crawl_file.id}.",
                hint=f"Check the Crawl with: {COMMAND_NAME} status --crawl {crawl_file.id}",
                details={"file": str(crawl_file.path)},
            ) from error
        with _claim_cleanup(crawl_file, "release", lambda: _unlock_claim(fd)):
            yield crawl_path


def _unlock_claim(fd: int) -> None:
    if sys.platform == "win32":
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def _claim_cleanup(
    crawl_file: CrawlFile, action: str, cleanup: Callable[[], None]
) -> Iterator[None]:
    try:
        yield
    except BaseException:
        # A cleanup failure must not replace the original failure. Close still releases the lock.
        with suppress(OSError):
            cleanup()
        raise
    else:
        try:
            cleanup()
        except OSError as error:
            raise _unwritable_claim(crawl_file, action) from error


def _unwritable_claim(crawl_file: CrawlFile, action: str = "open") -> OpenLinxError:
    return OpenLinxError(
        CRAWL_NOT_WRITABLE,
        f"Cannot {action} the writer claim for Crawl {crawl_file.id}.",
        hint="Check that the crawl file's folder and lock file are writable.",
        details={"file": str(crawl_file.path)},
    )
