"""What a fresh process loads (designs D2 and D10 of 010-add-workspace-and-cli-contract)."""

import os
import subprocess
import sys

import pytest

from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT

LIST_MODULES = 'sys.stderr.write("\\n".join(sys.modules))'
# Runs an app as the console script does, then lists every loaded module on stderr.
LIST_MODULES_AFTER_RUN = f"""
import sys
from {{module}} import {{factory}}
try:
    {{factory}}()(sys.argv[1:])
except SystemExit:
    pass
{LIST_MODULES}
"""

STARTUP_ALLOWLIST = {
    "typer",
    # Typer's own dependencies; rich is one too, but Typer's rich help is off.
    "annotated_doc",
    "colorama",
    "shellingham",
    "orjson",
    "spider",
}


def modules_loaded(module: str, factory: str, *args: str) -> set[str]:
    return _child_modules(LIST_MODULES_AFTER_RUN.format(module=module, factory=factory), *args)


def interpreter_startup_modules() -> set[str]:
    # Loaded before any code of ours: sitecustomize on some CI images, _virtualenv, __main__.
    return _child_modules(f"import sys\n{LIST_MODULES}")


def _child_modules(code: str, *args: str) -> set[str]:
    completed = subprocess.run(
        [sys.executable, "-c", code, *args],
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
    top_level = {name.partition(".")[0] for name in loaded - interpreter_startup_modules()}

    assert top_level - sys.stdlib_module_names - STARTUP_ALLOWLIST == set()
