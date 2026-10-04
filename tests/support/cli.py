"""Run the CLI in tests: in process, or as a real process (design D8 of 000-scaffold-project)."""

import json
import subprocess
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from typer.testing import CliRunner

from spider.cli.app import build_app


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: bytes
    stderr: bytes

    def json(self) -> Any:
        return json.loads(self.stdout)

    def stderr_json_lines(self) -> list[Any]:
        return [json.loads(line) for line in self.stderr.splitlines()]


def run_cli(
    *args: str, input: str | bytes | None = None, app: typer.Typer | None = None
) -> CliResult:
    result = CliRunner().invoke(app or build_app(), list(args), input=input)
    return CliResult(result.exit_code, result.stdout_bytes, result.stderr_bytes)


def run_cli_process(*args: str, env: Mapping[str, str] | None = None) -> CliResult:
    completed = subprocess.run(
        [sys.executable, "-m", "spider", *args], capture_output=True, env=env, check=False
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_EXAMPLE_APP = (
    "import sys; from tests.support.app import example_app; example_app()(sys.argv[1:])"
)
# A hung Command fails its test instead of hanging CI.
PROCESS_TIMEOUT = 10


def run_example_process(*args: str) -> CliResult:
    completed = subprocess.run(
        [sys.executable, "-c", RUN_EXAMPLE_APP, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)


def start_example_process(*args: str) -> subprocess.Popen[bytes]:
    process = subprocess.Popen(
        [sys.executable, "-c", RUN_EXAMPLE_APP, *args],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # A line that never comes would block a read forever; killing the process ends the read.
    watchdog = threading.Timer(PROCESS_TIMEOUT, process.kill)
    watchdog.daemon = True
    watchdog.start()
    return process
