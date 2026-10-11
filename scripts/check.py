"""Run the CI gates locally in CI's order (design D11 of 000-scaffold-project)."""

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Node expands the glob itself; since Node 22 a bare folder is loaded as one module and fails.
JS_TESTS = "tests/js/**/*.test.mjs"

PYTHON_GATES: list[list[str]] = [
    ["ruff", "check", "."],
    ["ruff", "format", "--check", "."],
    ["mypy"],
    # typeshed types some stdlib names per platform (os.altsep is None off Windows), so one OS
    # alone misses the others' errors. A cache per platform keeps the passes warm.
    ["mypy", "--platform", "linux", "--cache-dir", ".mypy_cache/linux"],
    ["mypy", "--platform", "darwin", "--cache-dir", ".mypy_cache/darwin"],
    ["pytest"],
]


def run(name: str, command: Sequence[str], env: Mapping[str, str] | None = None) -> None:
    print(f"==> {name}", flush=True)
    code = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False).returncode
    if code != 0:
        message = f"FAILED: {name} (exit code {code})"
        print(message, file=sys.stderr, flush=True)  # noqa: TID251 - not spider's output
        sys.exit(code)


def main() -> None:
    for args in PYTHON_GATES:
        run(" ".join(args), [sys.executable, "-m", *args])

    openspec = shutil.which("openspec")
    if openspec is None:
        print("SKIPPED: openspec validate (openspec is not on PATH; CI runs it)", flush=True)
    else:
        run(
            "openspec validate --all --strict",
            [openspec, "validate", "--all", "--strict"],
            env={**os.environ, "OPENSPEC_TELEMETRY": "0"},
        )

    node = shutil.which("node")
    if node is None:
        print("SKIPPED: node --test (node is not on PATH; CI runs it)", flush=True)
    else:
        run(f'node --test "{JS_TESTS}"', [node, "--test", JS_TESTS])

    print("All checks passed.", flush=True)


if __name__ == "__main__":
    main()
