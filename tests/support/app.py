"""The fixture app the scenarios use (design D8 of 010-add-workspace-and-cli-contract)."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from spider.cli.app import AppExtra, build_app
from spider.cli.meta import command_meta
from spider.cli.options import (
    CrawlOpt,
    CursorOpt,
    FieldsOpt,
    FormatOpt,
    LimitOpt,
    OptionMeta,
    WorkspaceOpt,
)
from spider.cli.runner import Invocation, SpiderGroup
from spider.output.codes import DiagnosticCode, ExitCode
from spider.output.diagnostics import Diagnostic, Outcome, SpiderError
from spider.output.paging import Fields, Page, fingerprint, paginate, select_fields
from spider.output.writer import Format
from spider.store.records import LATEST
from spider.workspace.discovery import resolve_workspace
from spider.workspace.tables import SettingsTables

# Declared here, not in spider.output.codes: the tool never lists the fixture app's codes.
EXAMPLE_FAILED = DiagnosticCode(
    code="example_failed",
    level="error",
    exit_code=ExitCode.FAILED,
    description="The example failed.",
)
EXAMPLE_WARNING_CODE = DiagnosticCode(
    code="example_warning", level="warning", exit_code=None, description="An example warning."
)
EXAMPLE_WARNING = Diagnostic.of(EXAMPLE_WARNING_CODE, "An example warning.")
# References, not imports: the tables load only with the settings.
EXAMPLE_TABLE = "tests.support.settings:ExampleSettings"
GROUPS_TABLE = "tests.support.settings:GroupsTable"
EXAMPLE_LIST = "example-list"
EXAMPLE_LONG_LIST = "example-long-list"
EXAMPLE_READ_CRAWL = "example-read-crawl"
EXAMPLE_FIELDS = Fields(available=("n", "sq"), default=("n",))


@command_meta(
    name=EXAMPLE_LIST,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=EXAMPLE_FIELDS,
)
def example_list(
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
    odd: Annotated[bool, typer.Option("--odd", help="Only the items with an odd n.")] = False,
) -> Page:
    """The example list Command of the cli-contract scenarios."""
    items = [{"n": n, "sq": n * n} for n in range(1, 6) if n % 2 or not odd]
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(EXAMPLE_LIST, {"odd": odd}),
        fields=select_fields(fields, EXAMPLE_FIELDS),
    )


N_ONLY = Fields(available=("n",), default=("n",))


@command_meta(
    name=EXAMPLE_LONG_LIST,
    output="list",
    formats=[Format.JSON, Format.JSONL, Format.TABLE],
    fields=N_ONLY,
)
def example_long_list(
    output_format: FormatOpt = Format.JSON,
    limit: LimitOpt = 50,
    cursor: CursorOpt = None,
    fields: FieldsOpt = None,
) -> Page:
    """A list Command whose items are n=1 to n=60."""
    items = [{"n": n} for n in range(1, 61)]
    return paginate(
        items,
        limit=limit,
        cursor=cursor,
        fingerprint=fingerprint(EXAMPLE_LONG_LIST, {}),
        fields=select_fields(fields, N_ONLY),
    )


@command_meta(output="rows", formats=[Format.JSONL], fields=N_ONLY)
def example_rows(output_format: FormatOpt = Format.JSONL) -> Iterator[Any]:
    """A rows Command that returns the rows n=1 and n=2."""
    yield {"n": 1}
    yield {"n": 2}


@command_meta(output="rows", formats=[Format.JSONL], fields=N_ONLY)
def example_rows_waiting(output_format: FormatOpt = Format.JSONL) -> Iterator[Any]:
    """Yields n=1, waits for a line on stdin, then yields n=2."""
    yield {"n": 1}
    sys.stdin.readline()
    yield {"n": 2}


@command_meta(output="rows", formats=[Format.JSONL], fields=N_ONLY)
def example_rows_interrupted(output_format: FormatOpt = Format.JSONL) -> Iterator[Any]:
    """Yields n=1, then stops as if Ctrl+C was pressed while the rows stream."""
    yield {"n": 1}
    raise KeyboardInterrupt


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_needs_argument(name: str, output_format: FormatOpt = Format.JSON) -> Any:
    """Takes one required argument."""
    return {"name": name}


@command_meta(output="document", formats=[Format.JSON, Format.TABLE], events=True)
def example_progress(ctx: typer.Context, output_format: FormatOpt = Format.JSON) -> Any:
    """Reports two progress events, then ends with the result urls=10."""
    invocation: Invocation = ctx.obj
    invocation.reporter.event("progress", crawled=5)
    invocation.reporter.event("progress", crawled=10)
    return {"urls": 10}


@command_meta(output="document", formats=[Format.JSON, Format.TABLE], events=True)
def example_mixed(ctx: typer.Context, output_format: FormatOpt = Format.JSON) -> Any:
    """Reports a progress event, then a warning, then a second progress event."""
    invocation: Invocation = ctx.obj
    invocation.reporter.event("progress", crawled=1)
    invocation.reporter.warn(EXAMPLE_WARNING)
    invocation.reporter.event("progress", crawled=2)
    return {"urls": 2}


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_warn_and_wait(ctx: typer.Context, output_format: FormatOpt = Format.JSON) -> Any:
    """Writes a warning, then waits for a line on stdin before it ends."""
    invocation: Invocation = ctx.obj
    invocation.reporter.warn(EXAMPLE_WARNING)
    sys.stdin.readline()
    return {"done": True}


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_failed_outcome(output_format: FormatOpt = Format.JSON) -> Outcome:
    """Ends with the result state=failed and an error whose exit code is 1."""
    return Outcome({"state": "failed"}, SpiderError(EXAMPLE_FAILED, "The example failed."))


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_raises(output_format: FormatOpt = Format.JSON) -> Any:
    """Raises RuntimeError("disk exploded")."""
    raise RuntimeError("disk exploded")


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_warning_inside(output_format: FormatOpt = Format.JSON) -> Any:
    """Ends with a result whose warnings list holds one warning."""
    return {"warnings": [EXAMPLE_WARNING.to_json()]}


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_interrupted(output_format: FormatOpt = Format.JSON) -> Any:
    """Stops as if Ctrl+C was pressed."""
    raise KeyboardInterrupt


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_aborted(output_format: FormatOpt = Format.JSON) -> Any:
    """Stops with Click's Abort, as Ctrl+C inside Click does."""
    raise typer.Abort


