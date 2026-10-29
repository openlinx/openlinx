# OpenLinx

[![CI](https://github.com/openlinx/openlinx/actions/workflows/ci.yml/badge.svg)](https://github.com/openlinx/openlinx/actions/workflows/ci.yml)

OpenLinx is an open-source, agent-first SEO crawler. It runs locally and stores each Crawl as a SQLite file with a public, versioned schema, so an agent can query it with arbitrary read-only SQL (`sql`, coming in v0.1), and every Issue it reports can be reproduced by a query. It has no GUI, no account and no telemetry. If you know desktop SEO crawlers such as Screaming Frog, the column names will be familiar.

OpenLinx runs as the `linx` command, and its Python package is `openlinx`.

AI agents drive it through a command-line tool, and a local MCP server is coming in v0.1.1:
- They run a Crawl of a website.
- They query what the Crawl recorded, including its Issues: the Rules that fired.
- They turn the results into a Report for people.

A Skill teaches the agent when and how to use each Command. The tool itself never calls an LLM ([ADR-0004](docs/adr/0004-tool-never-calls-an-llm.md)).

## Status

Pre-release: there is no release yet.
- **Progress:** done and archived: the scaffold (`000`), Workspaces and the CLI contract (`010`), the crawl store (`015`), the faster crawl writer (`017`), the schema conventions (`018`) and the crawl core (`020`). That is `linx init`, `linx commands`, `linx schema`, `--crawl`, one SQLite file per Crawl with a documented schema, and `linx crawl <url>`, which crawls a site in the foreground. [ROADMAP.md](ROADMAP.md) says where the build is.
- **Name:** OpenLinx: the command `linx`, the PyPI and import package `openlinx`, the GitHub organisation `openlinx`, `openlinx.toml` and the `.openlinx/` directory of each Workspace.

## Development quick start

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` by itself.

```
uv sync
uv run linx --version
```

## Using OpenLinx

Make a folder a Workspace, the place where Crawls and settings live:

```
linx init
```

It creates `.openlinx/` (Crawl data, git-ignored) and a commented `openlinx.toml`, and prints what it made as JSON:

```json
{"workspace":"/home/me/shop","data_dir":"/home/me/shop/.openlinx","settings_file":"/home/me/shop/openlinx.toml","global":false,"created":["/home/me/shop/.openlinx","/home/me/shop/.openlinx/.gitignore","/home/me/shop/.openlinx/crawls","/home/me/shop/openlinx.toml"]}
```

Ask the tool to describe itself, as an agent does before anything else:

```
linx commands
```

It prints one JSON document with every Command, its options and output, the exit codes, every diagnostic code and the environment variables it honours. See [docs/cli.md](docs/cli.md) for the contract every Command follows and [docs/workspace.md](docs/workspace.md) for Workspaces and `openlinx.toml`.

## Learn more

- [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md): how to make a change and open a pull request, for people and coding agents.
- [ROADMAP.md](ROADMAP.md): the changes planned for v0.1 and v0.1.1, and their build order.
- [CONTEXT.md](CONTEXT.md): the glossary. Every doc, test and piece of code uses its terms.
- [docs/architecture.md](docs/architecture.md): how the pieces fit together.
- [docs/crawling.md](docs/crawling.md): `linx crawl`, its options, and how URLs, Scope and Links work.
- [docs/crawl-store.md](docs/crawl-store.md): how each Crawl is stored as one SQLite file, and how it is written and read.
- [docs/schema.md](docs/schema.md): the public schema of a crawl file, for querying it with SQL.
- [docs/adr/](docs/adr/): the decisions behind them.
- [docs/testing.md](docs/testing.md): how everything is tested.
- [docs/benchmarks.md](docs/benchmarks.md): measured capacity, and the machine it was measured on.

## License

[Apache License 2.0](LICENSE).
