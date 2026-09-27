"""Checked-out text files use LF on every OS (design D16 of 000-scaffold-project)."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXT_IN_INDEX = {"i/lf", "i/crlf", "i/mixed"}


def text_files_not_checked_out_with_lf() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "--eol", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    offenders: list[str] = []
    for entry in filter(None, listing.split("\0")):
        info, path = entry.split("\t", 1)
        index_eol, worktree_eol, attributes = info.split(maxsplit=2)
        marked_binary = "-text" in attributes.removeprefix("attr/").split()
        if index_eol in TEXT_IN_INDEX and not marked_binary and worktree_eol != "w/lf":
            offenders.append(path)
    return offenders


def test_checked_out_text_files_use_lf() -> None:
    assert text_files_not_checked_out_with_lf() == []
