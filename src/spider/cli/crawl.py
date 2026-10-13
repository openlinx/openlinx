"""`spider crawl` over the Crawl Service (020-add-crawl-core D10, D11)."""

from typing import Annotated, Any

import typer

from spider.cli.meta import Example, command_meta
from spider.cli.options import FormatOpt
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
    url: Annotated[
        str,
        typer.Argument(
            help="The Seed: an http or https URL, or a host such as site.test, which gets "
            "https://.",
            show_default=False,
        ),
    ],
    output_format: FormatOpt = Format.JSON,
) -> dict[str, Any]:
    """Crawl a site from one Seed URL, in the foreground.

    Follows Links from the Seed within the Scope and records every URL in a new crawl file of
    the Workspace. Progress events go to stderr, and the result to stdout when the Crawl ends.
    """
    # Imported here: the crawler stays off the CLI's startup path.
    from spider.services.crawling import CrawlRequest, plan_crawl

    plan = plan_crawl(CrawlRequest(url))
    return {"seed": plan.seed}
