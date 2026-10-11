"""Checked-out text files use LF on every OS (design D16 of 000-scaffold-project)."""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEXT_IN_INDEX = {"i/lf", "i/crlf", "i/mixed"}


def git(root: Path, *args: str) -> bytes:
    # The fake home hides the global .gitconfig, and with it any safe.directory entry.
    return subprocess.run(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout


def text_files_not_checked_out_with_lf(root: Path) -> list[str]:
    listing = git(root, "ls-files", "--eol", "-z").decode("utf-8")
    offenders: list[str] = []
    for entry in filter(None, listing.split("\0")):
        info, path = entry.split("\t", 1)
        index_eol, worktree_eol, attributes = info.split(maxsplit=2)
        kept_byte_exact = "-text" in attributes.removeprefix("attr/").split()
        # A path deleted or moved but not yet staged, as after openspec archive, is still listed.
        if not (root / path).exists():
            continue
        if index_eol in TEXT_IN_INDEX and not kept_byte_exact and worktree_eol != "w/lf":
            offenders.append(path)
    return offenders


def test_checked_out_text_files_use_lf() -> None:
    assert text_files_not_checked_out_with_lf(REPO_ROOT) == []


def test_a_tracked_file_missing_from_the_working_tree_is_skipped(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "kept.txt").write_bytes(b"one\ntwo\n")
    (tmp_path / "deleted.txt").write_bytes(b"one\ntwo\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "lf")
    (tmp_path / "deleted.txt").unlink()
    (tmp_path / "kept.txt").write_bytes(b"one\r\ntwo\r\n")

    assert text_files_not_checked_out_with_lf(tmp_path) == ["kept.txt"]
