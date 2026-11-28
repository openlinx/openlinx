"""Run one read-only SQL query against a selected Crawl."""

from pathlib import Path
from typing import Annotated

import typer

from openlinx.cli.meta import Example, command_meta
from openlinx.cli.options import CrawlOpt, FormatOpt, WorkspaceOpt
from openlinx.naming import COMMAND_NAME
from openlinx.output.codes import INVALID_VALUE, USAGE_ERROR
from openlinx.output.diagnostics import OpenLinxError
from openlinx.output.sql import sql_document
from openlinx.output.writer import Format
from openlinx.query.sql import DEFAULT_SQL_LIMIT, DEFAULT_SQL_TIMEOUT, MAX_SQL_LIMIT
from openlinx.services.query import QueryRequest, sql_query
from openlinx.store.records import LATEST


@command_meta(
    name="sql",
    output="document",
    formats=[Format.JSON, Format.TABLE],
    examples=[
        Example(f'{COMMAND_NAME} sql "SELECT 1 AS one"', "Run a read-only query."),
        Example(f"{COMMAND_NAME} sql --file query.sql", "Run a query from a UTF-8 file."),
    ],
)
def sql(
    query: Annotated[str | None, typer.Argument(metavar="QUERY", help="SQL to run.")] = None,
    query_file: Annotated[
        Path | None, typer.Option("--file", help="Read the query from a UTF-8 file.")
    ] = None,
    workspace_dir: WorkspaceOpt = None,
    crawl: CrawlOpt = LATEST,
    output_format: FormatOpt = Format.JSON,
    limit: Annotated[
        int, typer.Option("--limit", min=1, max=MAX_SQL_LIMIT, help="Maximum result rows.")
    ] = DEFAULT_SQL_LIMIT,
    timeout: Annotated[
        float, typer.Option("--timeout", min=0.0, help="SQL execution deadline in seconds.")
    ] = DEFAULT_SQL_TIMEOUT,
) -> dict[str, object]:
    """Run one read-only SELECT or WITH statement."""
    statement = _query_text(query, query_file)
    request = QueryRequest(cwd=Path.cwd(), home=Path.home(), workspace=workspace_dir, crawl=crawl)
    return sql_document(sql_query(request, statement, limit=limit, timeout=timeout))


def _query_text(query: str | None, file: Path | None) -> str:
    hint = "Give a query argument or use --file PATH."
    if query is not None:
        if file is not None:
            raise OpenLinxError(USAGE_ERROR, "The query argument and --file conflict.", hint=hint)
        return query
    if file is None:
        raise OpenLinxError(USAGE_ERROR, "A SQL query is required.", hint=hint)

    try:
        return file.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise OpenLinxError(
            INVALID_VALUE, f"SQL query file {file} must be UTF-8.", details={"file": str(file)}
        ) from error
    except OSError as error:
        raise OpenLinxError(
            INVALID_VALUE,
            f"Cannot read SQL query file {file}: {error.strerror or error}",
            details={"file": str(file)},
        ) from error
