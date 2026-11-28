"""Read Pages from a real Crawl through the public CLI."""

import re
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest

from openlinx.store.connections import connect
from tests.fixture_site.plugin import StartSite
from tests.fixture_site.routes import Page, Site, Status
from tests.support.cli import run_cli
from tests.support.crawling import crawl_result
from tests.support.crawls import sha256_of
from tests.support.workspace import TempWorkspace


def test_unknown_field_in_fields(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(Site({"/": Page(body="<title>Home</title>")}))
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"
    before = sha256_of(crawl.crawl_file)
    selected = ("pages", "--crawl", str(crawl.crawl_file))

    result = run_cli(*selected, "--fields", "adress,title_1")

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["level"], error["code"]) == ("error", "unknown_field")
    assert error["details"]["field"] == "adress"

    schema = run_cli("schema", "pages")
    assert schema.exit_code == 0, schema.stderr
    (table,) = schema.json()["items"]
    assert error["details"]["available"] == [column["name"] for column in table["columns"]]

    corrected = run_cli(*selected, "--fields", "address,title_1")
    assert corrected.exit_code == 0, corrected.stderr
    assert corrected.json() == {
        "total": 1,
        "items": [{"address": site.url("/"), "title_1": "Home"}],
        "next_cursor": None,
    }
    assert sha256_of(crawl.crawl_file) == before


def test_filtered_listing(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(
        Site(
            {
                "/": Page(
                    body='<a href="/a-ok">A</a><a href="/b-gone">B</a>'
                    '<a href="/c-ok">C</a><a href="/d-gone">D</a>'
                ),
                "/a-ok": Page(body="<title>Found A</title>"),
                "/b-gone": Status(404, body="<html><p>Gone B</p></html>"),
                "/c-ok": Page(body="<title>Found C</title>"),
                "/d-gone": Status(404, body="<html><p>Gone D</p></html>"),
            }
        )
    )
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"
    before = sha256_of(crawl.crawl_file)
    selected = ("pages", "--crawl", str(crawl.crawl_file))
    projection = ("--fields", "address,status_code")
    filtered = (*selected, "--where", "status_code = 404")

    all_pages = run_cli(*selected, *projection)
    assert all_pages.exit_code == 0, all_pages.stderr
    assert all_pages.json()["total"] == 5

    result = run_cli(*filtered, *projection)
    assert result.exit_code == 0, result.stderr
    assert result.json() == {
        "total": 2,
        "items": [
            {"address": site.url("/b-gone"), "status_code": 404},
            {"address": site.url("/d-gone"), "status_code": 404},
        ],
        "next_cursor": None,
    }

    first = run_cli(*filtered, "--fields", "status_code", "--limit", "1")
    assert first.exit_code == 0, first.stderr
    first_page = first.json()
    assert first_page["items"] == [{"status_code": 404}]
    assert first_page["total"] == 2
    cursor = first_page["next_cursor"]
    assert isinstance(cursor, str)
    assert cursor

    second = run_cli(*filtered, *projection, "--limit", "2", "--cursor", cursor)
    assert second.exit_code == 0, second.stderr
    assert second.json() == {
        "total": 2,
        "items": [{"address": site.url("/d-gone"), "status_code": 404}],
        "next_cursor": None,
    }

    different_filter = run_cli(*selected, "--where", "status_code = 200", "--cursor", cursor)
    assert different_filter.exit_code == 2
    assert different_filter.stderr_json_lines()[-1]["code"] == "invalid_cursor"

    count = run_cli(*filtered, *projection, "--limit", "0")
    assert count.exit_code == 0, count.stderr
    assert count.json() == {"total": 2, "items": [], "next_cursor": None}
    assert sha256_of(crawl.crawl_file) == before
    assert sorted((request.method, request.path) for request in site.requests) == [
        ("GET", "/"),
        ("GET", "/a-ok"),
        ("GET", "/b-gone"),
        ("GET", "/c-ok"),
        ("GET", "/d-gone"),
        ("GET", "/robots.txt"),
    ]


def test_error_shape(temp_workspace: TempWorkspace, fixture_site: StartSite) -> None:
    site = fixture_site(Site({"/": Page(body="<title>Home</title>")}))
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"

    result = run_cli("pages", "--crawl", str(crawl.crawl_file), "--where", "(")

    assert result.exit_code == 2
    assert result.stdout == b""
    error = result.stderr_json_lines()[-1]
    assert (error["level"], error["code"]) == ("error", "invalid_where")
    assert isinstance(error["message"], str)
    assert error["message"].strip()
    assert isinstance(error["hint"], str)
    assert error["hint"].strip()


@pytest.fixture
def home_page_crawl(
    temp_workspace: TempWorkspace, fixture_site: StartSite
) -> Iterator[tuple[Path, str]]:
    site = fixture_site(Site({"/": Page(body="<title>Home</title><p>Home page.</p>")}))
    crawl = crawl_result(site.url("/"))
    assert crawl.summary.state == "completed"
    before = sha256_of(crawl.crawl_file)

    yield crawl.crawl_file, site.url("/")

    assert sha256_of(crawl.crawl_file) == before
    assert sorted((request.method, request.path) for request in site.requests) == [
        ("GET", "/"),
        ("GET", "/robots.txt"),
    ]


def test_unknown_column_in_where(home_page_crawl: tuple[Path, str]) -> None:
    crawl_file, address = home_page_crawl
    selected = ("pages", "--crawl", str(crawl_file), "--fields", "address,status_code")
    corrected = run_cli(*selected, "--where", "status_code = 200")
    assert corrected.exit_code == 0, corrected.stderr
    assert corrected.json() == {
        "total": 1,
        "items": [{"address": address, "status_code": 200}],
        "next_cursor": None,
    }

    result = run_cli(*selected, "--where", "stauts_code = 200")

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["level"], error["code"]) == ("error", "unknown_column")
    assert "stauts_code" in error["message"]
    assert error["details"]["suggestions"][0] == "status_code"
    assert "linx schema" in error["hint"]


