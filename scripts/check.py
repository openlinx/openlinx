"""Run the CI gates locally in CI's order (design D11 of 000-scaffold-project).

Usage: uv run scripts/check.py
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PYTHON_GATES: list[tuple[str, list[str]]] = [
    ("ruff check", ["ruff", "check", "."]),
    ("ruff format --check", ["ruff", "format", "--check", "."]),
    ("mypy", ["mypy"]),
    ("pytest", ["pytest"]),
]


def run(name: str, command: Sequence[str], env: Mapping[str, str] | None = None) -> None:
    print(f"==> {name}", flush=True)
    code = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False).returncode
    if code != 0:
        print(f"FAILED: {name} (exit code {code})", file=sys.stderr, flush=True)
        sys.exit(code)


def main() -> None:
    for name, args in PYTHON_GATES:
        run(name, [sys.executable, "-m", *args])

    openspec = shutil.which("openspec")
    if openspec is None:
        print("SKIPPED: openspec validate (openspec is not on PATH; CI runs it)", flush=True)
    else:
        run(
            "openspec validate --all --strict",
            [openspec, "validate", "--all", "--strict"],
            env={**os.environ, "OPENSPEC_TELEMETRY": "0"},
        )

    print("All checks passed.", flush=True)


if __name__ == "__main__":
    main()
