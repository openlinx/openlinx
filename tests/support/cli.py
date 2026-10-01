"""Run the CLI in tests: in process, or as a real process (design D8 of 000-scaffold-project)."""

import json
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from typer.testing import CliRunner

from spider.cli.app import build_app


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: bytes
    stderr: bytes

    def json(self) -> Any:
        return json.loads(self.stdout)


def run_cli(*args: str, input: str | bytes | None = None) -> CliResult:
    result = CliRunner().invoke(build_app(), list(args), input=input)
    return CliResult(result.exit_code, result.stdout_bytes, result.stderr_bytes)


def run_cli_process(*args: str, env: Mapping[str, str] | None = None) -> CliResult:
    completed = subprocess.run(
        [sys.executable, "-m", "spider", *args], capture_output=True, env=env, check=False
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)
