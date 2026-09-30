# Contributing

## Set up

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` and the locked dependencies:

```
uv sync
```

## Checks

Run CI's gates in CI's order. The script stops at the first failure. Only the wheel smoke test is left to CI:

```
uv run scripts/check.py
```

Each gate on its own:

| Gate | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format --check .` (`uv run ruff format .` fixes it) |
| Types | `uv run mypy` |
| Tests and coverage | `uv run pytest` |
| Specs | `openspec validate --all --strict` |
| Report script (seam 9) | `node --test "tests/js/**/*.test.mjs"` |

- **One test file:** add `--no-cov`, for example `uv run pytest tests/cli/test_version.py --no-cov`. The 90% coverage gate is meant for the whole suite, and a partial run can fall below it.
- **Specs:** `openspec` is a Node tool. If it is not on `PATH`, the check script skips this step with a notice, and CI still runs it. Turn off its telemetry first: `export OPENSPEC_TELEMETRY=0` in bash, `$env:OPENSPEC_TELEMETRY = "0"` in PowerShell. The check script sets it by itself.
- **Report script:** also needs Node, and is skipped with a notice without it. Keep the quotes around the glob: Node expands it itself.

## What CI runs

`.github/workflows/ci.yml` runs on:
- every push to `main`
- every pull request
- a manual run ("Run workflow" on the Actions page)

A push to any other branch runs nothing until a pull request is open for it.

Each run is a matrix of 9 cells: Ubuntu, macOS and Windows × Python 3.12, 3.13 and 3.14. No cell stops the others, and each has a 30-minute limit. A newer push to the same branch or PR cancels the run in progress.

Every cell runs these steps in order, all in bash, including on Windows. It stops at the first failure:

1. Check out the code, and install uv with the cell's Python.
2. `uv sync --locked`, which fails if `uv.lock` is out of date.
3. Check that the cell really runs its matrix Python, since `.python-version` pins 3.12.
4. `ruff check .`, then `ruff format --check .`.
5. `mypy` (strict).
6. `pytest`, with the 90% coverage gate and the hypothesis `ci` profile.
7. `uv build`, then `spider --version` from the built wheel in an isolated environment.
8. Install Node (current LTS) and OpenSpec 1.13.0, then `openspec validate --all --strict` with telemetry off.
9. `node --test "tests/js/**/*.test.mjs"`.

Steps 4 to 9 are the gates `uv run scripts/check.py` runs locally, except the wheel check.

## Adding a dependency

- **Runtime:** `uv add <name>`. In the same commit, add the new package and everything it pulls in to `tests/dependency_allowlist.txt`, one name per line with a short reason. `uv run pytest tests/test_dependencies.py --no-cov` names whatever is missing. Telemetry and LLM SDKs are refused even when allowlisted.
- **Development only:** `uv add --dev <name>`. The allowlist covers runtime dependencies only.

## Code style

- Write a comment only for a non-obvious *why*. Don't add a docstring to a function or method whose name and types already say what it does, and don't add a comment that restates the code.
- Each module starts with a one-line docstring that names the design decision it implements, such as "design D7 of 000-scaffold-project". An empty `__init__.py` that only marks a test package needs none.
