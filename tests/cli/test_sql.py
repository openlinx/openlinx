"""Exercise read-only SQL and its result document through the public Command."""

import re
import signal
from codecs import BOM_UTF8
from pathlib import Path

import pytest

from tests.support.cli import run_cli, run_cli_process
from tests.support.crawls import create_any_crawl, create_crawl_at
from tests.support.workspace import TempWorkspace

_QUERY_CONFLICT = re.compile(
    r"\b(?:conflicts?|mutually exclusive|(?:never|not) both"
    r"|(?:cannot|can't)\b[^.!?]*\btogether)\b"
)
_REQUIRED_QUERY = re.compile(
    r"\b(?:required|missing|no (?:sql )?query|(?:not|didn't) (?:provide|supply|give))\b"
)
_LIMIT_HINT = r"^(?:use|pass|supply|give)\b(?=.*--limit)(?=.*\binteger\b).*\b1\b.*\b100,?000\b"


@pytest.fixture
def sql_crawl(temp_workspace: TempWorkspace) -> Path:
    return create_any_crawl(temp_workspace).path


def test_sql_returns_the_select_document(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT 1 AS one", "--crawl", str(sql_crawl))

    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "columns": ["one"],
        "rows": [[1]],
        "row_count": 1,
        "truncated": False,
        "limit": 1000,
    }


def test_sql_selects_the_explicit_or_latest_crawl(temp_workspace: TempWorkspace) -> None:
    initialized = run_cli("init", "--workspace", str(temp_workspace.root))
    assert initialized.exit_code == 0, initialized.stderr
    first = create_crawl_at(temp_workspace, "2026-09-27T14:03:12+00:00", "k3f9")
    second = create_crawl_at(temp_workspace, "2026-09-27T14:03:13+00:00", "k3f9")
    args = ("sql", "SELECT id FROM crawl", "--workspace", str(temp_workspace.root))

    explicit = run_cli(*args, "--crawl", first.id)
    latest = run_cli(*args)
    by_path = run_cli(*args, "--crawl", str(second.path))

    assert [result.exit_code for result in (explicit, latest, by_path)] == [0, 0, 0], (
        explicit.stderr,
        latest.stderr,
        by_path.stderr,
    )
    assert explicit.json()["rows"] == [["20260927-140312-k3f9"]]
    assert latest.json()["rows"] == by_path.json()["rows"] == [["20260927-140313-k3f9"]]


def test_sql_result_keeps_column_positions_and_reports_blob_lengths(sql_crawl: Path) -> None:
    result = run_cli(
        "sql", "SELECT 1 AS a, 2 AS a, x'00010203' AS b, NULL AS missing", "--crawl", str(sql_crawl)
    )

    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "columns": ["a", "a", "b", "missing"],
        "rows": [[1, 2, {"blob_bytes": 4}, None]],
        "row_count": 1,
        "truncated": False,
        "limit": 1000,
    }


def test_infinite_real_values_preserve_sign_and_type(sql_crawl: Path) -> None:
    result = run_cli_process(
        "sql",
        "SELECT 1e999 AS positive, -1e999 AS negative, NULL AS missing, 1.25 AS finite,"
        " 'Infinity' AS positive_text, '-Infinity' AS negative_text",
        "--crawl",
        str(sql_crawl),
    )

    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "columns": ["positive", "negative", "missing", "finite", "positive_text", "negative_text"],
        "rows": [
            [{"real": "Infinity"}, {"real": "-Infinity"}, None, 1.25, "Infinity", "-Infinity"]
        ],
        "row_count": 1,
        "truncated": False,
        "limit": 1000,
    }


@pytest.mark.parametrize(("limit_args", "limit"), [((), 1000), (("--limit", "5"), 5)])
def test_sql_row_limits(sql_crawl: Path, limit_args: tuple[str, ...], limit: int) -> None:
    result = run_cli(
        "sql",
        "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 1500)"
        " SELECT i FROM n",
        "--crawl",
        str(sql_crawl),
        *limit_args,
    )

    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "columns": ["i"],
        "rows": [[value] for value in range(1, limit + 1)],
        "row_count": limit,
        "truncated": True,
        "limit": limit,
    }


