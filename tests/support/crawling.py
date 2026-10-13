"""Crawling the fixture site in tests (020-add-crawl-core, seam 3+6)."""

from pathlib import Path

from tests.support.cli import run_cli


def crawled(*args: str) -> Path:
    """Runs `spider crawl` with `args` and returns the crawl file its result names."""
    result = run_cli("crawl", *args)
    if result.exit_code != 0:
        raise AssertionError(f"spider crawl exited {result.exit_code}: {result.stderr!r}")
    return Path(result.json()["crawl_file"])
