"""Crawl ids: the UTC start time and 4 random characters (design D1 of 015-add-crawl-store)."""

import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

# Crockford-style: no i, l, o or u, so an id read aloud or copied by hand stays unambiguous.
SUFFIX_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
SUFFIX_LENGTH = 4
CRAWL_FILE_SUFFIX = ".sqlite"
_CRAWL_ID = re.compile(rf"[0-9]{{8}}-[0-9]{{6}}-[{SUFFIX_ALPHABET}]{{{SUFFIX_LENGTH}}}")

type Choice = Callable[[Sequence[str]], str]


def is_crawl_id(text: str) -> bool:
    return _CRAWL_ID.fullmatch(text) is not None


def crawl_path(crawls_dir: Path, crawl_id: str) -> Path:
    return crawls_dir / f"{crawl_id}{CRAWL_FILE_SUFFIX}"


def start_second(crawl_id: str) -> str:
    return crawl_id.rsplit("-", 1)[0]


def new_crawl_id(started_at: datetime, choice: Choice) -> str:
    suffix = "".join(choice(SUFFIX_ALPHABET) for _ in range(SUFFIX_LENGTH))
    return f"{started_at.astimezone(UTC):%Y%m%d-%H%M%S}-{suffix}"
