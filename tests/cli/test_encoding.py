"""UTF-8 output and the same Page data on every OS (010-add-workspace-and-cli-contract,
cli-contract; 020-add-crawl-core, crawling; 030-add-page-data, page-data)."""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import CRAWL_PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.crawls import query
from tests.support.processes import python_command
from tests.support.workspace import TempWorkspace

# The UTF-8 bytes of "Проверка", as the spec writes them.
CHECK_IN_UTF8 = bytes.fromhex("D0 9F D1 80 D0 BE D0 B2 D0 B5 D1 80 D0 BA D0 B0")


def test_non_ascii_characters_are_not_escaped(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli("init", "--workspace", str(folder)).stdout

    assert (CHECK_IN_UTF8 in stdout, b"\\u" in stdout) == (True, False)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_piped_output_on_windows(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli_process("init", "--workspace", str(folder)).stdout

    assert CHECK_IN_UTF8 in stdout


def test_pythonioencoding_does_not_change_the_output(temp_workspace: TempWorkspace) -> None:
    folder = temp_workspace.root / "Проверка"

    stdout = run_cli_process(
        "init", "--workspace", str(folder), env={**os.environ, "PYTHONIOENCODING": "cp1252"}
    ).stdout

    assert CHECK_IN_UTF8 in stdout


def test_utf8_on_stderr(temp_workspace: TempWorkspace) -> None:
    (temp_workspace.root / "Проверка.txt").write_bytes(b"")
    site = temp_workspace.root / "Проверка.txt" / "site"

    stderr = run_cli_process("init", "--workspace", str(site)).stderr

    assert CHECK_IN_UTF8 in stderr


@pytest.mark.skipif(sys.platform != "win32", reason="text streams add CR only on Windows")
def test_no_carriage_returns_on_windows() -> None:
    stdout = run_cli_process("commands").stdout

    assert (stdout.endswith(b"}\n"), b"\r" in stdout) == (True, False)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_events_are_utf_8_on_windows(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(Site(routes={"/": Page(body="<p>/</p>")}))
    workspace = temp_workspace.root / "Ünits"
    run_cli("init", "--workspace", str(workspace))

    stderr = run_cli_process("crawl", server.url("/"), "--workspace", str(workspace)).stderr
    crawl_files = [
        event["data"]["crawl_file"]
        for event in map(_utf8_json, stderr.splitlines())
        if isinstance(event, dict) and event.get("event") == "crawl_started"
    ]

    assert ["Ünits" in crawl_file for crawl_file in crawl_files] == [True]


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows console code page")
def test_non_ascii_title_on_a_windows_console(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    # No charset, so the title is decoded by the last rule, which no locale may enter.
    page = Page(body="<title>Привет, мир</title>", content_type="text/html")
    server = fixture_site(Site(routes={"/ru": page}))
    workspace = temp_workspace.root / "site"
    run_cli("init", "--workspace", str(workspace))
    crawl = python_command(
        "-m", "openlinx", "crawl", server.url("/ru"), "--workspace", str(workspace)
    )
    # A console of its own, so chcp leaves alone the one the other tests share.
    new_console = 0
    if sys.platform == "win32":
        new_console = subprocess.CREATE_NEW_CONSOLE

    completed = subprocess.run(
        f'cmd /d /s /c "chcp 1251 && {subprocess.list2cmdline(crawl.argv)}"',
        env=crawl.env,
        capture_output=True,
        timeout=CRAWL_PROCESS_TIMEOUT,
        check=False,
        creationflags=new_console,
    )
    crawl_files = [
        event["data"]["crawl_file"]
        for event in map(_utf8_json, completed.stderr.splitlines())
        if isinstance(event, dict) and event.get("event") == "crawl_started"
    ]

    # chcp prints the code page it set, in the console's language, before the Crawl runs.
    assert (
        b"1251" in completed.stdout.splitlines()[0],
        [query(Path(file), "SELECT title_1, title_1_length FROM pages") for file in crawl_files],
    ) == (True, [[("Привет, мир", 11)]])


def _utf8_json(line: bytes) -> Any:
    try:
        return json.loads(line.decode("utf-8"))
    except ValueError:
        return None
