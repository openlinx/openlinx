"""Guard: the working name spider is gone (021-rename-to-openlinx design D2 and D3)."""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# History, which the rename's own plan now is, and this guard.
EXEMPT = ("openspec/changes/archive/", "tests/test_no_working_name.py")
# spider as the Crawl Mode and as Spider mode, and ADR-0006's dated measurement, are not the
# product's name (design D2).
KEPT = re.compile(
    r"crawl_mode\W{1,8}spider\b"
    r'|CrawlMode = Literal\["spider"'
    r"|`spider`, `list`"
    r"|\(`spider` for this capability\)"
    r"|(?i:\bSpider[- ]mode\b)"
    r"|\*Spider\*"
    r"|\bSpider (?=[Cc]rawl)"
    r"|\(Spider, the Seed\)"
    r"|\btest_spider_mode\b"
    r"|Measured on `main` at f5abc9e .*"
)
# A Crawl Mode value that the line alone does not show: a positional argument of the result.
KEPT_LINES = {("tests/cli/test_crawl.py", '"spider",')}
WORKING_NAME = re.compile("spider", re.IGNORECASE)


def tracked_text_files(root: Path) -> list[str]:
    listing = subprocess.run(
        # The fake home hides the global .gitconfig, and with it any safe.directory entry.
        ["git", "-c", f"safe.directory={root.as_posix()}", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return [path for path in listing.split("\0") if path and not path.startswith(EXEMPT)]


def working_names(root: Path) -> list[str]:
    hits = []
    for path in tracked_text_files(root):
        file = root / path
        if not file.is_file():
            continue
        data = file.read_bytes()
        if b"\0" in data:
            continue
        # Fixture pages hold bytes in legacy encodings on purpose.
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), start=1):
            if (path, line.strip()) in KEPT_LINES:
                continue
            if WORKING_NAME.search(KEPT.sub("", line)):
                hits.append(f"{path}:{number}: {line.strip()}")
    return hits


def test_no_file_uses_the_working_name() -> None:
    assert working_names(REPO_ROOT) == [], (
        "the working name is used: name the tool through openlinx.naming, and keep spider "
        "only as the Crawl Mode and in KEPT_LINES"
    )
