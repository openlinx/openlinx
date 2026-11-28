"""Record stop requests and order them against the Crawl's final state."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Connection, bindparam, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from openlinx.clock import Clock
from openlinx.output.codes import CRAWL_FILE_INVALID, CRAWL_NOT_WRITABLE
from openlinx.output.diagnostics import OpenLinxError
from openlinx.store.connections import busy_error, is_busy, is_read_only, opening
from openlinx.store.crawls import crawl_summary, set_state
from openlinx.store.identity import check_crawl_id
from openlinx.store.reading import reading_selected
from openlinx.store.records import CrawlFile, CrawlState, CrawlSummary, StopReason
from openlinx.store.schema import control_requests, crawl

_CONTROL_BUSY_SECONDS = 5.0
_STATE = select(crawl.c.id, crawl.c.state, crawl.c.stop_reason)
_HAS_CONTROL = text("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=:name").bindparams(
    name=control_requests.name
)
_INSERT_STOP = insert(control_requests).values(kind="stop")
_LATEST_STOP_ID = select(func.max(control_requests.c.id))
_PENDING_STOP = (
    select(control_requests.c.id)
    .where(
        control_requests.c.kind == "stop",
        control_requests.c.id > bindparam("after"),
        control_requests.c.handled_at.is_(None),
    )
    .order_by(control_requests.c.id)
    .limit(1)
)
_MARK_HANDLED = (
    update(control_requests)
    .where(
        control_requests.c.id == bindparam("request_id"), control_requests.c.handled_at.is_(None)
    )
    .values(handled_at=bindparam("at"), handled_by_run_id=bindparam("run_id"))
)


def write_control(
    selected: CrawlFile, at: datetime, pid: int
) -> tuple[CrawlState, StopReason | None]:
    """Record a stop only while the selected Crawl is still running in the write transaction."""
    # A terminal Crawl needs only a read, even if it cannot be opened for writing.
    state, reason = read_stop_state(selected, busy_seconds=_CONTROL_BUSY_SECONDS)
    if state != "running":
        return state, reason

    path = selected.path
    try:
        with (
            opening(
                path, role="control", identity=selected.identity, busy_seconds=_CONTROL_BUSY_SECONDS
            ) as engine,
            engine.begin() as connection,
        ):
            found, state, reason = connection.execute(_STATE).one()
            check_crawl_id(path, selected.id, found)
            if state == "running":
                if connection.execute(_HAS_CONTROL).scalar_one_or_none() is None:
                    raise OpenLinxError(
                        CRAWL_FILE_INVALID,
                        f"The crawl file {path} does not support stop requests.",
                        details={"file": str(path)},
                    )
                connection.execute(_INSERT_STOP, {"requested_at": at, "requested_by_pid": pid})
        return state, reason
    except DBAPIError as error:
        if is_busy(error):
            raise busy_error(
                path, "recording the stop request", _CONTROL_BUSY_SECONDS, error
            ) from error
        if is_read_only(error):
            raise OpenLinxError(
                CRAWL_NOT_WRITABLE,
                f"Cannot record a stop request in the read-only crawl file {path}.",
                details={"file": str(path)},
            ) from error
        raise


def read_stop_state(
    selected: CrawlFile, *, busy_seconds: float = 0
) -> tuple[CrawlState, StopReason | None]:
    """Observe committed state, with a zero SQLite lock timeout for wait polls."""
    with reading_selected(selected, busy_seconds=busy_seconds) as connection:
        _, state, reason = connection.execute(_STATE).one()
        return state, reason


def latest_stop_request(selected: CrawlFile) -> int | None:
    """Get the last request before a continue, or None for files created without control."""
    with reading_selected(selected) as connection:
        if connection.execute(_HAS_CONTROL).scalar_one_or_none() is None:
            return None
        latest: int | None = connection.execute(_LATEST_STOP_ID).scalar_one()
        return 0 if latest is None else latest


def _pending_stop(connection: Connection, after: int) -> int | None:
    request: int | None = connection.execute(_PENDING_STOP, {"after": after}).scalar_one_or_none()
    return request


def pending_stop_request(selected: CrawlFile, *, after: int) -> int | None:
    """Find a committed request in one snapshot, without waiting for SQLite locks."""
    with reading_selected(selected, busy_seconds=0) as connection:
        return _pending_stop(connection, after)


def record_stop_handled(
    request_id: int, at: datetime, *, run_id: int
) -> Callable[[Connection], None]:
    """Record the request the Crawl acted on, preserving its timestamp and run on replay."""

    def unit(connection: Connection) -> None:
        connection.execute(_MARK_HANDLED, {"request_id": request_id, "at": at, "run_id": run_id})

    return unit


def record_end(
    state: CrawlState,
    clock: Clock,
    reason: StopReason | None,
    *,
    stop_after: int | None,
    run_id: int | None,
) -> Callable[[Connection], tuple[datetime, CrawlSummary]]:
    """Finalize under the same SQLite write lock a stop needs to inspect the running state."""
    summary = crawl_summary()

    def unit(connection: Connection) -> tuple[datetime, CrawlSummary]:
        # The writer commits immediately after this unit. Sample the Clock under the lock
        # so a request accepted just before the lock is recorded with its actual handling time.
        request = (
            _pending_stop(connection, stop_after)
            if stop_after is not None and reason in (None, "max_urls")
            else None
        )
        at = clock.now()
        if request is not None:
            if run_id is None:
                raise RuntimeError("A handled stop request needs a recorded run.")
            record_stop_handled(request, at, run_id=run_id)(connection)
            set_state(connection, "stopped", at, "requested")
        else:
            set_state(connection, state, at, reason)
        return at, summary(connection)

    return unit
