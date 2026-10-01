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
- **Progress:** the scaffold is done (change `000-scaffold-project`, archived), and so far `spider` only prints its version. The next change is `010-add-workspace-and-cli-contract`.
- **Name:** the product name is still open. `spider` is a placeholder for the command, the Python package, `spider.toml` and the `.spider/` directory of each Workspace.

## Development quick start

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` by itself.

```
uv sync
uv run spider --version
```

## Learn more

- [ROADMAP.md](ROADMAP.md): the changes planned for v0.1 and v0.1.1, and their build order.
- [CONTEXT.md](CONTEXT.md): the glossary. Every doc, test and piece of code uses its terms.
- [docs/architecture.md](docs/architecture.md): how the pieces fit together.
- [docs/adr/](docs/adr/): the decisions behind them.
- [docs/testing.md](docs/testing.md): how everything is tested.
- [CONTRIBUTING.md](CONTRIBUTING.md): setting up, running the checks and making a change.

## License

[Apache License 2.0](LICENSE).
