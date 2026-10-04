"""List Commands (010-add-workspace-and-cli-contract, cli-contract)."""

from tests.support.app import example_app
from tests.support.cli import run_cli


def test_compact_document() -> None:
    result = run_cli("example-list", "--limit", "5", app=example_app())

    assert result.stdout == (
        b'{"total":5,"items":[{"n":1},{"n":2},{"n":3},{"n":4},{"n":5}],"next_cursor":null}\n'
    )


def test_items_as_lines() -> None:
    result = run_cli("example-list", "--format", "jsonl", "--limit", "2", app=example_app())

    assert result.stdout == b'{"n":1}\n{"n":2}\n'


def test_a_list_table_shows_items_not_the_envelope() -> None:
    stdout = run_cli("example-list", "--format", "table", app=example_app()).stdout

    assert (b"next_cursor" in stdout, b"items" in stdout) == (False, False)


def test_first_page() -> None:
    page = run_cli("example-list", "--limit", "2", app=example_app()).json()

    assert (page["total"], page["items"], type(page["next_cursor"]), page["next_cursor"] != "") == (
        5,
        [{"n": 1}, {"n": 2}],
        str,
        True,
    )


def test_following_cursors() -> None:
    app = example_app()
    pages = [run_cli("example-list", "--limit", "2", app=app).json()]
    while pages[-1]["next_cursor"] is not None and len(pages) < 10:
        cursor = pages[-1]["next_cursor"]
        pages.append(run_cli("example-list", "--limit", "2", "--cursor", cursor, app=app).json())

    assert [page["items"] for page in pages] == [
        [{"n": 1}, {"n": 2}],
        [{"n": 3}, {"n": 4}],
        [{"n": 5}],
    ]


def test_everything_on_one_page() -> None:
    page = run_cli("example-list", app=example_app()).json()

    assert (len(page["items"]), page["next_cursor"]) == (5, None)


def test_default_limit() -> None:
    page = run_cli("example-long-list", app=example_app()).json()

    assert (page["items"], type(page["next_cursor"])) == ([{"n": n} for n in range(1, 51)], str)


def test_count_only() -> None:
    result = run_cli("example-list", "--limit", "0", app=example_app())

    assert result.stdout == b'{"total":5,"items":[],"next_cursor":null}\n'
