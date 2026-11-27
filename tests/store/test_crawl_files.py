"""Verify Crawl file creation within a Workspace."""

import errno
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.reporter import Collected
from openlinx.services.crawls import create_crawl
from openlinx.store.claim import claim_writer
from openlinx.store.records import CrawlFile
from openlinx.workspace.discovery import resolve_workspace
from tests.support.cli import PROCESS_TIMEOUT, REPO_ROOT
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, new_crawl
from tests.support.permissions import unwritable_folder
from tests.support.processes import python_command
from tests.support.randomness import scripted_choice
from tests.support.workspace import TempWorkspace


def test_location_of_a_crawl_file(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".openlinx" / "crawls").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    with create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    ):
        pass

    assert (shop / ".openlinx" / "crawls" / "20260927-140312-k3f9.sqlite").is_file()


def test_first_crawl_in_the_global_workspace(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    with create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    ):
        pass

    data = temp_workspace.home / ".openlinx"
    assert (
        (data / "crawls" / "20260927-140312-k3f9.sqlite").is_file(),
        (data / ".gitignore").is_file(),
    ) == (
        True,
        True,
    )


def test_no_settings_file_is_created_by_storing_a_crawl(temp_workspace: TempWorkspace) -> None:
    shop = temp_workspace.root / "shop"
    (shop / ".openlinx").mkdir(parents=True)
    workspace = resolve_workspace(cwd=shop, flag=None, home=temp_workspace.home)

    with create_crawl(
        new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9")
    ):
        pass

    assert not (shop / "openlinx.toml").exists()


def test_unwritable_data_folder(temp_workspace: TempWorkspace) -> None:
    data = temp_workspace.home / ".openlinx"
    data.write_text("not a folder", encoding="utf-8")
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)

    with (
        pytest.raises(OpenLinxError) as raised,
        create_crawl(new_crawl(workspace), FakeClock(), Collected()),
    ):
        pass

    assert (raised.value.code, raised.value.diagnostic.details["path"].startswith(str(data))) == (
        "workspace_not_writable",
        True,
    )


def test_a_taken_id_is_drawn_again(temp_workspace: TempWorkspace) -> None:
    crawls = temp_workspace.home / ".openlinx" / "crawls"
    crawls.mkdir(parents=True)
    (crawls / "20260927-140312-k3f9.sqlite").touch()
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    clock = FakeClock(start=datetime(2026, 9, 27, 14, 3, 12, 900000, tzinfo=UTC))

    with create_crawl(
        new_crawl(workspace), clock, Collected(), scripted_choice("k3f9m2p7")
    ) as crawl:
        pass

    assert crawl.id == "20260927-140312-m2p7"


def test_an_id_with_a_writer_claim_file_is_drawn_again(temp_workspace: TempWorkspace) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    workspace.crawls_dir.mkdir(parents=True)
    lock = workspace.crawls_dir / "20260927-140312-k3f9.lock"
    lock.write_bytes(b"reserved")
    clock = FakeClock(start=datetime(2026, 9, 27, 14, 3, 12, 900000, tzinfo=UTC))

    with create_crawl(
        new_crawl(workspace), clock, Collected(), scripted_choice("k3f9m2p7")
    ) as crawl:
        pass

    assert (crawl.id, lock.read_bytes(), lock.with_suffix(".sqlite").exists()) == (
        "20260927-140312-m2p7",
        b"reserved",
        False,
    )


_CREATE_WITH_COLLIDING_ID = """
import sys
from pathlib import Path

from openlinx.output.reporter import Collected
from openlinx.services.crawls import create_crawl
from openlinx.workspace.discovery import resolve_workspace
from tests.support.clock import FakeClock
from tests.support.crawls import STARTED_AT, new_crawl
from tests.support.randomness import scripted_choice

workspace = resolve_workspace(cwd=Path(sys.argv[1]), home=Path(sys.argv[2]), flag=None)
with create_crawl(
    new_crawl(workspace), FakeClock(start=STARTED_AT), Collected(), scripted_choice("k3f9m2p7")
) as crawl:
    print(crawl.id)
"""


@pytest.mark.slow
def test_an_id_claimed_before_its_sqlite_file_exists_is_drawn_again(
    temp_workspace: TempWorkspace,
) -> None:
    workspace = resolve_workspace(cwd=temp_workspace.root, flag=None, home=temp_workspace.home)
    workspace.crawls_dir.mkdir(parents=True)
    held = CrawlFile("20260927-140312-k3f9", workspace.crawls_dir / "20260927-140312-k3f9.sqlite")
    command = python_command(
        "-c", _CREATE_WITH_COLLIDING_ID, str(temp_workspace.root), str(temp_workspace.home)
    )

    with claim_writer(held):
        created = subprocess.run(
            command.argv,
            cwd=REPO_ROOT,
            env=command.env,
            capture_output=True,
            text=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )

    assert (created.returncode, created.stdout) == (0, "20260927-140312-m2p7\n"), created.stderr


@pytest.mark.skipif(
    sys.implementation.name != "cpython"
    or sys.version_info[:2] != (3, 12)
    or sys.platform == "win32",
    reason="CPython 3.12 POSIX resolves symlink chains recursively",
)
def test_writer_claim_propagates_recursion_error_from_an_acyclic_symlink_chain(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.sqlite"
    target.touch()
    for index in range(sys.getrecursionlimit()):
        link = tmp_path / f"link-{index}.sqlite"
        link.symlink_to(target.name)
        target = link
    crawl = CrawlFile("20260927-140312-k3f9", target)

    active_error = OSError(errno.ELOOP, "An unrelated symlink loop")
    try:
        raise active_error
    except OSError:
        with pytest.raises(RecursionError) as caught, claim_writer(crawl):
            pytest.fail("The writer claim was acquired despite the resolution failure")

        assert caught.value.__context__ is active_error


def test_writer_claim_propagates_an_unrelated_symlink_loop_from_its_body(tmp_path: Path) -> None:
    crawl = CrawlFile("20260927-140312-k3f9", tmp_path / "20260927-140312-k3f9.sqlite")
    failure = RuntimeError("Owner failed")
    # Match the implicit chain that Path.resolve creates on Python 3.12.
    failure.__context__ = OSError(errno.ELOOP, "An unrelated symlink loop")

    with pytest.raises(RuntimeError) as caught, claim_writer(crawl):
        raise failure

    assert caught.value is failure


def test_unwritable_crawls_folder(temp_workspace: TempWorkspace) -> None:
    crawls = temp_workspace.root / "shop" / ".openlinx" / "crawls"
    crawls.mkdir(parents=True)
    workspace = resolve_workspace(cwd=crawls.parent.parent, flag=None, home=temp_workspace.home)

    with (
        unwritable_folder(crawls),
        pytest.raises(OpenLinxError) as raised,
        create_crawl(new_crawl(workspace), FakeClock(), Collected()),
    ):
        pass

    assert (raised.value.code, raised.value.diagnostic.details["path"].startswith(str(crawls))) == (
        "workspace_not_writable",
        True,
    )
