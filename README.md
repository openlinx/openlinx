# spider

[![CI](https://github.com/bogzak/seo_spider/actions/workflows/ci.yml/badge.svg)](https://github.com/bogzak/seo_spider/actions/workflows/ci.yml)

`spider` is the working name of an open-source, agent-first SEO crawler, in the spirit of Screaming Frog SEO Spider but with no GUI.

AI agents drive it through a command-line tool, and a local MCP server is coming in v0.1.1:
- They run a Crawl of a website.
- They query what the Crawl recorded, including its Issues: the Rules that fired.
- They turn the results into a Report for people.

A Skill teaches the agent when and how to use each Command. The tool itself never calls an LLM ([ADR-0004](docs/adr/0004-tool-never-calls-an-llm.md)).

## Status

Pre-release: there is no release yet.
- **Progress:** the scaffold (`000-scaffold-project`) and `010-add-workspace-and-cli-contract` are done and archived: Workspaces, `spider.toml` settings, `spider init`, `spider commands` and the CLI contract that every later Command follows. Next is `015-add-crawl-store`. There is no crawling yet.
- **Name:** the product name is still open. `spider` is a placeholder for the command, the Python package, `spider.toml` and the `.spider/` directory of each Workspace.

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

- [ROADMAP.md](ROADMAP.md): the changes planned for v0.1 and v0.1.1, and their build order.
- [CONTEXT.md](CONTEXT.md): the glossary. Every doc, test and piece of code uses its terms.
- [docs/architecture.md](docs/architecture.md): how the pieces fit together.
- [docs/crawl-store.md](docs/crawl-store.md): how each Crawl is stored as one SQLite file, and how it is written and read.
- [docs/schema.md](docs/schema.md): the public schema of a crawl file, for querying it with SQL.
- [docs/adr/](docs/adr/): the decisions behind them.
- [docs/testing.md](docs/testing.md): how everything is tested.
- [CONTRIBUTING.md](CONTRIBUTING.md): setting up, running the checks and making a change.

## License

[Apache License 2.0](LICENSE).
