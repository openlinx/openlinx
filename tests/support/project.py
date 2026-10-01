"""What the tests read from pyproject.toml (task 1.12 of 010-add-workspace-and-cli-contract)."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def project_version() -> str:
    with PYPROJECT.open("rb") as file:
        version: str = tomllib.load(file)["project"]["version"]
    return version
