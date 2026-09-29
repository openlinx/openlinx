# spider

`spider` is the working name of an open-source, agent-first SEO crawler: a command-line tool and a local MCP server that AI agents drive to crawl a website and find its technical SEO issues, in the spirit of Screaming Frog SEO Spider but without a GUI. It is in early development and has no release yet; the plan is in [ROADMAP.md](ROADMAP.md).

## Status

Pre-release. The project scaffold is being built (change `000-scaffold-project`): so far `spider` only prints its version. The product name is still open; `spider` is a placeholder.

## Development quick start

You need [uv](https://docs.astral.sh/uv/). It installs the Python version from `.python-version` by itself.

```
uv sync
uv run spider --version
```