def _assert_comparison_type_error(
    home_page_crawl: tuple[Path, str],
    *,
    valid: str,
    invalid: str,
    column: str,
    column_type: str,
) -> None:
    crawl_file, address = home_page_crawl
    selected = ("pages", "--crawl", str(crawl_file), "--fields", "address")
    control = run_cli(*selected, "--where", valid)
    assert control.exit_code == 0, control.stderr
    assert control.json() == {
        "total": 1,
        "items": [{"address": address}],
        "next_cursor": None,
    }

    result = run_cli(*selected, "--where", invalid)

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["level"], error["code"]) == ("error", "invalid_where")
    message = error["message"]
    assert column in message
    assert column_type in message.upper()
    assert re.search(r"\bliterals?\b", message, re.IGNORECASE)
    # Accept both a type difference and a positive requirement for a compatible type.
    assert re.search(
        r"\b(?:type mismatch|(?:incompatible|different|wrong|unexpected|compatible|matching|"
        r"expected|correct|same) types?|(?:does not|doesn't|do not|must) match\b[^.]*\btype)\b",
        message,
        re.IGNORECASE,
    )
    hint = error["hint"]
    assert isinstance(hint, str)
    assert "linx schema" in hint
    assert re.search(r"\b(?:type|literal)\b", hint, re.IGNORECASE)


@pytest.mark.parametrize(
    ("valid", "invalid", "column", "column_type"),
    [
        ("status_code = 200", "status_code = 'abc'", "status_code", "INTEGER"),
        ("status_code = 200", "status_code = '200'", "status_code", "INTEGER"),
        ("text_ratio_pct >= 0.0", "text_ratio_pct >= '0.0'", "text_ratio_pct", "REAL"),
    ],
)
def test_string_compared_with_a_number_column(
    home_page_crawl: tuple[Path, str],
    valid: str,
    invalid: str,
    column: str,
    column_type: str,
) -> None:
    _assert_comparison_type_error(
        home_page_crawl,
        valid=valid,
        invalid=invalid,
        column=column,
        column_type=column_type,
    )


def test_number_compared_with_a_text_column(home_page_crawl: tuple[Path, str]) -> None:
    _assert_comparison_type_error(
        home_page_crawl,
        valid="title_1 = 'Home'",
        invalid="title_1 > 5",
        column="title_1",
        column_type="TEXT",
    )


def test_boolean_literal_requires_a_boolean_column(home_page_crawl: tuple[Path, str]) -> None:
    _assert_comparison_type_error(
        home_page_crawl,
        valid="meta_robots_noindex = false",
        invalid="status_code = true",
        column="status_code",
        column_type="INTEGER",
    )


def test_contains_is_scoped_to_pages(home_page_crawl: tuple[Path, str]) -> None:
    crawl_file, address = home_page_crawl
    selected = ("--crawl", str(crawl_file))
    pages = run_cli("pages", *selected, "--where", "title_1 contains 'hOME'", "--fields", "address")
    assert pages.exit_code == 0, pages.stderr
    assert pages.json() == {"total": 1, "items": [{"address": address}], "next_cursor": None}

    sql = run_cli("sql", "SELECT openlinx_contains('Home', 'hOME')", *selected)
    assert (sql.exit_code, sql.stdout) == (2, b"")
    (error,) = sql.errors()
    assert error["code"] == "sql_error"
    assert "no such function: openlinx_contains" in error["message"]


def test_position_of_a_syntax_error(home_page_crawl: tuple[Path, str]) -> None:
    crawl_file, address = home_page_crawl
    selected = ("pages", "--crawl", str(crawl_file), "--fields", "address")
    control = run_cli(*selected, "--where", "status_code = 200")
    assert control.exit_code == 0, control.stderr
    assert control.json() == {
        "total": 1,
        "items": [{"address": address}],
        "next_cursor": None,
    }

    result = run_cli(*selected, "--where", "status_code = = 200")

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["level"], error["code"]) == ("error", "invalid_where")
    assert re.search(r"\bposition 15\b", error["message"])


def test_sql_cannot_be_smuggled_in(home_page_crawl: tuple[Path, str]) -> None:
    crawl_file, _ = home_page_crawl
    selected = ("pages", "--crawl", str(crawl_file), "--fields", "address")

    quoted = run_cli(*selected, "--where", "address contains ';'")
    assert quoted.exit_code == 0, quoted.stderr
    assert quoted.json() == {"total": 0, "items": [], "next_cursor": None}

    result = run_cli(*selected, "--where", "address = 'x'; DROP TABLE pages")

    assert result.exit_code == 2
    assert result.stdout == b""
    (error,) = result.stderr_json_lines()
    assert (error["level"], error["code"]) == ("error", "invalid_where")
    assert re.search(r"\bposition 14\b", error["message"])


def test_a_smuggling_attempt_leaves_the_store_unchanged(
    home_page_crawl: tuple[Path, str],
) -> None:
    crawl_file, _ = home_page_crawl
    with closing(connect(crawl_file, read_only=True)) as connection:
        before = tuple(connection.iterdump())

    result = run_cli(
        "pages", "--crawl", str(crawl_file), "--where", "address = 'x'; DROP TABLE pages"
    )

    assert result.exit_code == 2
    assert result.stderr_json_lines()[-1]["code"] == "invalid_where"
    with closing(connect(crawl_file, read_only=True)) as connection:
        after = tuple(connection.iterdump())
    assert after == before
