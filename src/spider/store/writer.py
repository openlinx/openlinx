"""The transactional writer: units of work on one thread (design D4 of 015-add-crawl-store)."""

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from types import TracebackType
from typing import Any, Self

from sqlalchemy import Connection

from spider.clock import Clock
from spider.store.connections import opening

QUEUE_SIZE = 50_000


@dataclass(frozen=True)
class _Job:
    # None asks the writer thread to stop.
    unit: Callable[[Connection], Any] | None
    done: Future[Any]


class CrawlWriter:
    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        self._queue: Queue[_Job] = Queue(maxsize=QUEUE_SIZE)
        started: Future[None] = Future()
        self._thread = threading.Thread(
            target=self._serve, args=(started,), name=f"crawl writer {path.name}", daemon=True
        )
        self._thread.start()
        started.result()

    def run[T](self, unit: Callable[[Connection], T]) -> T:
        done: Future[T] = Future()
        self._queue.put(_Job(unit, done))
        return done.result()

    def close(self) -> None:
        done: Future[None] = Future()
        self._queue.put(_Job(None, done))
        done.result()
        self._thread.join()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _serve(self, started: Future[None]) -> None:
        try:
            with opening(self._path) as engine, engine.connect() as connection:
                started.set_result(None)
                connection.begin()
                while True:
                    job = self._queue.get()
                    if job.unit is None:
                        connection.commit()
                        job.done.set_result(None)
                        return
                    job.done.set_result(job.unit(connection))
        except BaseException as error:
            if not started.done():
                started.set_exception(error)
            raise
