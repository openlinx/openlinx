"""Crawling the fixture site in tests (020-add-crawl-core, seam 3+6)."""

from pathlib import Path

from tests.support.cli import run_cli


def crawled(*args: str) -> Path:
    """Runs `spider crawl` with `args` and returns the crawl file its result names."""
    result = run_cli("crawl", *args)
    if result.exit_code != 0:
        last = result.stderr.splitlines()[-1:] or [b""]
        raise AssertionError(f"spider crawl exited {result.exit_code}: {last[0][:2000]!r}")
    return Path(result.json()["crawl_file"])
