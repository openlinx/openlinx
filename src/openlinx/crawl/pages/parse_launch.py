"""Isolate parse children from owner interrupts before their interpreters run."""

import os
import subprocess
import sys
from collections.abc import Callable
from contextlib import ExitStack, suppress
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

else:
    import _winapi
    import msvcrt
    from multiprocessing.popen_spawn_win32 import Popen as WindowsPopen

    def _inheritable(handle: int, handles: ExitStack) -> int:
        current = _winapi.GetCurrentProcess()
        duplicate = _winapi.DuplicateHandle(
            current, handle, current, 0, True, _winapi.DUPLICATE_SAME_ACCESS
        )
        handles.callback(_winapi.CloseHandle, duplicate)
        return duplicate

    def _redirected_stream(std_handle: int, access: int, handles: ExitStack) -> int:
        handle = _winapi.GetStdHandle(std_handle)
        if handle and handle != _winapi.INVALID_HANDLE_VALUE:
            kind = _winapi.GetFileType(handle)
            if kind in (_winapi.FILE_TYPE_DISK, _winapi.FILE_TYPE_PIPE):
                return _inheritable(handle, handles)
        # Console buffers belong to the parent's console. Give each missing stream a
        # valid handle so redirected streams still work without that console.
        fd = os.open(os.devnull, access)
        handles.callback(os.close, fd)
        return _inheritable(msvcrt.get_osfhandle(fd), handles)

    # Only stdlib imports are available until spawn._main restores the owner's sys.path.
    _WINDOWS_BOOTSTRAP = """
import os
import _winapi
import msvcrt
from multiprocessing import spawn

try:
    token, _ = _winapi.ReadFile({ready}, 1)
except BrokenPipeError:
    raise SystemExit(1) from None
finally:
    _winapi.CloseHandle({ready})
if token != b"\\0":
    raise SystemExit(1)
descriptor = msvcrt.open_osfhandle({data}, os.O_RDONLY | os.O_BINARY)
raise SystemExit(spawn._main(descriptor, {owner}))
"""

    class _WindowsChildPopen(WindowsPopen):
        def __init__(self, process_obj: BaseProcess) -> None:
            preparation = spawn.get_preparation_data(process_obj.name)
            # Spawn reducers need a real child handle. Publish their output via a file so
            # start can return even if the child stalls before reading its bootstrap data.
            with TemporaryFile() as start_data, ExitStack() as handles, ExitStack() as process:
                reader, writer = _winapi.CreatePipe(None, 0)
                handles.callback(_winapi.CloseHandle, reader)
                handles.callback(_winapi.CloseHandle, writer)
                ready = _inheritable(reader, handles)
                data = _inheritable(msvcrt.get_osfhandle(start_data.fileno()), handles)
                current = _winapi.GetCurrentProcess()
                owner = _winapi.DuplicateHandle(
                    current, current, current, _winapi.SYNCHRONIZE, True, 0
                )
                handles.callback(_winapi.CloseHandle, owner)

                command = spawn.get_command_line()
                command[-2] = _WINDOWS_BOOTSTRAP.format(data=data, ready=ready, owner=owner)
                executable = spawn.get_executable()
                executable_path = os.path.normcase(executable)
                base: str = getattr(sys, "_base_executable", sys.executable)
                env = os.environ.copy()
                if executable_path == os.path.normcase(
                    sys.executable
                ) and executable_path != os.path.normcase(base):
                    # The venv redirector would own the handle we need for the interpreter.
                    command[0] = executable = base
                    env["__PYVENV_LAUNCHER__"] = sys.executable
                stdin = _redirected_stream(subprocess.STD_INPUT_HANDLE, os.O_RDONLY, handles)
                stdout = _redirected_stream(subprocess.STD_OUTPUT_HANDLE, os.O_WRONLY, handles)
                stderr = _redirected_stream(subprocess.STD_ERROR_HANDLE, os.O_WRONLY, handles)
                startup = subprocess.STARTUPINFO(
                    dwFlags=subprocess.STARTF_USESTDHANDLES
                    | getattr(subprocess, "STARTF_FORCEOFFFEEDBACK", 0),
                    hStdInput=stdin,
                    hStdOutput=stdout,
                    hStdError=stderr,
                    lpAttributeList={"handle_list": [ready, data, owner, stdin, stdout, stderr]},
                )
                # Ctrl+Break broadcasts reach every group on the sender's console.
                process_handle, thread_handle, pid, _ = _winapi.CreateProcess(
                    executable,
                    subprocess.list2cmdline(command),
                    None,
                    None,
                    True,
                    subprocess.CREATE_NO_WINDOW,
                    env,
                    None,
                    startup,
                )
                process.callback(_winapi.CloseHandle, process_handle)
                _winapi.CloseHandle(thread_handle)
                self.pid = pid
                self.returncode = None
                self._handle = self.sentinel = process_handle
                set_spawning_popen(self)
                try:
                    reduction.dump(preparation, start_data)
                    reduction.dump(process_obj, start_data)
                    start_data.flush()
                    start_data.seek(0)
                    _winapi.WriteFile(writer, b"\0")
                except Exception:
                    with suppress(PermissionError):
                        self.kill()
                    raise
                finally:
                    set_spawning_popen(None)
                self.finalizer = Finalize(self, process.pop_all().close)

    class WindowsChild(SpawnProcess):
        """Start a hidden Windows spawn child outside the Crawl's console."""

        @staticmethod
        def _Popen(process_obj: BaseProcess) -> WindowsPopen:
            return _WindowsChildPopen(process_obj)
