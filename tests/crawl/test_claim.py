"""A running Crawl owns its OS writer claim (060-add-crawl-control D12; seams 1, 3)."""

import subprocess
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site
from tests.support.cli import PROCESS_TIMEOUT, await_event, start_cli_process
from tests.support.processes import python_command
from tests.support.workspace import TempWorkspace

# Independent of the claim implementation: this probe must also run before it exists.
_PROBE = """
import errno
import sys

with open(sys.argv[1], "a+b") as file:
    if sys.platform == "win32":
        import msvcrt
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            sys.exit(10)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        try:
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (errno.EACCES, errno.EAGAIN):
                raise
            sys.exit(10)
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)
"""


@pytest.mark.slow
def test_a_running_crawl_keeps_its_writer_claim(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> None:
    server = fixture_site(
        Site(
            routes={
                "/": Page(body="<p>Waiting</p>", hang=True),
                "/probe-ready": Page(body="ready", after="/"),
            }
        )
    )
    process = start_cli_process("crawl", server.url("/"))
    try:
        started = await_event(process, "crawl_started")
        crawl_file = Path(started["crawl_file"])
        lock_file = crawl_file.with_name(f"{started['crawl_id']}.lock")
        # crawl_started precedes the writer opening; the HTTP handshake proves it is running.
        with closing(
            HTTPConnection("127.0.0.1", urlsplit(server.base_url).port, timeout=PROCESS_TIMEOUT)
        ) as connection:
            connection.request("GET", "/probe-ready")
            with connection.getresponse() as response:
                assert (response.status, response.read()) == (200, b"ready")

        command = python_command("-c", _PROBE, str(lock_file))
        probe = subprocess.run(
            command.argv,
            env=command.env,
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )

        assert (probe.returncode, process.poll()) == (10, None), probe.stderr
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=PROCESS_TIMEOUT)
