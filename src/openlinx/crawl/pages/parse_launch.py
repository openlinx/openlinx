"""Launch POSIX spawn workers inside the guardian's group before Python runs."""

import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import ExitStack
from multiprocessing import reduction, resource_tracker, spawn
from multiprocessing.context import SpawnProcess, set_spawning_popen
from multiprocessing.process import BaseProcess
from multiprocessing.util import Finalize
from tempfile import TemporaryFile

if sys.platform != "win32":
    from multiprocessing.popen_spawn_posix import Popen

    class _WorkerPopen(Popen):
        # The spawn reducers append the descriptors referenced by the serialized process.
        _fds: list[int]

        def _launch(self, process_obj: BaseProcess) -> None:
            if not isinstance(process_obj, PosixWorker):
                raise TypeError("The POSIX worker launcher needs a group and a startup lease.")
            tracker = resource_tracker.getfd()
            if tracker is None:
                raise RuntimeError("The spawn resource tracker has no descriptor.")
            preparation = spawn.get_preparation_data(process_obj.name)
            with TemporaryFile() as start_data, ExitStack() as parent, ExitStack() as child:
                # The import of __main__ and the spawn reducers still belong to multiprocessing.
                # A file lets start return even if Python hangs before reading these bytes.
                set_spawning_popen(self)
                try:
                    reduction.dump(preparation, start_data)
                    reduction.dump(process_obj, start_data)
                finally:
                    set_spawning_popen(None)
                start_data.seek(0)
                exited, exit_writer = os.pipe()
                parent.callback(os.close, exited)
                child.callback(os.close, exit_writer)
                owner, owner_writer = os.pipe()
                parent.callback(os.close, owner_writer)
                child.callback(os.close, owner)
                command = spawn.get_command_line()
                # As in spawn_main, use the existing resource tracker and the parent's sentinel.
                command[-2] = (
                    "import os; from multiprocessing import resource_tracker, spawn; "
                    f"os.close({process_obj.lease}); "
                    f"resource_tracker._resource_tracker._fd = {tracker}; "
                    f"raise SystemExit(spawn._main({start_data.fileno()}, {owner}))"
                )
                self._child: subprocess.Popen[bytes] = subprocess.Popen(  # noqa: S603 - spawn argv
                    command,
                    pass_fds=(
                        *self._fds,
                        tracker,
                        start_data.fileno(),
                        exit_writer,
                        owner,
                        process_obj.lease,
                    ),
                    process_group=process_obj.group,
                )
                self.pid = self._child.pid
                self.sentinel = exited
                self.finalizer = Finalize(self, parent.pop_all().close)

        def poll(self, flag: int = os.WNOHANG) -> int | None:
            # Keep exactly one waitpid owner for this Popen.
            self.returncode = self._child.poll() if flag == os.WNOHANG else self._child.wait()
            return self.returncode

    class PosixWorker(SpawnProcess):
        """Give each fresh interpreter a process group and a pre-bootstrap lease."""

        def __init__(
            self,
            target: Callable[..., None],
            args: tuple[object, ...],
            name: str,
            group: int,
            lease: int,
        ) -> None:
            super().__init__(target=target, args=args, name=name, daemon=True)
            self.group = group
            self.lease = lease

        @staticmethod
        def _Popen(process_obj: BaseProcess) -> Popen:
            return _WorkerPopen(process_obj)
