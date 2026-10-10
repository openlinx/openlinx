"""Python processes that a test can kill (015-add-crawl-store)."""

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PythonCommand:
    argv: list[str]
    env: dict[str, str] | None


def python_command(*args: str) -> PythonCommand:
    base: str = getattr(sys, "_base_executable", sys.executable)
    if sys.platform == "win32" and sys.executable != base:
        # A venv's python.exe is a launcher that runs Python as its child, so a kill would miss
        # Python; the stdlib's multiprocessing starts the venv's base interpreter too (bpo-35797).
        env = {**os.environ, "__PYVENV_LAUNCHER__": sys.executable}
        return PythonCommand([base, *args], env)
    return PythonCommand([sys.executable, *args], None)
