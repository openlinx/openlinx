"""UTF-8 output and the same Page data on every OS (010-add-workspace-and-cli-contract,
cli-contract; 020-add-crawl-core, crawling; 030-add-page-data, page-data)."""

import json
import os
import socket
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryFile
from time import monotonic
from typing import Any

import psutil
import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import CRAWL_PROCESS_TIMEOUT, run_cli, run_cli_process
from tests.support.crawls import query
from tests.support.processes import console_process, python_command
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

    stderr = run_cli_process(
        "crawl", server.url("/"), "--workspace", str(workspace), timeout=CRAWL_PROCESS_TIMEOUT
    ).stderr
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
    # No charset, so the title is decoded by the last rule, UTF-8, where code that took the
    # machine's encoding would go wrong.
    page = Page(body="<title>Привет, мир</title>", content_type="text/html")
    server = fixture_site(Site(routes={"/ru": page}))
    workspace = temp_workspace.root / "site"
    run_cli("init", "--workspace", str(workspace))
    crawl = python_command(
        "-m", "openlinx", "crawl", server.url("/ru"), "--workspace", str(workspace)
    )
    # A console of its own, so chcp leaves alone the one the other tests share.
    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        with console_process(
            f"chcp 1251 && {subprocess.list2cmdline(crawl.argv)}",
            env=crawl.env,
            stdout=stdout.fileno(),
            stderr=stderr.fileno(),
        ) as process:
            process.communicate(timeout=CRAWL_PROCESS_TIMEOUT)
        stdout.seek(0)
        stderr.seek(0)
        output, errors = stdout.read(), stderr.read()
    crawl_files = [
        event["data"]["crawl_file"]
        for event in map(_utf8_json, errors.splitlines())
        if isinstance(event, dict) and event.get("event") == "crawl_started"
    ]

    # chcp prints the code page it set, in the console's language, before the Crawl runs.
    assert (
        [b"1251" in line for line in output.splitlines()[:1]],
        [query(Path(file), "SELECT title_1, title_1_length FROM pages") for file in crawl_files],
    ) == ([True], [[("Привет, мир", 11)]])


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console process trees")
def test_a_console_timeout_ends_the_controlled_process_tree() -> None:
    identities: list[psutil.Process] = []
    try:
        with socket.socket() as listener, TemporaryFile() as stdout, TemporaryFile() as stderr:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(10)
            command = python_command(
                "-m", "tests.support.console_tree", str(listener.getsockname()[1])
            )
            with console_process(
                subprocess.list2cmdline(command.argv),
                env=command.env,
                stdout=stdout.fileno(),
                stderr=stderr.fileno(),
            ) as process:
                root = psutil.Process(process.pid)
                root.create_time()
                identities.append(root)
                connection, _ = listener.accept()
                with connection, connection.makefile("rb") as ready:
                    connection.settimeout(10)
                    middle_pid, leaf_pid = json.loads(ready.readline(512))
                    for pid in (middle_pid, leaf_pid):
                        child = psutil.Process(pid)
                        child.create_time()
                        identities.append(child)
                    assert psutil.Process(middle_pid).ppid() == process.pid
                    assert psutil.Process(leaf_pid).ppid() == middle_pid
                    with pytest.raises(subprocess.TimeoutExpired):
                        process.communicate(timeout=0.1)

            assert [identity.is_running() for identity in identities] == [False, False, False]
    finally:
        # Independent of console_process, so its mutation cannot leak the deliberately hung tree.
        deadline = monotonic() + 5
        owned = list(identities)
        for identity in identities:
            with suppress(psutil.NoSuchProcess):
                owned.extend(identity.children(recursive=True))
        for identity in reversed(owned):
            with suppress(psutil.NoSuchProcess):
                identity.kill()
        _, alive = psutil.wait_procs(owned, timeout=max(0, deadline - monotonic()))
        assert alive == [], "the guard's independent cleanup left a process alive"


def _utf8_json(line: bytes) -> Any:
    try:
        return json.loads(line.decode("utf-8"))
    except ValueError:
        return None
