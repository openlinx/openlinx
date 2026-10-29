"""A writer in its own process, run and killed by durability tests (015-add-crawl-store)."""

import os
import subprocess
import sys
import threading
from pathlib import Path
from types import TracebackType
from typing import Self

from openlinx.store.connections import connect
from openlinx.store.writer import CrawlWriter
from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.clock import FakeClock
from tests.support.crawls import insert_seed
from tests.support.processes import python_command

READY = "ok"


class StoreWorker:
    """Each command returns once the worker has answered it, so a test never sleeps.

    Use it as a context manager: the worker is killed on the way out, even when a test fails.
    """

    def __init__(self, crawl_file: Path) -> None:
        command = python_command("-m", "tests.support.store_worker", str(crawl_file))
        self.process = subprocess.Popen(
            command.argv,
            cwd=REPO_ROOT,
            env=command.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        # The process that holds the crawl file, which a kill must reach.
        self.pid = int(self._ask("open"))

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
        answer = self._ask(command)
        if answer != READY:
            raise RuntimeError(f"The store worker answered {answer!r} to {command!r}.")

    def _ask(self, command: str) -> str:
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
            answer: str = stdout.readline().strip()
        finally:
            watchdog.cancel()
        if not answer:
            raise RuntimeError(f"The store worker ended before answering {command!r}.")
        return answer


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
            elif command == "open":
                print(os.getpid(), flush=True)
                continue
            else:
                print(f"unknown command {command}", flush=True)
                continue
            print(READY, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
