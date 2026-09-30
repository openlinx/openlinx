"""`spider --version` (000-scaffold-project, tasks 2.1 and 2.2)."""

import tomllib
from pathlib import Path

from tests.support.cli import run_cli, run_cli_process

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def expected_version_line() -> bytes:
    with PYPROJECT.open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return b"spider " + version.encode() + b"\n"


def test_version_prints_the_app_name_and_the_project_version() -> None:
    result = run_cli("--version")

    assert (result.exit_code, result.stdout) == (0, expected_version_line())


def test_version_as_a_real_process_prints_the_same_bytes() -> None:
    result = run_cli_process("--version")

    assert (result.exit_code, result.stdout) == (0, expected_version_line())
