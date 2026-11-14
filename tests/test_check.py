"""The local gate checks every supported type platform regardless of its host."""

import runpy
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest


@pytest.mark.parametrize("windows_error", [False, True], ids=["all_platforms", "windows_error"])
def test_local_gate_checks_all_platforms_and_stops_on_a_type_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], windows_error: bool
) -> None:
    commands: list[list[str]] = []

    def spawn(
        command: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None, check: bool
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(list(command))
        failed = windows_error and list(command[1:5]) == ["-m", "mypy", "--platform", "win32"]
        return subprocess.CompletedProcess(command, int(failed))

    monkeypatch.setattr(subprocess, "run", spawn)

    if windows_error:
        with pytest.raises(SystemExit) as raised:
            runpy.run_path(
                str(Path(__file__).resolve().parents[1] / "scripts/check.py"), run_name="__main__"
            )
        assert raised.value.code == 1
        assert "FAILED: mypy --platform win32" in capsys.readouterr().err
        assert commands == [
            [sys.executable, "-m", "ruff", "check", "."],
            [sys.executable, "-m", "ruff", "format", "--check", "."],
            [
                sys.executable,
                "-m",
                "mypy",
                "--platform",
                "win32",
                "--cache-dir",
                ".mypy_cache/win32",
            ],
        ]
    else:
        runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "scripts/check.py"), run_name="__main__"
        )
        assert [command[3:] for command in commands if command[1:3] == ["-m", "mypy"]] == [
            ["--platform", "win32", "--cache-dir", ".mypy_cache/win32"],
            ["--platform", "linux", "--cache-dir", ".mypy_cache/linux"],
            ["--platform", "darwin", "--cache-dir", ".mypy_cache/darwin"],
        ]
