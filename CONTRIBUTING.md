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

## Adding a dependency

- **Runtime:** `uv add <name>`. In the same commit, add the new package and everything it pulls in to `tests/dependency_allowlist.txt`, one name per line with a short reason. `uv run pytest tests/test_dependencies.py --no-cov` names whatever is missing. Telemetry and LLM SDKs are refused even when allowlisted.
- **Development only:** `uv add --dev <name>`. The allowlist covers runtime dependencies only.

## Code style

- Write a comment only for a non-obvious *why*. Don't add a docstring to a function or method whose name and types already say what it does, and don't add a comment that restates the code.
- Each module starts with a one-line docstring that names the design decision it implements, such as "design D7 of 000-scaffold-project". An empty `__init__.py` that only marks a test package needs none.
