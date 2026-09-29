"""`spider --version` (000-scaffold-project, task 2.1)."""

import tomllib
from pathlib import Path

from tests.support.cli import run_cli

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def project_version() -> str:
    with PYPROJECT.open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return version


def test_version_prints_the_app_name_and_the_project_version() -> None:
    result = run_cli("--version")

    assert (result.exit_code, result.stdout) == (0, b"spider " + project_version().encode() + b"\n")
