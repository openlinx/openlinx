"""The two console scripts, linx and openlinx (021-rename-to-openlinx design D1 and D4)."""

import json
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import CRAWL_PROCESS_TIMEOUT, PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.crawls import crawl_row
from tests.support.workspace import TempWorkspace


def console_script(name: str) -> str:
    # The environment's scripts sit beside its Python: Scripts on Windows, bin elsewhere.
    script = shutil.which(name, path=str(Path(sys.executable).parent))
    assert script is not None, f"{name} is not installed beside {sys.executable}"
    return script


def test_both_console_scripts_run_the_same_entry_point() -> None:
    scripts = {
        entry.name: entry.value
        for entry in distribution("openlinx").entry_points
        if entry.group == "console_scripts"
    }

    assert scripts == {"linx": "openlinx.cli.app:main", "openlinx": "openlinx.cli.app:main"}


def test_usage_names_the_script_that_ran() -> None:
    script = subprocess.run(
        [console_script("openlinx"), "--help"],
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    module = run_cli_process("--help")

    assert (
        script.returncode,
        script.stdout.split(b"[")[0],
        module.exit_code,
        module.stdout.split(b"[")[0],
    ) == (0, b"Usage: openlinx ", 0, b"Usage: linx ")


def test_a_hint_names_linx_whichever_script_ran(temp_workspace: TempWorkspace) -> None:
    missing = temp_workspace.root / "missing"

    failed = subprocess.run(
        [console_script("openlinx"), "crawl", "site.test", "--workspace", str(missing)],
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )
    error = json.loads(failed.stderr.splitlines()[-1])

    assert (error["code"], error["hint"].startswith("Create it with: linx init")) == (
        "workspace_not_found",
        True,
    )


def test_the_recorded_command_line_starts_with_the_script_that_ran(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>/</p>")}))
    workspace = temp_workspace.root / "site"
    run_cli("init", "--workspace", str(workspace))

    crawled = subprocess.run(
        [console_script("openlinx"), "crawl", server.url("/"), "--workspace", str(workspace)],
        capture_output=True,
        timeout=CRAWL_PROCESS_TIMEOUT,
        check=False,
    )
    assert crawled.returncode == 0, crawled.stderr.decode("utf-8", "replace")
    crawl_file = Path(json.loads(crawled.stdout)["crawl_file"])

    assert json.loads(crawl_row(crawl_file)["command_argv"])[:2] == ["openlinx", "crawl"]
