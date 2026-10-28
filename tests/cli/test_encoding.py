"""UTF-8 output on every OS (010-add-workspace-and-cli-contract, cli-contract; 020-add-crawl-core,
crawling)."""

import json
import os
import sys
from typing import Any

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import run_cli, run_cli_process
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


def _utf8_json(line: bytes) -> Any:
    try:
        return json.loads(line.decode("utf-8"))
    except ValueError:
        return None
