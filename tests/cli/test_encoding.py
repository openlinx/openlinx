"""UTF-8 output on every OS (010-add-workspace-and-cli-contract, cli-contract)."""

import os
import sys

import pytest

from tests.support.cli import run_cli, run_cli_process
from tests.support.workspace import TempWorkspace

# The UTF-8 bytes of "Проверка", as the spec writes them.
CHECK_IN_UTF8 = bytes.fromhex("D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0")


def test_non_ascii_characters_are_not_escaped(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli("init", "--workspace", str(folder)).stdout

    assert (CHECK_IN_UTF8 in stdout, b"\\u" in stdout) == (True, False)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_piped_output_on_windows(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli_process("init", "--workspace", str(folder)).stdout

    assert CHECK_IN_UTF8 in stdout


def test_pythonioencoding_does_not_change_the_output(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli_process(
        "init", "--workspace", str(folder), env={**os.environ, "PYTHONIOENCODING": "cp1252"}
    ).stdout

    assert CHECK_IN_UTF8 in stdout


def test_utf8_on_stderr(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "Проверка.txt").write_bytes(b"")
    site = temp_workspace.root / "Проверка.txt" / "site"

    stderr = run_cli_process("init", "--workspace", str(site)).stderr

    assert CHECK_IN_UTF8 in stderr


@pytest.mark.skipif(sys.platform != "win32", reason="text streams add CR only on Windows")
def test_no_carriage_returns_on_windows() -> None:
    stdout = run_cli_process("commands").stdout

    assert (stdout.endswith(b"}\n"), b"\r" in stdout) == (True, False)