def test_sql_timeout_uses_the_declared_budget(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT 1", "--crawl", str(sql_crawl), "--timeout", "0")

    assert (result.exit_code, result.stdout) == (1, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_timeout"
    assert re.search(r"\b(?:increase|raise)\b.*--timeout", error["hint"] or "", re.I)


def test_sql_interrupted_during_workspace_lookup_can_be_retried(
    temp_workspace: TempWorkspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = temp_workspace.root / "named-workspace"
    workspace.mkdir()
    is_dir = Path.is_dir

    def interrupted_is_dir(path: Path) -> bool:
        if path == workspace:
            signal.raise_signal(signal.SIGINT)
        return is_dir(path)

    with monkeypatch.context() as filesystem:
        filesystem.setattr(Path, "is_dir", interrupted_is_dir)
        result = run_cli("sql", "SELECT 1", "--workspace", str(workspace))

    assert (result.exit_code, result.stdout) == (130, b"")
    (error,) = result.stderr_json_lines()
    assert error["code"] == "interrupted"
    assert re.search(r"\b(?:rerun|run .* again|retry)\b", error["hint"] or "", re.I), error


@pytest.mark.parametrize("existing_file", [False, True], ids=["missing", "regular-file"])
def test_sql_workspace_error_points_to_an_existing_directory(
    temp_workspace: TempWorkspace, existing_file: bool
) -> None:
    invalid = temp_workspace.root / "query inputs"
    if existing_file:
        invalid.write_text("SELECT 1", encoding="utf-8")

    result = run_cli("sql", "SELECT 1", "--workspace", str(invalid))

    assert (result.exit_code, result.stdout) == (4, b"")
    (error,) = result.errors()
    assert error["code"] == "workspace_not_found"
    assert re.search(r"\bexisting (?:Workspace )?(?:directory|folder)\b", error["hint"] or "", re.I)
    assert "--workspace" in error["hint"]


@pytest.mark.parametrize(
    ("option", "hint_pattern"),
    [
        ("--limit=0", _LIMIT_HINT),
        ("--limit=abc", _LIMIT_HINT),
        ("--timeout=-1", r"--timeout.*\b(?:nonnegative|non-negative)\b"),
        ("--timeout=abc", r"(?=.*--timeout)(?=.*\bfinite\b)(?=.*\bnon[- ]?negative\b).*seconds"),
        ("--timeout=nan", r"--timeout.*\bfinite\b"),
        ("--timeout=inf", r"--timeout.*\bfinite\b"),
    ],
)
def test_sql_invalid_option_value_explains_the_accepted_input(
    sql_crawl: Path, option: str, hint_pattern: str
) -> None:
    result = run_cli("sql", "SELECT 1", "--crawl", str(sql_crawl), option)

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "invalid_value"
    assert re.search(hint_pattern, error["hint"] or "", re.I), error


@pytest.mark.parametrize("extra", ["--file", "--unknown-sql-option", "extra-query"])
def test_sql_usage_errors_point_to_command_help(extra: str) -> None:
    result = run_cli("sql", "SELECT 1", extra)

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "usage_error"
    assert "linx sql --help" in (error["hint"] or ""), error


def test_unknown_column(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT adress FROM pages", "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_error"
    assert "no such column: adress" in error["message"]
    assert error["details"]["suggestions"][0] == "address"
    assert "linx schema" in error["hint"]


def test_sql_suggests_a_qualified_page_column(sql_crawl: Path) -> None:
    described = run_cli("schema", "pages", "--fields", "columns")
    assert described.exit_code == 0, described.stderr
    (page,) = described.json()["items"]
    assert "redirect_url" in {column["name"] for column in page["columns"]}

    result = run_cli("sql", "SELECT pages.redirec_url FROM pages", "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_error"
    assert "no such column: pages.redirec_url" in error["message"]
    assert error["details"]["suggestions"][0] == "redirect_url"


def test_sql_suggests_an_unknown_table(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT address FROM pagez", "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_error"
    assert "no such table: pagez" in error["message"]
    assert error["details"]["suggestions"][0] == "pages"
    assert "linx schema" in error["hint"]


def test_sql_reports_the_native_syntax_error(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT FROM pages", "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_error"
    assert 'near "FROM": syntax error' in error["message"]
    pattern = (
        r"\b(?:fix|correct|revise)\b.*\b(?:sql|query|statement)\b.*sqlite.*(?:error|diagnostic)"
    )
    assert re.search(pattern, error["hint"] or "", re.I), error


def test_sql_query_error_explains_how_to_recover(sql_crawl: Path) -> None:
    result = run_cli("sql", "SELECT unknown_sql_function()", "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_error"
    assert "no such function: unknown_sql_function" in error["message"]
    pattern = (
        r"\b(?:fix|correct|revise)\b.*\b(?:sql|query|statement)\b.*sqlite.*(?:error|diagnostic)"
    )
    assert re.search(pattern, error["hint"] or "", re.I), error


@pytest.mark.parametrize(
    ("query", "hint_pattern"),
    [
        ("DELETE FROM pages", r"\b(?:replace|rewrite)\b.*\bread-only\b.*\bSELECT\b"),
        ("PRAGMA user_version", r"\b(?:omit|remove)\b.*PRAGMA"),
        ("SELECT * FROM pragma_table_info('pages')", r"\b(?:run|use)\s+linx schema\b"),
        ("WITH x AS (SELECT 1) DELETE FROM pages", r"\b(?:replace|rewrite)\b.*\bread-only\b"),
        ("SELECT load_extension('example')", r"\b(?:remove|omit)\b.*\bload_extension\b"),
        (
            "SELECT 1; SELECT 2",
            r"^(?:pass|run|give|submit|execute|supply) (?:only )?"
            r"(?:one|a single) (?:SQL )?statement\b",
        ),
    ],
)
def test_sql_explains_how_to_replace_a_refused_statement(
    sql_crawl: Path, query: str, hint_pattern: str
) -> None:
    result = run_cli("sql", query, "--crawl", str(sql_crawl))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "sql_not_allowed"
    assert re.search(hint_pattern, error["hint"] or "", re.I), error


def test_sql_table_prints_query_text_literally(sql_crawl: Path) -> None:
    result = run_cli(
        "sql", "SELECT '[bold]text[/bold]' AS value", "--crawl", str(sql_crawl), "--format", "table"
    )

    assert result.exit_code == 0, result.stderr
    assert b"row_count" in result.stdout
    assert b"[bold]text[/bold]" in result.stdout


def test_sql_is_discoverable_as_a_document() -> None:
    result = run_cli("commands")
    assert result.exit_code == 0, result.stderr
    description = result.json()
    (entry,) = [command for command in description["commands"] if command["name"] == "sql"]
    assert (entry["output"], entry["formats"], entry["fields"]) == (
        "document",
        ["json", "table"],
        None,
    )
    assert [(arg["name"], arg["required"]) for arg in entry["arguments"]] == [("query", False)]
    options = {option["name"]: option for option in entry["options"]}
    assert set(options) == {"--crawl", "--workspace", "--format", "--limit", "--timeout", "--file"}
    assert [options["--limit"][key] for key in ("default", "min", "max")] == [1000, 1, 100000]
    assert options["--timeout"]["default"] == 30
    assert {"sql_error", "sql_not_allowed", "sql_timeout"} <= {
        diagnostic["code"] for diagnostic in description["diagnostics"]
    }


@pytest.mark.parametrize("query", ["SELECT 1", ""], ids=["sql", "empty-argument"])
def test_query_given_twice(tmp_path: Path, query: str) -> None:
    missing = tmp_path / "missing.sql"
    workspace = tmp_path / "missing-workspace"

    result = run_cli("sql", query, "--file", str(missing), "--workspace", str(workspace))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "usage_error"
    message = error["message"].casefold()
    assert "--file" in message
    assert re.search(r"\b(?:argument|positional|query)\b", message), message
    assert _QUERY_CONFLICT.search(message), message


def test_sql_requires_a_query(tmp_path: Path) -> None:
    result = run_cli("sql", "--workspace", str(tmp_path / "missing-workspace"))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "usage_error"
    message = error["message"].casefold()
    assert re.search(r"\b(?:query|sql)\b", message), message
    assert _REQUIRED_QUERY.search(message), message
    assert "--file" in (error["hint"] or "")


def test_sql_reads_a_relative_utf8_query_file(
    sql_crawl: Path, temp_workspace: TempWorkspace
) -> None:
    file = temp_workspace.root / "report query.sql"
    file.write_text("SELECT 'Привет' AS t\n", encoding="utf-8")

    result = run_cli("sql", "--file", file.name, "--crawl", str(sql_crawl))

    assert result.exit_code == 0, result.stderr
    assert result.json()["rows"] == [["Привет"]]


@pytest.mark.parametrize("kind", ["missing", "directory", "not-utf8"])
def test_sql_reports_query_file_errors(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "query.sql"
    if kind == "directory":
        path.mkdir()
    elif kind == "not-utf8":
        path.write_bytes(b"SELECT '\xff'")

    result = run_cli("sql", "--file", str(path))

    assert (result.exit_code, result.stdout) == (2, b"")
    (error,) = result.errors()
    assert error["code"] == "invalid_value"
    assert error["details"]["file"] == str(path)
    assert ("UTF-8" in error["message"]) is (kind == "not-utf8")
    pattern = (
        r"\b(?:save|convert|encode)\b.*UTF-8"
        if kind == "not-utf8"
        else r"(?=.*\breadable\b)(?=.*--file)"
    )
    assert re.search(pattern, error["hint"] or "", re.I), error


def test_query_file_with_a_byte_order_mark_on_windows(sql_crawl: Path, tmp_path: Path) -> None:
    file = tmp_path / "отчёт q.sql"
    file.write_bytes(BOM_UTF8 + "SELECT 'Привет' AS t\r\n".encode())

    result = run_cli_process("sql", "--file", str(file), "--crawl", str(sql_crawl))

    assert result.exit_code == 0, result.stderr
    assert not result.stdout.startswith(BOM_UTF8)
    assert result.json() == {
        "columns": ["t"],
        "rows": [["Привет"]],
        "row_count": 1,
        "truncated": False,
        "limit": 1000,
    }
