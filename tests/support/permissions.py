"""Real folders without write permission (015-add-crawl-store, task 3.11)."""

import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

# The well-known SID of Everyone, so the deny entry needs no user or language-specific name.
EVERYONE = "*S-1-1-0"


@contextmanager
def unwritable_folder(folder: Path) -> Iterator[None]:
    """No file can be created in `folder`: its mode on POSIX, a deny ACL on Windows.

    Windows ignores the read-only attribute on folders, so only an ACL protects one there.
    """
    if sys.platform == "win32":
        _icacls(folder, "/deny", f"{EVERYONE}:(W)")
        try:
            yield
        finally:
            _icacls(folder, "/remove:d", EVERYONE)
    else:
        if os.geteuid() == 0:
            pytest.skip("root ignores folder permissions")
        folder.chmod(0o555)
        try:
            yield
        finally:
            folder.chmod(0o755)


@contextmanager
def read_only_file(file: Path) -> Iterator[None]:
    """The read-only attribute on Windows; no write permission on POSIX."""
    if sys.platform != "win32" and os.geteuid() == 0:
        pytest.skip("root ignores file permissions")
    mode = file.stat().st_mode
    file.chmod(stat.S_IREAD)
    try:
        yield
    finally:
        file.chmod(mode)


def _icacls(folder: Path, *args: str) -> None:
    subprocess.run(["icacls", str(folder), *args], capture_output=True, check=True)
