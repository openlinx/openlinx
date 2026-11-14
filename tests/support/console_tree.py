"""A controlled Windows tree waits after both Python descendants are ready (030 task 12.3)."""

import json
import os
import socket
import subprocess
import sys

from tests.support.processes import python_command


def main() -> None:
    port = int(sys.argv[1])
    if len(sys.argv) == 3:
        with socket.create_connection(("127.0.0.1", port)) as connection:
            connection.sendall(f"{os.getpid()}\n".encode())
            connection.recv(1)
        return

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(10)
        leaf = python_command(
            "-m", "tests.support.console_tree", str(listener.getsockname()[1]), "leaf"
        )
        child = subprocess.Popen(leaf.argv, env=leaf.env, stdin=subprocess.DEVNULL)
        connection, _ = listener.accept()
        with connection, connection.makefile("rb") as ready:
            connection.settimeout(10)
            leaf_pid = int(ready.readline(64))
            with socket.create_connection(("127.0.0.1", port)) as parent:
                parent.sendall(json.dumps([os.getpid(), leaf_pid]).encode() + b"\n")
                # Closing the test's handshake socket must not let a cleanup mutation pass.
                child.wait()


if __name__ == "__main__":
    main()
