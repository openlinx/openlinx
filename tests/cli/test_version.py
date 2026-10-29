"""`linx --version` (000-scaffold-project)."""

from tests.support.cli import run_cli, run_cli_process
from tests.support.project import project_version


def expected_version_line() -> bytes:
    return b"linx " + project_version().encode() + b"\n"


def test_version_prints_the_app_name_and_the_project_version() -> None:
    result = run_cli("--version")

    assert (result.exit_code, result.stdout) == (0, expected_version_line())


def test_version_as_a_real_process_prints_the_same_bytes() -> None:
    result = run_cli_process("--version")

    assert (result.exit_code, result.stdout) == (0, expected_version_line())
