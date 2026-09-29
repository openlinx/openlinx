"""Every test gets its own home folder (design D8 of 000-scaffold-project)."""

import subprocess
import sys
from pathlib import Path


def test_home_is_the_home_folder_under_tmp_path(tmp_path: Path) -> None:
    assert Path.home() == tmp_path / "home"


def test_a_child_process_sees_the_same_home(tmp_path: Path) -> None:
    printed = subprocess.run(
        [sys.executable, "-c", "import pathlib; print(pathlib.Path.home())"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout

    assert Path(printed.strip()) == tmp_path / "home"
