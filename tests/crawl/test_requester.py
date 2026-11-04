"""Which outcome of an attempt is tried again (022-add-fetch-policy D4; pure logic)."""

from datetime import UTC, datetime
from typing import get_args

import pytest

from openlinx.crawl.fetch.fetcher import FetchFailure, FetchResult
from openlinx.crawl.fetch.requester import is_retried, retry_wait
from openlinx.store.records import FetchError

_AT = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)

# Every fetch_error the store knows, classified: a new value fails here until it is.
_FAILURES: dict[FetchError, bool] = {
    "timeout": True,
    "connection_refused": True,
    "connection_error": True,
    "dns_error": False,
    "tls_error": False,
    "invalid_response": False,
    "watchdog": False,
    "record_failed": False,
}
# One status of each class: a server error and a 429 are tried again, no other 4xx. A status
# past 599, such as the 999 some sites send crawlers, is no server error.
_STATUSES = {
    200: False,
    301: False,
    404: False,
    410: False,
    429: True,
    500: True,
    503: True,
    599: True,
    600: False,
    999: False,
}


def test_every_fetch_error_is_classified() -> None:
    assert sorted(_FAILURES) == sorted(get_args(FetchError.__value__))


@pytest.mark.parametrize(("fetch_error", "retried"), _FAILURES.items())
def test_a_failure_is_retried_only_when_it_may_pass(fetch_error: FetchError, retried: bool) -> None:
    failure = FetchFailure(fetch_error=fetch_error, message="", fetched_at=_AT)

    assert is_retried(failure) is retried


@pytest.mark.parametrize(("status_code", "retried"), _STATUSES.items())
def test_a_response_is_retried_only_on_a_server_error_or_a_429(
    status_code: int, retried: bool
) -> None:
    response = FetchResult(
        status_code=status_code,
        reason=None,
        headers=(),
        body=b"",
        fetched_at=_AT,
        response_time_ms=1,
    )

    assert is_retried(response) is retried


@pytest.mark.parametrize(("attempt", "wait"), [(1, 1.0), (3, 4.0)])
def test_a_500_retry_after_pauses_the_host_without_replacing_its_backoff(
    attempt: int, wait: float
) -> None:
    response = FetchResult(
        status_code=500,
        reason=None,
        headers=(("Retry-After", "60"),),
        body=b"",
        fetched_at=_AT,
        response_time_ms=1,
    )

    assert retry_wait(response, attempt, _AT) == (wait, 60.0)


@pytest.mark.parametrize(
    ("status", "header", "expected"),
    [
        (301, None, (4.0, None)),
        (301, "not a date", (4.0, None)),
        (500, "not a date", (4.0, None)),
        (503, None, (4.0, None)),
        (503, "not a date", (4.0, None)),
        (429, None, (10.0, 10.0)),
        (429, "not a date", (10.0, 10.0)),
        (301, "0", (4.0, 0.0)),
        (503, "0", (0.0, 0.0)),
        (500, "600", (4.0, 120.0)),
        (503, "600", (120.0, 120.0)),
    ],
)
def test_retry_wait_and_host_pause_keep_their_header_rules(
    status: int, header: str | None, expected: tuple[float, float | None]
) -> None:
    response = FetchResult(
        status_code=status,
        reason=None,
        headers=() if header is None else (("Retry-After", header),),
        body=b"",
        fetched_at=_AT,
        response_time_ms=1,
    )

    assert retry_wait(response, 3, _AT) == expected
