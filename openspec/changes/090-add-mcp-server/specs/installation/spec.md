## MODIFIED Requirements

### Requirement: Release workflow
`.github/workflows/release.yml` SHALL run on pushes of tags that match `v*`, with jobs in this order:

| Job | What it does |
|---|---|
| `verify` | `scripts/release_check.py` and the test suite |
| `build` | `uv build` (wheel and sdist), `scripts/build_mcpb.py` from `090-add-mcp-server`, and a `SHA256SUMS` file |
| `smoke` | the installer smoke tests with the built wheel |
| `publish` | PyPI trusted publishing, in the `pypi` environment with `id-token: write` and no stored API token |
| `release` | a GitHub release with the wheel, the sdist, `openlinx-<version>.mcpb`, `install.sh`, `install.ps1` and `SHA256SUMS`, marked as a pre-release when `release_check.py` reports `prerelease: true` |

A failure before `publish` SHALL leave nothing published.

#### Scenario: Tag trigger
- **WHEN** `.github/workflows/release.yml` is parsed
- **THEN** `on.push.tags` is `["v*"]`

#### Scenario: Job order
- **WHEN** the workflow is parsed
- **THEN** `publish` needs `verify`, `build` and `smoke`, and `release` needs `publish`

#### Scenario: Trusted publishing only
- **WHEN** the workflow is parsed
- **THEN** the `publish` job has `permissions.id-token` `write` and `environment` `pypi`, and no step of any job references a secret whose name contains `PYPI`

#### Scenario: Bundle built in the release
- **WHEN** the workflow is parsed
- **THEN** a step of the `build` job runs `scripts/build_mcpb.py`, before the step that writes `SHA256SUMS`

#### Scenario: Bundle is a release asset
- **WHEN** the workflow is parsed
- **THEN** the `release` job uploads `openlinx-<version>.mcpb` together with the wheel, the sdist, both scripts and `SHA256SUMS`

### Requirement: Supported Python range
The package SHALL declare `requires-python = ">=3.12,<3.15"` and classifiers for Python 3.12, 3.13 and 3.14. Both install scripts SHALL declare the Python version they pass to `--python` as `3.14`. That version SHALL satisfy `requires-python`, and SHALL equal the `.python-version` of the `090-add-mcp-server` bundle. `docs/installation.md` SHALL explain two reasons for the pin:
- uv issue #14110
- the missing Python 3.15 wheels for aiohttp, selectolax, msgspec and zstandard

It SHALL also say that the pin will be raised when those wheels ship.

#### Scenario: Pins agree
- **WHEN** `requires-python` from `pyproject.toml`, the Python version declared in both install scripts, and `packaging/mcpb/.python-version` are read
- **THEN** `requires-python` is `>=3.12,<3.15`, both scripts and `.python-version` say `3.14`, and `3.14` satisfies `requires-python`

#### Scenario: Wheel metadata
- **WHEN** the `Requires-Python` field in the `METADATA` of the wheel built by `uv build` is parsed as a specifier set
- **THEN** it equals the specifier set `>=3.12,<3.15`

#### Scenario: Pin explained
- **WHEN** `docs/installation.md` is read
- **THEN** it contains `#14110` and the names aiohttp, selectolax, msgspec and zstandard
