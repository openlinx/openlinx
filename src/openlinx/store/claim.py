"""An OS claim outlives every writer of a Crawl (060-add-crawl-control D12)."""

import errno
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import CRAWL_LOCKED
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.records import CrawlFile

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


@contextmanager
def claim_writer(crawl_file: CrawlFile, *, exclusive: bool = False) -> Iterator[None]:
    path = crawl_file.path.with_name(f"{crawl_file.id}.lock")
    with path.open("x+b" if exclusive else "a+b") as lock:
        lock.seek(0)
        try:
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            raise OpenLinxError(
                CRAWL_LOCKED,
                f"Another process holds the writer claim for Crawl {crawl_file.id}.",
                hint=f"Check the Crawl with: {COMMAND_NAME} status --crawl {crawl_file.id}",
                details={"file": str(crawl_file.path)},
            ) from error
        try:
            yield
        finally:
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
