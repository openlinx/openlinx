"""Verify the HTTP benchmark measures a real Crawl and accounts for the requested Pages."""

import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from tests.fixture_site.synthetic.accounting import accounted_urls
from tests.fixture_site.synthetic.site import SyntheticSite
from tests.support.cli import CRAWL_PROCESS_TIMEOUT
from tests.support.crawls import query


@pytest.mark.slow
def test_benchmark_verifies_the_requested_urls_in_the_crawl_file(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.crawl_500k",
            "--pages",
            "3",
            "--seed",
            "2408",
            "--keep",
            str(tmp_path / "crawl"),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        timeout=CRAWL_PROCESS_TIMEOUT,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    report = json.loads(result.stdout)
    assert (
        report["pages_requested"],
        report["pages_stored"],
        report["site"]["pages_requested"],
    ) == (
        3,
        2,
        3,
    )
    assert report["stored_urls"] == {
        "pages": 3,
        "resources": 84,
        "not_followed": 7,
        "missing": 2,
        "total": 96,
    }
    assert report["crawl_peak_rss_bytes"] > 0
    file = Path(report["crawl_file"])
    assert file.is_relative_to(tmp_path / "crawl")
    assert query(file, "SELECT state FROM crawl") == [("completed",)]
    assert query(
        file,
        "SELECT url_path, h1_count FROM pages WHERE status_code = 200 AND url_path IN "
        "('/', '/p/1', '/p/2') ORDER BY url_path",
    ) == [("/", 1), ("/p/2", 1)]

    assert query(file, "SELECT status_code, parsed FROM urls WHERE url LIKE '%/p/1'") == [(500, 0)]

    # A row count stays the same when one Resource is replaced by another URL.
    with closing(sqlite3.connect(file)) as db, db:
        seed: str = db.execute(
            "SELECT url FROM urls JOIN pages ON pages.url_id = urls.id WHERE url_path = '/'"
        ).fetchone()[0]
        db.execute(
            "UPDATE urls SET url = ? WHERE url = ?", (seed + "r/a/99.mp3", seed + "r/a/2.mp3")
        )
    with pytest.raises(ValueError, match=r"Unexpected URL in the crawl file: .*/r/a/99\.mp3"):
        accounted_urls(file, SyntheticSite(seed=2408, pages=3), seed.rstrip("/"))
