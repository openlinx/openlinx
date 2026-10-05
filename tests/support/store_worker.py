"""A writer in its own process, run and killed by durability tests (015-add-crawl-store)."""

import subprocess
import sys
import threading
from pathlib import Path
from types import TracebackType
from typing import Self

from spider.store.connections import connect
from spider.store.writer import CrawlWriter
from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.clock import FakeClock
from tests.support.crawls import insert_seed

READY = "ok"


class StoreWorker:
    """Each command returns once the worker has answered it, so a test never sleeps.

    Use it as a context manager: the worker is killed on the way out, even when a test fails.
    """

    def __init__(self, crawl_file: Path) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.support.store_worker", str(crawl_file)],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self._send("open")

    def insert(self, *positions: int) -> None:
        """One unit per Seed, each inserting the Seed at that position."""
        for position in positions:
            self._send(f"insert {position}")

    def flush(self) -> None:
        self._send("flush")

    def lock(self) -> None:
        """Holds an exclusive lock until killed; only rollback-journal mode shuts out readers."""
        self._send("lock")

    def kill(self) -> None:
        # SIGKILL on POSIX, TerminateProcess on Windows: nothing in the worker runs after it.
        self.process.kill()
        # Waits, and closes the pipes, which would otherwise warn when collected.
        self.process.communicate()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.process.returncode is None:
            self.kill()

    def _send(self, command: str) -> None:
        stdin, stdout = self.process.stdin, self.process.stdout
        assert stdin is not None
        assert stdout is not None
        # Armed per answer, not per process: a held lock may outlive PROCESS_TIMEOUT.
        watchdog = threading.Timer(PROCESS_TIMEOUT, self.process.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            stdin.write(command + "\n")
            stdin.flush()
            answer = stdout.readline().strip()
        finally:
            watchdog.cancel()
        if answer != READY:
            raise RuntimeError(f"The store worker answered {answer!r} to {command!r}.")


def main(crawl_file: Path) -> None:
    # Frozen, so only a flush or the 500th unit commits: what a kill loses is exact.
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        for line in sys.stdin:
            command, _, argument = line.strip().partition(" ")
            if command == "insert":
                position = int(argument)
                writer.run(insert_seed(position, f"https://example.com/{position}"))
            elif command == "lock":
                locker = connect(crawl_file)
                locker.isolation_level = None
                locker.execute("BEGIN EXCLUSIVE")
            elif command == "flush":
                writer.flush()
            elif command != "open":
                print(f"unknown command {command}", flush=True)
                continue
            print(READY, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
