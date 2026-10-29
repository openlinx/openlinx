"""The two console scripts, linx and openlinx (021-rename-to-openlinx design D1 and D4)."""

from importlib.metadata import distribution


def test_both_console_scripts_run_the_same_entry_point() -> None:
    scripts = {
        entry.name: entry.value
        for entry in distribution("openlinx").entry_points
        if entry.group == "console_scripts"
    }

    assert scripts == {"linx": "openlinx.cli.app:main", "openlinx": "openlinx.cli.app:main"}
