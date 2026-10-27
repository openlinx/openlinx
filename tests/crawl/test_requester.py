"""Which outcome of an attempt is tried again (022-add-fetch-policy D4; pure logic)."""

from datetime import UTC, datetime
from typing import get_args

import pytest

from spider.crawl.fetch.fetcher import FetchFailure, FetchResult
from spider.crawl.fetch.requester import is_retried
from spider.store.records import FetchError

_AT = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)

# Every fetch_error the store knows, classified: a new value fails here until it is.
_FAILURES: dict[str, bool] = {
    "timeout": True,
    "connection_refused": True,
    "connection_error": True,
    "dns_error": False,
    "tls_error": False,
    "invalid_response": False,
    "watchdog": False,
    "record_failed": False,
}
# One status of each class: only a server error is tried again.
_STATUSES = {200: False, 301: False, 404: False, 410: False, 500: True, 503: True}


def test_every_fetch_error_is_classified() -> None:
    assert sorted(_FAILURES) == sorted(get_args(FetchError.__value__))


@pytest.mark.parametrize(("fetch_error", "retried"), _FAILURES.items())
def test_a_failure_is_retried_only_when_it_may_pass(fetch_error: str, retried: bool) -> None:
    failure = FetchFailure(fetch_error=fetch_error, message="", fetched_at=_AT)  # type: ignore[arg-type]

    assert is_retried(failure) is retried


@pytest.mark.parametrize(("status_code", "retried"), _STATUSES.items())
def test_a_response_is_retried_only_on_a_server_error(status_code: int, retried: bool) -> None:
    response = FetchResult(
        status_code=status_code,
        reason=None,
        headers=(),
        body=b"",
        fetched_at=_AT,
        response_time_ms=1,
    )

    assert is_retried(response) is retried
