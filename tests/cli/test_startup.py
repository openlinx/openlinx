"""What a fresh process loads (designs D2 and D10 of 010-add-workspace-and-cli-contract)."""

import os
import subprocess
import sys

import pytest

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT

# Runs an app as the console script does, then lists every loaded module on stderr.
LIST_MODULES_AFTER_RUN = """
import sys
from {module} import {factory}
try:
    {factory}()(sys.argv[1:])
except SystemExit:
    pass
sys.stderr.write("\\n".join(sys.modules))
"""

STARTUP_ALLOWLIST = {
    "__main__",
    "typer",
    # Typer's own dependencies; rich is one too, but Typer's rich help is off.
    "annotated_doc",
    "colorama",
    "shellingham",
    "orjson",
    "spider",
    # uv's virtual environment loads it, before any code of ours.
    "_virtualenv",
}


def modules_loaded(module: str, factory: str, *args: str) -> set[str]:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            LIST_MODULES_AFTER_RUN.format(module=module, factory=factory),
            *args,
        ],
        cwd=REPO_ROOT,
        # Coverage would measure the child and load its own modules into it.
        env={k: v for k, v in os.environ.items() if not k.startswith("COVERAGE_PROCESS_")},
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=True,
        text=True,
    )
    return set(completed.stderr.split())


def test_settings_tables_load_with_the_settings() -> None:
    loaded = modules_loaded("tests.support.app", "example_app", "--help")

    assert "tests.support.settings" not in loaded


@pytest.mark.parametrize("command", ["--help", "commands"])
def test_startup_loads_only_the_allowlist(command: str) -> None:
    loaded = modules_loaded("spider.cli.app", "build_app", command)
    top_level = {name.partition(".")[0] for name in loaded}

    assert top_level - sys.stdlib_module_names - STARTUP_ALLOWLIST == set()
