"""Run a real Crawl with an observed parse worker in a foreground process."""

import ctypes
import os
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import replace
from functools import partial
from multiprocessing.process import BaseProcess
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from unittest.mock import patch

import msgspec
from selectolax.lexbor import LexborHTMLParser

from openlinx.crawl.pages.parse_pool import PoolExecutor
from openlinx.crawl.pages.preparation import PageInput, extractor
from openlinx.output.reporter import Collected
from openlinx.services.hooks import default_hooks
from tests.support.crawling import crawl_result


class Probe(msgspec.Struct, frozen=True):
    folder: Path
    phase: str

    def __post_init__(self) -> None:
        if self.phase == "starting" and os.environ.get("PARSE_OWNER_PID") != str(os.getpid()):
            block(self.folder)


class Observed(msgspec.Struct, frozen=True):
    pid: int


def block(folder: Path) -> None:
    # PyDLL keeps the GIL held during the read, as a wedged native parser can.
    if sys.platform == "linux":
        reader, writer = os.pipe()
        try:
            (folder / "blocked").write_text(str(os.getpid()), encoding="ascii")
            ctypes.PyDLL(None).read(reader, ctypes.create_string_buffer(1), 1)
        finally:
            os.close(writer)
            os.close(reader)
    else:
        (folder / "blocked").write_text(str(os.getpid()), encoding="ascii")
        threading.Event().wait(90)


def prepare(tree: LexborHTMLParser, page: PageInput, config: Probe) -> Observed:
    if page.url.endswith("/die"):
        os._exit(3)
    if page.url.endswith("/hang"):
        block(config.folder)
    if page.url.endswith("/"):
        (config.folder / "prepared").write_text(str(os.getpid()), encoding="ascii")
    return Observed(os.getpid())


class Notes(Collected):
    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = folder

    def event(self, name: str, **data: Any) -> None:
        super().event(name, **data)
        if name == "crawl_started":
            (self.folder / "crawl_file").write_text(data["crawl_file"], encoding="utf-8")
        if name == "stopping":
            (self.folder / "stopping").write_text(data["reason"], encoding="ascii")


def _sockets() -> tuple[int, ...]:
    sockets = []
    for entry in Path("/proc/self/fd").iterdir():
        descriptor = int(entry.name)
        with suppress(OSError):
            if descriptor > 2 and stat.S_ISSOCK(os.fstat(descriptor).st_mode):
                sockets.append(descriptor)
    return tuple(sockets)


@contextmanager
def _hold_spawn_handoff(folder: Path, *, retain_sockets: bool) -> Iterator[None]:
    spawn = BaseProcess.start

    def start(process: BaseProcess) -> None:
        spawn(process)
        if process.name != "parse-worker-0":
            return
        if retain_sockets:
            kept = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                pass_fds=_sockets(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            (folder / "retained").write_text(str(kept.pid), encoding="ascii")
        (folder / "spawned").write_text(str(process.pid), encoding="ascii")
        threading.Event().wait(20)

    with patch.object(BaseProcess, "start", start):
        yield


def main(url: str, folder: Path, phase: str) -> int:
    os.environ["PARSE_OWNER_PID"] = str(os.getpid())
    if sys.platform == "linux" and phase in {"pre_admission", "bootstrap_handoff"}:
        with _hold_spawn_handoff(folder, retain_sockets=phase == "pre_admission"):
            return _crawl(url, folder, phase)
    return _crawl(url, folder, phase)


def _await_observer(marker: Path) -> None:
    deadline = monotonic() + 15
    while not marker.exists():
        if monotonic() >= deadline:
            raise RuntimeError(f"The observer did not create {marker.name}.")
        sleep(0.01)


def _crawl(url: str, folder: Path, phase: str) -> int:
    if phase == "complete":
        _await_observer(folder / "allow_start")
    hooks = default_hooks()
    probe = extractor("probe", prepare, Probe(folder, phase))
    result = crawl_result(
        url,
        replace(hooks, extractors=(*hooks.extractors, probe)),
        pages=partial(PoolExecutor, workers=1),
        reporter=Notes(folder),
    )
    if phase == "complete":
        (folder / "closed").write_text("closed", encoding="ascii")
        _await_observer(folder / "allow_exit")
    return 130 if result.summary.stop_reason == "interrupt" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], Path(sys.argv[2]), sys.argv[3]))
