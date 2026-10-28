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
from tests.support.processes import python_command


@dataclass(frozen=True)
class CliResult:
    exit_code: int
    stdout: bytes
    stderr: bytes

    def json(self) -> Any:
        return json.loads(self.stdout)

    def stderr_json_lines(self) -> list[Any]:
        return [json.loads(line) for line in self.stderr.splitlines()]

    def stray_stderr_lines(self) -> list[bytes]:
        """The stderr lines that are neither an event nor a diagnostic."""
        return [line for line in self.stderr.splitlines() if not _is_event_or_diagnostic(line)]

    def errors(self) -> list[Any]:
        """The stderr lines that are error diagnostics."""
        return [line for line in self.stderr_json_lines() if line.get("level") == "error"]


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
# A Crawl of the fixture site takes longer to start and to end.
CRAWL_PROCESS_TIMEOUT = 45


def run_example_process(*args: str) -> CliResult:
    command = python_command("-c", RUN_EXAMPLE_APP, *args)
    completed = subprocess.run(
        command.argv,
        cwd=REPO_ROOT,
        env=command.env,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    return CliResult(completed.returncode, completed.stdout, completed.stderr)


def start_example_process(*args: str) -> subprocess.Popen[bytes]:
    command = python_command("-c", RUN_EXAMPLE_APP, *args)
    process = subprocess.Popen(
        command.argv,
        cwd=REPO_ROOT,
        env=command.env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # A line that never comes would block a read forever; killing the process ends the read.
    watchdog = threading.Timer(PROCESS_TIMEOUT, process.kill)
    watchdog.daemon = True
    watchdog.start()
    return process


def start_cli_process(*args: str) -> subprocess.Popen[bytes]:
    """A real `spider` process in the current folder, which a test can signal or kill. On
    Windows it has its own process group, so a Ctrl+Break event reaches it alone."""
    command = python_command("-m", "spider", *args)
    if sys.platform == "win32":
        group = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        group = 0
    process = subprocess.Popen(
        command.argv,
        env=command.env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=group,
    )
    # A Command that never ends would hang the test's read; killing it ends the read.
    watchdog = threading.Timer(CRAWL_PROCESS_TIMEOUT, process.kill)
    watchdog.daemon = True
    watchdog.start()
    return process


def _is_event_or_diagnostic(line: bytes) -> bool:
    try:
        parsed = json.loads(line)
    except ValueError:
        return False
    return isinstance(parsed, dict) and ("event" in parsed or "level" in parsed)
