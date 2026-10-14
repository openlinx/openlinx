"""`spider crawl` over the Crawl Service (020-add-crawl-core D10, D11)."""

from pathlib import Path
from typing import Annotated, Any

import typer

from spider.cli.meta import Example, command_meta
from spider.cli.options import FormatOpt, OptionMeta, WorkspaceOpt, secret_names, setting_flags
from spider.cli.runner import Invocation
from spider.clock import SystemClock
from spider.naming import APP_NAME
from spider.output.writer import Format

CRAWL = "crawl"


@command_meta(
    name=CRAWL,
    output="document",
    formats=[Format.JSON, Format.TABLE],
    events=True,
    examples=[Example(f"{APP_NAME} {CRAWL} site.test", "Crawl https://site.test/.")],
)
def crawl(
    ctx: typer.Context,
    url: Annotated[
        str,
        typer.Argument(
            help="The Seed: an http or https URL, or a host such as site.test, which gets "
            "https://.",
            show_default=False,
        ),
    ],
    concurrency: Annotated[
        int,
        typer.Option(
            "--concurrency", min=1, max=50, help="The most requests in flight to one host, 1 to 50."
        ),
        OptionMeta(setting="crawl.concurrency"),
    ] = 5,
    exclude: Annotated[
        list[str] | None,
        typer.Option(
            "--exclude",
            help="A regular expression, searched for in each normalised URL; a URL it matches "
            "is never requested. Give it more than once for several patterns.",
            show_default=False,
        ),
        OptionMeta(setting="crawl.exclude"),
    ] = None,
    workspace_dir: WorkspaceOpt = None,
    output_format: FormatOpt = Format.JSON,
) -> dict[str, Any]:
    """Crawl a site from one Seed URL, in the foreground.

    Follows Links from the Seed within the Scope and records every URL in a new crawl file of
    the Workspace. Progress events go to stderr, and the result to stdout when the Crawl ends.
    """
    # Imported here: the crawler stays off the CLI's startup path.
    from spider.crawl.hooks import default_hooks
    from spider.services.crawling import CrawlRequest, plan_crawl, start_crawl

    invocation: Invocation = ctx.obj
    request = CrawlRequest(
        seed=url,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=workspace_dir,
        command_argv=[APP_NAME, *invocation.argv],
        secret_names=secret_names(ctx.command, invocation.settings_tables),
        flags=setting_flags(ctx),
    )
    plan = plan_crawl(request, invocation.settings_tables)
    return start_crawl(plan, SystemClock(), invocation.reporter, default_hooks()).to_json()
