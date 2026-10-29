# OpenLinx

[![CI](https://github.com/bogzak/seo_spider/actions/workflows/ci.yml/badge.svg)](https://github.com/bogzak/seo_spider/actions/workflows/ci.yml)

OpenLinx is an open-source, agent-first SEO crawler. It runs locally and stores each Crawl as a SQLite file with a public, versioned schema, so an agent can query it with arbitrary read-only SQL (`sql`, coming in v0.1), and every Issue it reports can be reproduced by a query. It has no GUI, no account and no telemetry. If you know desktop SEO crawlers such as Screaming Frog, the column names will be familiar.

`spider` is the working name of the command and the Python package until a rename change moves them to OpenLinx.

AI agents drive it through a command-line tool, and a local MCP server is coming in v0.1.1:
- They run a Crawl of a website.
- They query what the Crawl recorded, including its Issues: the Rules that fired.
- They turn the results into a Report for people.

A Skill teaches the agent when and how to use each Command. The tool itself never calls an LLM ([ADR-0004](docs/adr/0004-tool-never-calls-an-llm.md)).

## Status

Pre-release: there is no release yet.
- **Progress:** done and archived: the scaffold (`000`), Workspaces and the CLI contract (`010`), the crawl store (`015`), the faster crawl writer (`017`) and the schema conventions (`018`). That is `spider init`, `spider commands`, `spider schema`, `--crawl`, and one SQLite file per Crawl with a documented schema. `020-add-crawl-core` is in progress: its first part is merged, so `spider crawl <url>` crawls a site in the foreground. [ROADMAP.md](ROADMAP.md) says where the build is.
- **Name:** the product is OpenLinx (PyPI `openlinx`, GitHub organisation `openlinx`). `spider` is the working name of the command, the Python package, `spider.toml` and the `.spider/` directory of each Workspace until the rename.

## Development quick start

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` by itself.

```
uv sync
uv run spider --version
```

## Using spider

Make a folder a Workspace, the place where Crawls and settings live:

```
spider init
```

It creates `.spider/` (Crawl data, git-ignored) and a commented `spider.toml`, and prints what it made as JSON:

```json
{"workspace":"/home/me/shop","data_dir":"/home/me/shop/.spider","settings_file":"/home/me/shop/spider.toml","global":false,"created":["/home/me/shop/.spider","/home/me/shop/.spider/.gitignore","/home/me/shop/.spider/crawls","/home/me/shop/spider.toml"]}
```

Ask the tool to describe itself, as an agent does before anything else:

```
spider commands
```

It prints one JSON document with every Command, its options and output, the exit codes, every diagnostic code and the environment variables it honours. See [docs/cli.md](docs/cli.md) for the contract every Command follows and [docs/workspace.md](docs/workspace.md) for Workspaces and `spider.toml`.

## Learn more

- [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md): how to make a change and open a pull request, for people and coding agents.
- [ROADMAP.md](ROADMAP.md): the changes planned for v0.1 and v0.1.1, and their build order.
- [CONTEXT.md](CONTEXT.md): the glossary. Every doc, test and piece of code uses its terms.
- [docs/architecture.md](docs/architecture.md): how the pieces fit together.
- [docs/crawling.md](docs/crawling.md): `spider crawl`, its options, and how URLs, Scope and Links work.
- [docs/crawl-store.md](docs/crawl-store.md): how each Crawl is stored as one SQLite file, and how it is written and read.
- [docs/schema.md](docs/schema.md): the public schema of a crawl file, for querying it with SQL.
- [docs/adr/](docs/adr/): the decisions behind them.
- [docs/testing.md](docs/testing.md): how everything is tested.
- [docs/benchmarks.md](docs/benchmarks.md): measured capacity, and the machine it was measured on.

## License

[Apache License 2.0](LICENSE).