@command_meta(output="document", formats=[Format.JSON, Format.TABLE])
def example_settings(
    output_format: FormatOpt = Format.JSON,
    level: Annotated[
        str | None,
        typer.Option("--level", help="How much the example does."),
        OptionMeta(setting="example.level"),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", help="The example's token."),
        OptionMeta(setting="example.token"),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="A key that maps to no setting."),
        OptionMeta(secret=True),
    ] = None,
) -> Any:
    """Has options mapped to the settings example.level and example.token, and --api-key."""
    return {"level": level}


@command_meta(name=EXAMPLE_READ_CRAWL, output="document", formats=[Format.JSON, Format.TABLE])
def example_read_crawl(
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
) -> Any:
    """Reads the --crawl Crawl and reports its id, as the Commands of 050 will."""
    # Imported here, as in every Command that reads a Crawl: sqlalchemy stays off --help.
    from spider.store.selection import resolve_crawl

    workspace = resolve_workspace(cwd=Path.cwd(), flag=workspace_dir, home=Path.home())
    return {"crawl": resolve_crawl(crawl, workspace=workspace, cwd=Path.cwd()).id}


def example_app() -> typer.Typer:
    return build_app(
        extra=AppExtra(
            settings_tables={"example": EXAMPLE_TABLE, "groups": GROUPS_TABLE},
            commands=[
                example_list,
                example_long_list,
                example_rows,
                example_rows_waiting,
                example_rows_interrupted,
                example_needs_argument,
                example_progress,
                example_mixed,
                example_warn_and_wait,
                example_failed_outcome,
                example_raises,
                example_warning_inside,
                example_interrupted,
                example_aborted,
                example_settings,
                example_read_crawl,
            ],
        )
    )


def settings_tables(app: typer.Typer) -> SettingsTables:
    """The settings tables an app registered, as its Commands see them."""
    return cast(SpiderGroup, typer.main.get_group(app)).settings_tables
