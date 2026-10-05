"""Crawl ids: the UTC start time and 4 random characters (design D1 of 015-add-crawl-store)."""

import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

# Crockford-style: no i, l, o or u, so an id read aloud or copied by hand stays unambiguous.
SUFFIX_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
SUFFIX_LENGTH = 4

type Choice = Callable[[Sequence[str]], str]


def new_crawl_id(started_at: datetime, choice: Choice = secrets.choice) -> str:
    suffix = "".join(choice(SUFFIX_ALPHABET) for _ in range(SUFFIX_LENGTH))
    return f"{started_at.astimezone(UTC):%Y%m%d-%H%M%S}-{suffix}"
