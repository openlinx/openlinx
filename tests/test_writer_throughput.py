"""The writer's throughput check runs on the schema a Crawl declares (017-speed-up-crawl-writer
D11)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "writer_throughput.py"


@pytest.mark.slow
def test_the_writer_throughput_check_runs_on_the_declared_schema() -> None:
    # A real process, since the check spawns its reader; 105 Pages is the smallest run it takes.
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--pages", "105"],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(run.stdout)

    # The rate floor is the full run's: over 105 Pages it says nothing.
    assert (
        report.get("run_failed"),
        report.get("atomicity", {}).get("ok"),
        report.get("reader", {}).get("exit_code"),
    ) == (None, True, 0)
