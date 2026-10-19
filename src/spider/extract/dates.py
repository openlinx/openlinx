"""Times in headers, read leniently, as RFC 9110 and RFC 6265 ask (030-add-page-data D1, D14)."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


def internet_date(value: str, *, cookie: bool = False) -> datetime | None:
    """An HTTP-date or another Internet Message Format date, in UTC; None when neither."""
    try:
        moment = parsedate_to_datetime(value)
        # The mail-date reading takes a two-digit 69 for 1969, while RFC 6265 reads it as 2069.
        if cookie and moment.year == 1969 and "1969" not in value:
            moment = moment.replace(year=2069)
        # An HTTP-date is always GMT, also in the asctime form, which names no zone. Converted
        # here, so a time past the year 9999 in UTC is None, not a Page that fails to be written.
        return (moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment).astimezone(UTC)
    except (ValueError, OverflowError):
        return None
