"""A writer in its own process, run and killed by durability tests (015-add-crawl-store)."""

import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Connection, insert

from spider.store.schema import seeds
from spider.store.writer import CrawlWriter
from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.clock import FakeClock

READY = "ok"


class StoreWorker:
    """Sends one command per line and waits for its answer, so a test never sleeps."""

    def __init__(self, crawl_file: Path) -> None:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.support.store_worker", str(crawl_file)],
            cwd=REPO_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        # An answer that never comes would block a read forever; killing the process ends it.
        watchdog = threading.Timer(PROCESS_TIMEOUT, self.process.kill)
        watchdog.daemon = True
        watchdog.start()
        self.send("open")

    def send(self, command: str) -> None:
        stdin, stdout = self.process.stdin, self.process.stdout
        assert stdin is not None
        assert stdout is not None
        stdin.write(command + "\n")
        stdin.flush()
        answer = stdout.readline().strip()
        if answer != READY:
            raise RuntimeError(f"The store worker answered {answer!r} to {command!r}.")

    def kill(self) -> None:
        # SIGKILL on POSIX, TerminateProcess on Windows: nothing in the worker runs after it.
        self.process.kill()
        # Waits, and closes the pipes, which would otherwise warn when collected.
        self.process.communicate()


def _insert_seed(position: int) -> Callable[[Connection], None]:
    def unit(connection: Connection) -> None:
        connection.execute(
            insert(seeds).values(position=position, url=f"https://example.com/{position}")
        )

    return unit


def main(crawl_file: Path) -> None:
    # Frozen, so only a flush or the 500th unit commits: what a kill loses is exact.
    with CrawlWriter(crawl_file, FakeClock()) as writer:
        for line in sys.stdin:
            command, _, argument = line.strip().partition(" ")
            if command == "insert":
                writer.run(_insert_seed(int(argument)))
            elif command == "flush":
                writer.flush()
            print(READY, flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
