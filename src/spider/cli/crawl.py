"""`spider crawl` over the Crawl Service (020-add-crawl-core D10, D11)."""

from pathlib import Path
from typing import Annotated, Any

import typer

from spider.cli.meta import Example, command_meta
from spider.cli.options import FormatOpt, OptionMeta, WorkspaceOpt, secret_names, setting_flags
from spider.cli.runner import Invocation
from spider.clock import SystemClock
from spider.naming import APP_NAME
from spider.output.codes import OPTION_CONFLICT
from spider.output.diagnostics import SpiderError
from spider.output.writer import Format
from spider.store.records import ScopeKind

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
    check_external: Annotated[
        bool,
        typer.Option(
            "--check-external/--no-check-external",
            help="Request each External URL once to record its response; with "
            "--no-check-external it is recorded as skipped, unrequested.",
        ),
        OptionMeta(setting="crawl.check_external"),
    ] = True,
    follow_nofollow: Annotated[
        bool,
        typer.Option(
            "--follow-nofollow",
            help="Follow nofollow hyperlinks, and every hyperlink of a Page whose robots "
            "directives say nofollow, like any other hyperlink.",
        ),
        OptionMeta(setting="crawl.follow_nofollow"),
    ] = False,
    max_depth: Annotated[
        int | None,
        typer.Option(
            "--max-depth",
            min=0,
            help="The deepest Crawl Depth whose URLs are requested, the Seed's being 0; "
            "Resources of followed Pages are requested one deeper. No limit by default.",
            show_default=False,
        ),
        OptionMeta(setting="crawl.max_depth"),
    ] = None,
    max_urls: Annotated[
        int | None,
        typer.Option(
            "--max-urls",
            help="The most URL requests over the Crawl's whole life; robots.txt requests do "
            "not count. No limit by default.",
            show_default=False,
        ),
        OptionMeta(setting="crawl.max_urls"),
    ] = None,
    scope: Annotated[
        ScopeKind,
        typer.Option(
            "--scope",
            help="Which Internal URLs are in the Scope: host (the Seed hosts), subdomains "
            "(every host of their registrable domains) or subfolder (the Seed's folder).",
        ),
        OptionMeta(setting="crawl.scope"),
    ] = "host",
    subdomains: Annotated[
        bool,
        typer.Option("--subdomains", help="The same as --scope subdomains."),
    ] = False,
    strip_params: Annotated[
        list[str] | None,
        typer.Option(
            "--strip-params",
            help="Comma-separated glob patterns of query parameter names, such as utm_*, "
            "removed from every URL before it is recorded or requested. Give it more than once "
            "for several values.",
            show_default=False,
        ),
        OptionMeta(setting="crawl.strip_params"),
    ] = None,
    include: Annotated[
        list[str] | None,
        typer.Option(
            "--include",
            help="A regular expression, searched for in each normalised URL; when given, an "
            "Internal URL that matches no include pattern is checked but not followed. Give it "
            "more than once for several patterns.",
            show_default=False,
        ),
        OptionMeta(setting="crawl.include"),
    ] = None,
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
    from spider.services.crawling import CrawlRequest, plan_crawl, start_crawl
    from spider.services.hooks import default_hooks

    invocation: Invocation = ctx.obj
    request = CrawlRequest(
        seed=url,
        cwd=Path.cwd(),
        home=Path.home(),
        workspace=workspace_dir,
        command_argv=[APP_NAME, *invocation.argv],
        secret_names=secret_names(ctx.command, invocation.settings_tables),
        flags=_with_subdomains(setting_flags(ctx)) if subdomains else setting_flags(ctx),
    )
    plan = plan_crawl(request, invocation.settings_tables)
    return start_crawl(plan, SystemClock(), invocation.reporter, default_hooks()).to_json()


def _with_subdomains(flags: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """--subdomains has no setting of its own: it is resolved into scope (design D11)."""
    crawl_flags = flags.get("crawl", {})
    scope = crawl_flags.get("scope", "subdomains")
    if scope != "subdomains":
        raise SpiderError(
            OPTION_CONFLICT,
            f"--subdomains means --scope subdomains, so it cannot be given with --scope {scope}.",
            hint="Give --scope alone, or --subdomains alone.",
            details={"options": ["--subdomains", "--scope"]},
        )
    return {**flags, "crawl": {**crawl_flags, "scope": "subdomains"}}
