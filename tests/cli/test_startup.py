"""What a fresh process loads to start (design D2 of 010-add-workspace-and-cli-contract)."""

import subprocess
import sys

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT

# Runs the app as the console script does, then lists every loaded module on stderr.
LIST_MODULES_AFTER_RUN = """
import sys
from tests.support.app import example_app
try:
    example_app()(sys.argv[1:])
except SystemExit:
    pass
sys.stderr.write("\\n".join(sys.modules))
"""


def modules_loaded_by_the_example_app(*args: str) -> set[str]:
    completed = subprocess.run(
        [sys.executable, "-c", LIST_MODULES_AFTER_RUN, *args],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=True,
        text=True,
    )
    return set(completed.stderr.split())


def test_settings_tables_load_with_the_settings() -> None:
    assert "tests.support.settings" not in modules_loaded_by_the_example_app("--help")
