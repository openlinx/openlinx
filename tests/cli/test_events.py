"""Progress events (010-add-workspace-and-cli-contract, cli-contract)."""

import json

from tests.support.app import example_app
from tests.support.cli import (
    PROCESS_TIMEOUT,
    run_cli,
    run_example_process,
    start_example_process,
)


def test_the_result_goes_to_stdout() -> None:
    assert run_cli("example-progress", app=example_app()).stdout == b'{"urls":10}\n'


def test_events_go_to_stderr() -> None:
    lines = run_cli("example-progress", app=example_app()).stderr_json_lines()

    assert [line["event"] for line in lines] == ["progress", "progress"]


def test_events_and_diagnostics_share_stderr() -> None:
    lines = run_example_process("example-mixed").stderr_json_lines()

    assert [sorted(set(line) & {"event", "level"}) for line in lines] == [
        ["event"],
        ["level"],
        ["event"],
    ]


def test_a_warning_is_readable_at_once() -> None:
    process = start_example_process("example-warn-and-wait")
    assert process.stderr is not None
    warning = process.stderr.readline()
    process.communicate(b"go\n", timeout=PROCESS_TIMEOUT)

    assert json.loads(warning or b"null") == {
        "level": "warning",
        "code": "example_warning",
        "message": "An example warning.",
        "hint": None,
        "details": {},
    }
